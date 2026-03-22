import asyncio
import logging
import re
import time
import uuid
from typing import Any

import aioboto3
from botocore.exceptions import ClientError
from fastapi import UploadFile
from pypinyin import lazy_pinyin

from common.config import app_config


class FileStorageService:
    """
    文件存储服务 (RustFS/S3)

    Service for handling file operations with RustFS (S3 compatible).
    """
    def __init__(self):
        self.s3_session: aioboto3.Session = aioboto3.Session()
        self.bucket_name: str = app_config.rustfs_bucket_name
        self.bucket_checked: bool = False
        self.bucket_check_lock: asyncio.Lock = asyncio.Lock()

    def _create_s3_client(self) -> Any:
        return self.s3_session.client(
            "s3",
            endpoint_url=app_config.rustfs_endpoint_url,
            aws_access_key_id=app_config.rustfs_access_key,
            aws_secret_access_key=app_config.rustfs_secret_key,
            region_name=app_config.rustfs_region_name,
        )

    async def ensure_bucket_exists(self) -> None:
        """
        确保 bucket 存在，不存在则自动创建。

        Ensure the configured bucket exists in RustFS.
        If it does not exist, create it automatically.
        """
        if self.bucket_checked:
            return

        async with self.bucket_check_lock:
            if self.bucket_checked:
                return

            try:
                async with self._create_s3_client() as s3_client:
                    await s3_client.head_bucket(Bucket=self.bucket_name)
            except ClientError as e:
                error_code: str = e.response.get("Error", {}).get("Code", "")
                if error_code == "404" or error_code == "NoSuchBucket":
                    logging.info("Bucket '%s' 不存在，正在创建...", self.bucket_name)
                    try:
                        async with self._create_s3_client() as s3_client:
                            await s3_client.create_bucket(Bucket=self.bucket_name)
                        logging.info("Bucket '%s' 创建成功", self.bucket_name)
                    except ClientError as create_err:
                        raise Exception(f"Failed to create bucket '{self.bucket_name}': {str(create_err)}")
                else:
                    raise Exception(f"Failed to check bucket '{self.bucket_name}': {str(e)}")

            self.bucket_checked = True

    async def upload_file_to_rustfs(self, file: UploadFile, prefix: str) -> str:
        """
        上传文件到RustFS，返回为其生成的文件key

        Upload resume to RustFS, returns fileKey
        """
        file_key = self.generate_file_key(file.filename or "unknown", prefix)
        await self.ensure_bucket_exists()
        
        try:
            file_content = await file.read()
            async with self._create_s3_client() as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                    Body=file_content,
                    ContentType=file.content_type
                )
        except ClientError as e:
            raise Exception(f"Failed to upload file to RustFS: {str(e)}")
        finally:
            await file.seek(0)
            
        return file_key

    async def upload_resume(self, file: UploadFile) -> str:
        """上传简历文件"""
        return await self.upload_file_to_rustfs(file, "resumes")

    async def upload_knowledgebase(self, file: UploadFile) -> str:
        """上传知识库文件"""
        return await self.upload_file_to_rustfs(file, "knowledgebase")

    async def get_file_url(self, file_key: str) -> str:
        """
        获取RustFS文件的预签名URL

        Get RustFS presigned URL
        """
        await self.ensure_bucket_exists()
        try:
            async with self._create_s3_client() as s3_client:
                url: str = await s3_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket_name,
                        'Key': file_key
                    },
                    ExpiresIn=3600
                )
                return url
        except ClientError as e:
            raise Exception(f"Failed to generate URL for file: {str(e)}")

    async def download_file(self, file_key: str) -> bytes:
        """
        从RustFS下载文件内容。

        Download file content from RustFS by key.
        """
        await self.ensure_bucket_exists()
        try:
            async with self._create_s3_client() as s3_client:
                response: dict[str, Any] = await s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                )
                return await response["Body"].read()
        except ClientError as e:
            raise Exception(f"Failed to download file from RustFS: {str(e)}")

    async def file_exists(self, file_key: str) -> bool:
        """
        根据 file_key 检查文件是否存在。

        Check whether a file exists in RustFS by its key.
        Uses HEAD request to avoid downloading the file content.
        """
        await self.ensure_bucket_exists()
        try:
            async with self._create_s3_client() as s3_client:
                await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                )
            return True
        except ClientError as e:
            error_code: str = e.response.get("Error", {}).get("Code", "")
            if error_code == "404" or error_code == "NoSuchKey":
                return False
            raise Exception(f"Failed to check file existence in RustFS: {str(e)}")

    async def get_file_size(self, file_key: str) -> int:
        """
        根据 file_key 获取文件大小（字节）。

        Get file size in bytes from RustFS by its key.
        Returns ContentLength from HEAD response.
        """
        await self.ensure_bucket_exists()
        try:
            async with self._create_s3_client() as s3_client:
                response: dict[str, Any] = await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                )
            return response["ContentLength"]
        except ClientError as e:
            raise Exception(f"Failed to get file size from RustFS: {str(e)}")

    async def delete_file(self, file_key: str) -> None:
        """
        根据 file_key 删除文件。

        Delete a file from RustFS by its key.

        """
        if not file_key or len(file_key) == 0:
            logging.debug("文件键为空，跳过删除")
            return

        if not await self.file_exists(file_key):
            logging.debug("文件不存在，跳过删除")
            return

        await self.ensure_bucket_exists()
        try:
            async with self._create_s3_client() as s3_client:
                await s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=file_key,
                )
            logging.debug("文件删除成功")
        except ClientError as e:
            raise Exception(f"Failed to delete file from RustFS: {str(e)}")

    def generate_file_key(self, original_filename: str, prefix: str = "") -> str:
        """获取文件系统的key"""
        date_path: str = time.strftime("%Y/%m/%d", time.localtime())
        random_uuid: str = str(uuid.uuid4().hex)[0:8]
        safe_name: str = self.sanitize_filename(original_filename)
        return f"{prefix}/{date_path}/{random_uuid}_{safe_name}"

    def sanitize_filename(self, filename: str) -> str:
        """处理名字里的特殊字符"""
        if not filename or len(filename) == 0:
            return "unknow"
        return self.convert_to_pinyin(filename)

    def convert_to_pinyin(self, filename: str) -> str:
        """把文件名汉字转换成拼音，特殊字符替换为_"""
        # 1. 允许的字符
        allowed_pattern = r"[a-zA-Z0-9.\-_]"

        result = []

        # 2. 逐字符扫描或利用 pypinyin 的特性
        for char in filename:
            # 判断是否为汉字 (Unicode 编码区间)
            if '\u4e00' <= char <= '\u9fa5':
                # 是汉字：转拼音并首字母大写
                py = lazy_pinyin(char)[0]
                result.append(py.capitalize())

            # 判断是否为允许的非汉字字符
            elif re.match(allowed_pattern, char):
                # 保持原样
                result.append(char)

            else:
                # 其他特殊字符（空格、@、# 等）替换为下划线
                result.append("_")

        return "".join(result)