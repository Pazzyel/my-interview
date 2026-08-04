from __future__ import annotations

import io
import re
import wave


class InvalidAudioError(ValueError):
    """Raised when a browser audio frame violates the PCM wire contract."""


def validate_pcm16(data: bytes, *, max_bytes: int = 256 * 1024) -> bytes:
    """Validate signed 16-bit little-endian mono PCM.

    Sample rate and channel count are out-of-band properties; alignment and the
    WebSocket frame limit are the properties that can be verified from bytes.
    """
    if not data:
        raise InvalidAudioError("audio data is empty")
    if len(data) > max_bytes:
        raise InvalidAudioError(f"audio frame exceeds {max_bytes} bytes")
    if len(data) % 2:
        raise InvalidAudioError("PCM16 audio must contain an even number of bytes")
    return data


def pcm_to_wav(
    pcm: bytes,
    *,
    sample_rate: int = 24_000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM in a standards-compliant RIFF/WAVE container."""
    if sample_width <= 0 or channels <= 0 or sample_rate <= 0:
        raise ValueError("invalid WAV format")
    if len(pcm) % (sample_width * channels):
        raise InvalidAudioError("PCM data is not aligned to the requested WAV format")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|(?<=[.])\s+(?=[A-Z0-9\u4e00-\u9fff])")


def split_sentences(text: str, *, max_chars: int = 180) -> list[str]:
    """Split LLM output into short, ordered TTS units without losing text."""
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return []
    rough = [part.strip() for part in _SENTENCE_BOUNDARY.split(normalized) if part.strip()]
    result: list[str] = []
    for sentence in rough:
        while len(sentence) > max_chars:
            cut = max(sentence.rfind(mark, 0, max_chars + 1) for mark in ("，", ",", "、", " "))
            if cut < max_chars // 3:
                cut = max_chars
            result.append(sentence[: cut + (cut != max_chars)].strip())
            sentence = sentence[cut + (cut != max_chars) :].strip()
        if sentence:
            result.append(sentence)
    return result
