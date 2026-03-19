import asyncio
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO

from fastapi import UploadFile
from unstructured.partition.auto import partition

from common.config import app_config


class DocumentParseService:
    async def parse_content(self, file: UploadFile) -> str:
        """Parse document text using unstructured"""
        # 预检查文件大小（这一步已经在ResumeUploadService做好）

        # 读取文件内容
        content: bytes = await file.read()
        await file.seek(0)
        return await self.parse_content_from_bytes(content, file.filename)

    async def parse_content_from_bytes(self, content: bytes, file_name: str) -> str:
        file_like = BytesIO(content)

        # 解析函数的lambda包装函数，这里我们指定模式为fast
        def parse_func(file_bytes: BytesIO, file__name: str):
            return partition(metadata_filename=file__name, file=file_bytes, strategy="fast")

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
            return "解析超时，文件可能过大或结构过于复杂。"
        except Exception as e:
            # Fallback if parsing fails
            return f"Error parsing content for {file_name}: {str(e)}"

    def detect_content_type(self, file: UploadFile) -> str:
        return file.content_type or "application/octet-stream"
