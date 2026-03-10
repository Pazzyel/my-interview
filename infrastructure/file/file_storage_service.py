from fastapi import UploadFile
import uuid
import boto3
from botocore.exceptions import ClientError
from common.config import app_config

class FileStorageService:
    """
    文件存储服务 (RustFS/S3)

    Service for handling file operations with RustFS (S3 compatible).
    """
    def __init__(self):
        # 根据配置获取RustFS的客户端
        self.s3_client = boto3.client(
            's3',
            endpoint_url=app_config.rustfs_endpoint_url,
            aws_access_key_id=app_config.rustfs_access_key,
            aws_secret_access_key=app_config.rustfs_secret_key,
            region_name=app_config.rustfs_region_name
        )
        self.bucket_name = app_config.rustfs_bucket_name

    async def upload_file_to_rustfs(self, file: UploadFile) -> str:
        """
        上传文件到RustFS，返回为其生成的文件key

        Upload resume to RustFS, returns fileKey
        """
        file_key = f"resume_{uuid.uuid4().hex}"
        
        try:
            file_content = await file.read()
            self.s3_client.put_object(
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

    def get_file_url(self, file_key: str) -> str:
        """
        获取RustFS文件的预签名URL

        Get RustFS presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
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

    def download_file(self, file_key: str) -> bytes:
        """
        从RustFS下载文件内容。

        Download file content from RustFS by key.
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=file_key,
            )
            return response["Body"].read()
        except ClientError as e:
            raise Exception(f"Failed to download file from RustFS: {str(e)}")
