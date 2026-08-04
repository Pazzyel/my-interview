"""Speech provider abstractions and DashScope implementations."""

from .audio import pcm_to_wav, split_sentences, validate_pcm16
from .protocols import AsrCallbacks, AsrProvider, AsrStream, TtsProvider

__all__ = [
    "AsrCallbacks",
    "AsrProvider",
    "AsrStream",
    "TtsProvider",
    "pcm_to_wav",
    "split_sentences",
    "validate_pcm16",
]
