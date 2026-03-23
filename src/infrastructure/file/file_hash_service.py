import hashlib

from fastapi import UploadFile


class FileHashService:
    async def calculate_hash_file(self, file: UploadFile) -> str:
        content: bytes = await file.read()
        await file.seek(0)
        return self.calculate_hash_bytes(content)


    def calculate_hash_bytes(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()