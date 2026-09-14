"""Local, offline speech-to-text for voice input to Benfieg.

The browser records the microphone as a 16 kHz mono WAV and uploads the bytes.
We decode the WAV with the Python standard library (no ffmpeg dependency) into a
float32 numpy array in [-1, 1] and hand it to a locally cached openai-whisper
model. Everything runs on the machine — no API key, nothing leaves the host.

The model is heavy to load, so it is cached process-wide and only loaded on the
first transcription request.
"""
from __future__ import annotations

import io
import logging
import wave

import numpy as np

from app.core.config import settings

logger = logging.getLogger("digitaltwin.transcribe")

# openai-whisper expects mono audio at this sample rate.
WHISPER_SR = 16000

_model = None  # process-wide cache; loaded lazily on first use.


class TranscriptionUnavailable(RuntimeError):
    """Raised when voice input is disabled or the whisper package is missing."""


def _load_model():
    global _model
    if _model is not None:
        return _model
    name = (settings.WHISPER_MODEL or "").strip()
    if not name:
        raise TranscriptionUnavailable("Voice input is disabled (WHISPER_MODEL empty).")
    try:
        import whisper  # openai-whisper; imported lazily so it's optional.
    except ImportError as e:  # pragma: no cover - depends on install
        raise TranscriptionUnavailable(
            "The 'openai-whisper' package is not installed."
        ) from e
    logger.info("Loading whisper model %r (first use)…", name)
    _model = whisper.load_model(name)
    return _model


def _wav_to_float32(data: bytes) -> np.ndarray:
    """Decode a PCM WAV into a mono float32 array at 16 kHz, using only stdlib.

    Handles 16-bit PCM (what the browser records). Multi-channel audio is
    down-mixed to mono; other sample rates are linearly resampled to 16 kHz.
    """
    with wave.open(io.BytesIO(data), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if width != 2:
        raise ValueError(f"Unsupported sample width {width * 8}-bit; expected 16-bit PCM.")

    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    if rate != WHISPER_SR and audio.size:
        # Linear resample to 16 kHz (adequate for speech recognition).
        n_out = int(round(audio.size * WHISPER_SR / rate))
        if n_out > 0:
            x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
            x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
            audio = np.interp(x_new, x_old, audio).astype(np.float32)

    return np.ascontiguousarray(audio, dtype=np.float32)


def transcribe_wav(data: bytes) -> dict:
    """Transcribe WAV bytes to text. Returns {text, language, model}."""
    model = _load_model()
    audio = _wav_to_float32(data)
    if audio.size == 0:
        return {"text": "", "language": None, "model": settings.WHISPER_MODEL}
    # fp16 is only useful on GPU; force fp32 for CPU correctness/portability.
    result = model.transcribe(audio, fp16=False)
    return {
        "text": (result.get("text") or "").strip(),
        "language": result.get("language"),
        "model": settings.WHISPER_MODEL,
    }
