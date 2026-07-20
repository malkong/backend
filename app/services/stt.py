"""Faster-Whisper 기반 STT (영상/오디오 파일 -> speech_text).

로컬 CPU 환경 기준.
"""
import os
import subprocess
import tempfile

from dotenv import load_dotenv
from faster_whisper import WhisperModel

load_dotenv()

MODEL_SIZE = os.getenv("STT_MODEL_SIZE", "base")
DEVICE = os.getenv("STT_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "int8")

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        if DEVICE != "cpu":
            raise RuntimeError(
                f"STT_DEVICE='{DEVICE}'는 지원하지 않습니다. 이 프로젝트는 CPU 전용입니다 (STT_DEVICE=cpu)."
            )
        _model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    return _model


def _extract_audio(input_path: str) -> str:
    """ffmpeg으로 입력 파일(영상/오디오 무관)을 16kHz mono wav로 정규화."""
    fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-ac", "1", "-ar", "16000", audio_path],
        check=True,
        capture_output=True,
    )
    return audio_path


def transcribe(file_path: str) -> dict:
    """영상/오디오 파일을 받아 speech_text/language/duration_sec을 반환한다."""
    audio_path = _extract_audio(file_path)
    try:
        model = _get_model()
        segments, info = model.transcribe(audio_path, language="ko")
        text = "".join(segment.text for segment in segments).strip()
        return {
            "speech_text": text,
            "language": info.language,
            "duration_sec": round(info.duration, 2),
        }
    finally:
        os.remove(audio_path)
