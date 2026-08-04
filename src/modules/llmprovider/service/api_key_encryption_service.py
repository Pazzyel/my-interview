import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode


class ApiKeyEncryptionService:
    def __init__(self, master_key: str | None = None) -> None:
        self._master_key = master_key

    def validate_ready(self) -> None:
        self._key_bytes()

    def encrypt(self, plaintext: str) -> tuple[str, str]:
        if not plaintext:
            raise BusinessException(ErrorCode.LLM_PROVIDER_CONFIG_ERROR, "API Key 不能为空")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key_bytes()).encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(ciphertext).decode("ascii"), base64.b64encode(nonce).decode("ascii")

    def decrypt(self, ciphertext: str, nonce: str) -> str:
        try:
            value = AESGCM(self._key_bytes()).decrypt(
                base64.b64decode(nonce, validate=True),
                base64.b64decode(ciphertext, validate=True),
                None,
            )
            return value.decode("utf-8")
        except (InvalidTag, ValueError, UnicodeDecodeError) as error:
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CRYPTO_ERROR,
                "Provider API Key 解密失败，请检查 LLM_PROVIDER_ENCRYPTION_KEY",
            ) from error

    @staticmethod
    def mask(value: str) -> str:
        return "***" if len(value) <= 6 else f"{value[:3]}***{value[-3:]}"

    def _key_bytes(self) -> bytes:
        raw = self._master_key if self._master_key is not None else app_config.llm_provider_encryption_key
        if raw is None or not raw.strip():
            raise BusinessException(
                ErrorCode.LLM_PROVIDER_CRYPTO_ERROR,
                "缺少 LLM_PROVIDER_ENCRYPTION_KEY，应用拒绝启动",
            )
        raw = raw.strip()
        try:
            decoded = base64.b64decode(raw, validate=True)
            if len(decoded) == 32:
                return decoded
        except ValueError:
            pass
        return hashlib.sha256(raw.encode("utf-8")).digest()
