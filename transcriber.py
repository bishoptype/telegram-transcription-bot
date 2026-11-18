import asyncio
import logging
import os
import sys
import time
from importlib.util import find_spec
from pathlib import Path
from threading import Lock
from typing import Dict, Any, Optional

import config


def setup_cuda_dlls():
    """Настраивает поиск DLL CUDA в Windows для CTranslate2."""
    if sys.platform != "win32" or config.WHISPER_DEVICE != "cuda":
        return []

    directories = []
    torch_spec = find_spec("torch")
    if torch_spec and torch_spec.origin:
        directories.append(Path(torch_spec.origin).parent / "lib")
    for entry in sys.path:
        if Path(entry).name == "site-packages":
            nvidia = Path(entry) / "nvidia"
            directories.extend([nvidia / "cublas" / "bin", nvidia / "cudnn" / "bin"])

    handles = []
    for directory in directories:
        if directory.is_dir():
            handles.append(os.add_dll_directory(str(directory)))
            os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
    return handles


_cuda_dll_handles = setup_cuda_dlls()
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


class WhisperService:
    _instance: Optional["WhisperService"] = None

    def __init__(self):
        self._model_lock = Lock()
        self.device = config.WHISPER_DEVICE
        self.compute_type = config.WHISPER_COMPUTE_TYPE
        self.model_name = config.WHISPER_MODEL
        self._load_model()

    @classmethod
    def get_instance(cls) -> "WhisperService":
        if cls._instance is None:
            cls._instance = WhisperService()
        return cls._instance

    def _load_model(self):
        """Загружает модель WhisperModel с поддержкой GPU CUDA и fallback на CPU."""
        if self.device == "cuda":
            try:
                logger.info(f"[*] Загрузка Faster-Whisper '{self.model_name}' на GPU (CUDA, {self.compute_type})...")
                self.model = WhisperModel(
                    self.model_name,
                    device="cuda",
                    compute_type=self.compute_type
                )
                logger.info(f"✅ Модель '{self.model_name}' успешно загружена на GPU CUDA!")
                return
            except Exception as e:
                logger.warning(f"⚠️ Ошибка инициализации на GPU ({e}). Переключаюсь на CPU (int8)...")
        self._load_cpu_model("int8" if self.device == "cuda" else self.compute_type)

    def _load_cpu_model(self, compute_type: str):
        logger.info(f"[*] Загрузка Faster-Whisper '{self.model_name}' на CPU ({compute_type})...")
        self.model = WhisperModel(self.model_name, device="cpu", compute_type=compute_type)
        self.device = "cpu"
        self.compute_type = compute_type
        logger.info(f"✅ Модель '{self.model_name}' загружена на CPU.")

    def transcribe_sync(self, file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Транскрибирует файл. При сбое CUDA повторяет обработку на CPU."""
        with self._model_lock:
            model, device = self.model, self.device

        try:
            return self._transcribe(model, file_path, language)
        except RuntimeError as error:
            if device != "cuda" or not any(
                library in str(error).lower() for library in ("cuda", "cublas", "cudnn")
            ):
                raise
            # CUDA может загрузить библиотеки только при обработке первого файла.
            with self._model_lock:
                if self.model is model:
                    logger.warning("Сбой CUDA (%s). Переключаюсь на CPU (int8)...", error)
                    self._load_cpu_model("int8")
                model = self.model

        return self._transcribe(model, file_path, language)

    def _transcribe(
        self, model: WhisperModel, file_path: str, language: Optional[str]
    ) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Файл не найден: {file_path}")

        file_abs = os.path.abspath(file_path)
        lang_to_use = language or config.WHISPER_LANGUAGE
        lang_param = None if lang_to_use.lower() in ["auto", "none"] else lang_to_use

        logger.info(f"🎵 Начало расшифровки: {os.path.basename(file_abs)} (язык: {lang_param or 'auto'})")
        start_time = time.time()

        segments_gen, info = model.transcribe(
            file_abs,
            language=lang_param,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False
        )

        segments_list = []
        full_text_pieces = []

        for seg in segments_gen:
            text = seg.text.strip()
            if text:
                segments_list.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": text
                })
                full_text_pieces.append(text)

        elapsed = time.time() - start_time
        full_text = " ".join(full_text_pieces).strip()
        speedup = info.duration / elapsed if elapsed > 0 else 0

        logger.info(
            f"✨ Расшифровка завершена за {elapsed:.2f} сек. "
            f"Аудио: {info.duration:.1f} сек. ({speedup:.1f}x реального времени)"
        )

        return {
            "file_name": os.path.basename(file_abs),
            "full_text": full_text,
            "duration": info.duration,
            "language": info.language,
            "language_probability": info.language_probability,
            "segments": segments_list,
            "elapsed_time": elapsed
        }

    async def transcribe_async(self, file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Асинхронная обертка для выполнения в пуле потоков без блокировки event loop.
        """
        return await asyncio.to_thread(self.transcribe_sync, file_path, language)
