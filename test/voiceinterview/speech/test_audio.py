import io
import wave

import pytest

from modules.voiceinterview.speech.audio import InvalidAudioError, pcm_to_wav, split_sentences, validate_pcm16


def test_validate_pcm16_rejects_empty_odd_and_oversized_frames() -> None:
    with pytest.raises(InvalidAudioError):
        validate_pcm16(b"")
    with pytest.raises(InvalidAudioError):
        validate_pcm16(b"\x00")
    with pytest.raises(InvalidAudioError):
        validate_pcm16(b"\x00\x00" * 3, max_bytes=4)
    assert validate_pcm16(b"\x00\x00") == b"\x00\x00"


def test_pcm_to_wav_writes_expected_24k_mono_header() -> None:
    pcm = b"\x01\x00\xff\xff"
    encoded = pcm_to_wav(pcm)
    assert encoded.startswith(b"RIFF")
    with wave.open(io.BytesIO(encoded), "rb") as wav:
        assert wav.getframerate() == 24_000
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.readframes(2) == pcm


def test_split_sentences_preserves_order_and_limits_long_units() -> None:
    result = split_sentences("第一句。第二句！" + "很长" * 100, max_chars=40)
    assert result[:2] == ["第一句。", "第二句！"]
    assert all(len(item) <= 40 for item in result)
    assert "".join(result).replace(" ", "") == ("第一句。第二句！" + "很长" * 100)
