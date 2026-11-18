# Telegram-бот транскрибации

Бот преобразует голосовые сообщения, видеокружки, аудио и видео в текст с помощью Faster-Whisper. Он отправляет расшифровку в чат и прикладывает TXT-файл с таймкодами. Распознавание выполняется на компьютере, где запущен бот. Telegram используется для получения медиа и отправки результата.

## Быстрый старт

Установите Python 3.11 и получите токен бота у [@BotFather](https://t.me/BotFather). При первом запуске Faster-Whisper скачает выбранную модель с Hugging Face.

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Впишите токен в `BOT_TOKEN` в файле `.env`. Для личного бота укажите свой числовой Telegram ID в `ALLOWED_USERS`. Запустите бота.

```powershell
.\run_bot.bat
```

**Linux / macOS**

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Заполните `BOT_TOKEN` и `ALLOWED_USERS` в `.env`, затем запустите `.venv/bin/python bot.py`.

Откройте чат с ботом, отправьте `/start`, затем голосовое сообщение или медиафайл со звуком. Облачный Telegram Bot API позволяет ботам скачивать файлы размером до [20 МБ](https://core.telegram.org/bots/api#getfile).

## NVIDIA GPU

Шаблон запускает модель `small` на CPU. Для более точного распознавания на NVIDIA GPU используйте этот блок настроек.

```dotenv
WHISPER_MODEL=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
```

Для CUDA на Windows и Linux нужны совместимые драйвер NVIDIA, cuBLAS для CUDA 12 и cuDNN 9. Добавьте каталоги библиотек в `PATH` на Windows или настройте пути динамического загрузчика на Linux. Подробнее см. [настройку GPU в Faster-Whisper](https://github.com/SYSTRAN/faster-whisper#gpu). При сбое CUDA бот загружает ту же модель на CPU в режиме `int8` и повторяет расшифровку. Чтобы снизить расход памяти, можно выбрать `small`, `base` или `tiny`.

## Настройки

| Переменная | Значение в шаблоне | Назначение |
| --- | --- | --- |
| `BOT_TOKEN` | Пусто | Токен от BotFather |
| `WHISPER_MODEL` | `small` | Модель Faster-Whisper |
| `WHISPER_DEVICE` | `cpu` | Устройство `cpu` или `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Тип вычислений, обычно `int8` для CPU и `float16` для GPU |
| `WHISPER_LANGUAGE` | `ru` | Код языка, например `ru` или `en`, либо `auto` |
| `ALLOWED_USERS` | Пусто | Числовые ID Telegram через запятую. Пустой список открывает доступ всем |

Скачанные записи временно хранятся в `temp/` и удаляются после обработки. Для проверки настроек и формирования TXT запустите `python -m unittest discover -s tests` из активированного окружения. Тесты обходятся без реального токена и скачивания модели.
