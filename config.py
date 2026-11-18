import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем конфигурацию из .env
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не указана в файле .env!")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3").strip()
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda").strip()
if WHISPER_DEVICE not in {"cpu", "cuda"}:
    raise ValueError("WHISPER_DEVICE должен быть cpu или cuda.")
_default_compute_type = "int8" if WHISPER_DEVICE == "cpu" else "float16"
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", _default_compute_type).strip()
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "ru").strip()

# Список разрешенных пользователей (ID через запятую)
_allowed_raw = os.getenv("ALLOWED_USERS", "").strip()
ALLOWED_USERS = set()
if _allowed_raw:
    for uid in _allowed_raw.split(","):
        uid_clean = uid.strip()
        if not uid_clean:
            continue
        if not uid_clean.isascii() or not uid_clean.isdecimal() or int(uid_clean) == 0:
            raise ValueError("ALLOWED_USERS должен содержать числовые Telegram ID через запятую.")
        ALLOWED_USERS.add(int(uid_clean))
    if not ALLOWED_USERS:
        raise ValueError("ALLOWED_USERS не содержит ни одного Telegram ID.")

# Директория для временных файлов медиа
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

def is_user_allowed(user_id: int) -> bool:
    """Проверяет, разрешен ли доступ пользователю."""
    if not ALLOWED_USERS:
        return True
    return user_id in ALLOWED_USERS
