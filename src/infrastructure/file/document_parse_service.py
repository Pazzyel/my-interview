import asyncio
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
import logging

from fastapi import UploadFile
from pypdf import PdfReader
from unstructured.partition.auto import partition

from common.config import app_config

logger = logging.getLogger(__name__)


class DocumentParseError(RuntimeError):
    """Raised when a document cannot be converted to usable text."""


def parse_func(file_bytes: BytesIO, file__name: str):
    # unstructured's PDF partitioner imports the full local-inference stack
    # even for the fast strategy. Text resumes only need pypdf, which is
    # already a direct project dependency and keeps the runtime image small.
    if file__name.lower().endswith(".pdf"):
        reader = PdfReader(file_bytes)
        return [text for page in reader.pages if (text := page.extract_text())]

    return partition(metadata_filename=file__name, file=file_bytes, strategy="fast")


class DocumentParseService:
    async def parse_content(self, file: UploadFile) -> str:
        """Parse document text using unstructured"""
        # 预检查文件大小（这一步已经在ResumeUploadService做好）

        # 读取文件内容
        content: bytes = await file.read()
        await file.seek(0)
        if (file.filename is None) or (file.filename.strip() == ""):
            file_name = "unknown"
        else:
            file_name = file.filename
        return await self.parse_content_from_bytes(content, file_name)

    async def parse_content_from_bytes(self, content: bytes, file_name: str) -> str:
        file_like = BytesIO(content)

        # 获取时间循环异步执行partition
        loop = asyncio.get_running_loop()
        process_executor = ProcessPoolExecutor(max_workers=4)  # CPU密集型任务用ProcessPoolExecutor
        try:
            # 2. 在进程池中执行，设置 60 秒超时防止死锁或恶意文件
            elements = await asyncio.wait_for(
                loop.run_in_executor(process_executor, parse_func, file_like, file_name),
                timeout=app_config.MAX_PARSE_TIME
            )

            text_content = "\n\n".join([str(el) for el in elements])
            return text_content

        except asyncio.TimeoutError:
            message = f"Parsing document {file_name} timed out after {app_config.MAX_PARSE_TIME} seconds"
            logger.warning(message)
            raise DocumentParseError(message)
        except Exception as e:
            message = f"Error parsing document {file_name}: {str(e)}"
            logger.error(message, exc_info=True)
            raise DocumentParseError(message) from e
        finally:
            process_executor.shutdown(wait=False, cancel_futures=True)

    def detect_content_type(self, file: UploadFile) -> str:
        return file.content_type or "application/octet-stream"
