from typing import List

from fastapi import UploadFile

from common.config import app_config
from common.exceptions import BusinessException, ErrorCode


class FileValidationService:
    async def validate_file(self, file: UploadFile, max_size: int, file_type_desc: str) -> int:
        """保证文件大小合法，非法时抛出异常，合法时返回文件的大小"""
        if not file or (file.size and file.size == 0):
            raise BusinessException(ErrorCode.VALIDATION_ERROR, f"{file_type_desc}文件不能为空")
        file_size: int | None = file.size
        if not file.size:
            file_chunk = await file.read(app_config.max_file_size_bytes + 1)
            await file.seek(0)
            file_size = len(file_chunk)

        # In actual implementation, check file.size
        # Fast API UploadFile size can be checked after reading or via headers
        if file_size > max_size:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, f"{file_type_desc}文件大小超过限制")
        return file_size

    def validate_content_type_by_list(self, content_type: str, allowed_types: List[str], error_msg: str) -> None:
        if content_type not in allowed_types:
            raise BusinessException(ErrorCode.VALIDATION_ERROR, error_msg)
