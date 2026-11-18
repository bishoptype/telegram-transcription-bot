import html
import datetime
from typing import List, Dict, Any


def format_timestamp(seconds: float) -> str:
    """Преобразует секунды в формат MM:SS или HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def split_text_into_chunks(text: str, max_chunk_size: int = 3800) -> List[str]:
    """
    Разбивает длинный текст на части, не превышающие max_chunk_size.
    Форматирует каждую часть в тег <pre> для копирования в один клик.
    """
    if max_chunk_size < 1:
        raise ValueError("max_chunk_size должен быть положительным.")

    text = text.strip()
    chunks = []
    while len(text) > max_chunk_size:
        split_at = text.rfind("\n", 0, max_chunk_size + 1)
        if split_at < 1:
            split_at = text.rfind(" ", 0, max_chunk_size + 1)
        if split_at < 1:
            split_at = max_chunk_size
        chunks.append(text[:split_at].rstrip())
        text = text[split_at:].lstrip()

    if text:
        chunks.append(text)

    total_chunks = len(chunks)
    formatted_chunks = []
    for i, chunk in enumerate(chunks, 1):
        escaped_text = html.escape(chunk)
        if total_chunks > 1:
            formatted_chunks.append(
                f"📄 <b>Часть {i}/{total_chunks}:</b> <i>(нажмите на текст ниже для копирования)</i>\n\n"
                f"<pre>{escaped_text}</pre>"
            )
        else:
            formatted_chunks.append(f"<pre>{escaped_text}</pre>")

    return formatted_chunks


def create_transcription_txt(
    filename: str,
    duration: float,
    language: str,
    full_text: str,
    segments: List[Dict[str, Any]]
) -> str:
    """
    Формирует полный отчет в формате TXT с чистым текстом и таймкодами.
    """
    now_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    dur_str = format_timestamp(duration)

    lines = [
        "=" * 70,
        "                     РАСШИФРОВКА АУДИО / ВИДЕО",
        "=" * 70,
        f"Файл:           {filename}",
        f"Дата:           {now_str}",
        f"Длительность:   {dur_str} ({duration:.1f} сек.)",
        f"Язык:           {language}",
        "=" * 70,
        "",
        "--- ПОЛНЫЙ ТЕКСТ ---",
        "",
        full_text,
        "",
        "=" * 70,
        "--- ТЕКСТ С ТАЙМКОДАМИ ---",
        "=" * 70,
        ""
    ]

    for s in segments:
        t_start = format_timestamp(s["start"])
        t_end = format_timestamp(s["end"])
        text = s["text"].strip()
        lines.append(f"[{t_start} -> {t_end}] {text}")

    lines.append("")
    return "\n".join(lines)
