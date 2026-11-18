import sys
import uuid
import logging
import asyncio
from pathlib import Path
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    BufferedInputFile
)
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

import config
from transcriber import WhisperService
from text_utils import split_text_into_chunks, create_transcription_txt, format_timestamp

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("TranscribeBot")

# Инициализация бота и диспетчера
bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Глобальный сервис Whisper
whisper_service: WhisperService

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".opus", ".aiff", ".alac",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".3gp", ".m4v"
}


@dp.message(Command("start", "help"))
async def cmd_start_help(message: Message):
    if not config.is_user_allowed(message.from_user.id if message.from_user else 0):
        await message.reply("⛔ <i>Извините, у вас нет доступа к этому боту.</i>")
        return

    text = (
        "👋 <b>Привет! Я бот для транскрибации аудио и видео в текст.</b>\n\n"
        "⚡ <b>Движок:</b> Faster-Whisper\n\n"
        "📥 <b>Что можно отправлять:</b>\n"
        "• 🎙 Голосовые сообщения (включая пересланные)\n"
        "• 🔘 Кружочки (видеосообщения)\n"
        "• 🎵 Аудиофайлы и подкасты (MP3, WAV, OGG, M4A, FLAC и т.д.)\n"
        "• 🎬 Видеозаписи (MP4, MKV, MOV, AVI и т.д.)\n"
        "• 📁 Документы с аудио/видео файлами\n\n"
        "📤 <b>Как я отдаю результат:</b>\n"
        "• 💬 Сообщениями прямо в чат (если текста много — делю на аккуратные части)\n"
        "• 📄 Всегда прикрепляю цельный <b>.txt</b> файл с полным текстом и таймкодами!\n\n"
        "<i>Просто запишите голосовое или отправьте любой медиафайл!</i>"
    )
    await message.answer(text)


def is_supported_document(message: Message) -> bool:
    if not message.document:
        return False
    doc = message.document
    if doc.mime_type and (doc.mime_type.startswith("audio/") or doc.mime_type.startswith("video/")):
        return True
    if doc.file_name:
        ext = Path(doc.file_name).suffix.lower()
        if ext in SUPPORTED_EXTENSIONS:
            return True
    return False


@dp.message(F.voice | F.audio | F.video_note | F.video | F.document)
async def handle_media(message: Message):
    # Проверка доступа
    user_id = message.from_user.id if message.from_user else 0
    if not config.is_user_allowed(user_id):
        await message.reply("⛔ <i>У вас нет доступа к использованию этого бота.</i>")
        return

    # Определение типа медиа
    media = None
    default_ext = ".ogg"
    orig_name = "audio"

    if message.voice:
        media = message.voice
        default_ext = ".ogg"
        orig_name = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elif message.video_note:
        media = message.video_note
        default_ext = ".mp4"
        orig_name = f"video_note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    elif message.audio:
        media = message.audio
        orig_name = message.audio.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        default_ext = Path(orig_name).suffix or ".mp3"
    elif message.video:
        media = message.video
        orig_name = message.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        default_ext = Path(orig_name).suffix or ".mp4"
    elif message.document:
        if not is_supported_document(message):
            await message.reply("⚠️ <i>Этот документ не похож на аудио или видео файл. Отправьте медиафайл со звуком.</i>")
            return
        media = message.document
        orig_name = message.document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        default_ext = Path(orig_name).suffix or ".mp4"

    if not media:
        return

    status_msg = await message.reply("⏳ <i>Скачиваю медиафайл...</i>")
    temp_file_path = None

    try:
        # Скачиваем файл из Telegram
        try:
            file_info = await bot.get_file(media.file_id)
        except TelegramBadRequest as e:
            if "file is too big" in str(e).lower():
                await status_msg.edit_text(
                    "⚠️ <b>Файл слишком большой!</b>\n"
                    "Telegram Bot API ограничивает загрузку файлов размером более 20 МБ.\n"
                    "Пожалуйста, отправьте более короткий фрагмент или сжатое аудио."
                )
                return
            raise

        if not file_info.file_path:
            raise RuntimeError("Telegram не вернул путь к медиафайлу.")
        ext = Path(file_info.file_path).suffix or default_ext
        unique_name = f"{uuid.uuid4().hex}{ext}"
        temp_file_path = config.TEMP_DIR / unique_name

        await bot.download_file(file_info.file_path, destination=temp_file_path)

        await status_msg.edit_text("🎙️ <i>Идёт расшифровка...</i>")

        # Запуск транскрибации в потоке
        result = await whisper_service.transcribe_async(str(temp_file_path))

        full_text = result["full_text"]
        if not full_text:
            await status_msg.edit_text("⚠️ <i>В полученной записи не удалось обнаружить речь.</i>")
            return

        # Разбиваем текст на блоки с поддержкой кликабельного копирования (<pre>)
        chunks = split_text_into_chunks(full_text)

        # Отправляем первый блок редактированием статусного сообщения
        await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)

        # Если блоков несколько, отправляем остальные частями
        for chunk in chunks[1:]:
            await message.answer(chunk, parse_mode=ParseMode.HTML)

        # Формируем и отправляем TXT-файл с полным текстом и таймкодами
        txt_content = create_transcription_txt(
            filename=orig_name,
            duration=result["duration"],
            language=result["language"],
            full_text=full_text,
            segments=result["segments"]
        )

        txt_filename = f"{Path(orig_name).stem}_расшифровка.txt"
        doc_file = BufferedInputFile(
            file=txt_content.encode("utf-8"),
            filename=txt_filename
        )

        caption_info = (
            f"📄 <b>Полный текст расшифровки</b>\n"
            f"⏱ Длительность: {format_timestamp(result['duration'])}\n"
            f"🌍 Язык: {result['language']} (обработано за {result['elapsed_time']:.1f}с)"
        )
        await message.reply_document(doc_file, caption=caption_info)

    except Exception:
        logger.exception("Ошибка при обработке медиафайла")
        error_text = "❌ Не удалось обработать запись. Попробуйте отправить файл ещё раз."
        try:
            await status_msg.edit_text(error_text)
        except TelegramBadRequest:
            await message.reply(error_text)

    finally:
        # Удаляем временный файл с диска
        if temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Не удалось удалить временный файл {temp_file_path}: {e}")


@dp.message()
async def handle_other_messages(message: Message):
    """Ответ на обычные текстовые сообщения без медиа."""
    if not config.is_user_allowed(message.from_user.id if message.from_user else 0):
        return
    await message.reply(
        "💡 Отправьте мне <b>голосовое сообщение</b>, <b>кружочек</b>, <b>аудиозапись</b> или <b>видео</b> со звуком — и я переведу его в текст!"
    )


async def main():
    global whisper_service
    logger.info("==================================================")
    logger.info("  Запуск Telegram-бота транскрибации (Faster-Whisper)")
    logger.info("==================================================")

    logger.info("Инициализация модели Faster-Whisper...")
    whisper_service = WhisperService.get_instance()
    logger.info("Модель готова к работе!")

    # Удаляем вебхук и запускаем polling
    async with bot:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("🚀 Бот успешно запущен и слушает новые сообщения...")
        await dp.start_polling(bot, close_bot_session=False)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
