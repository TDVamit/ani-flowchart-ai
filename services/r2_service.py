"""
R2 Storage Service — all file storage goes through Cloudflare R2.
R2 is S3-compatible, so we use boto3 pointed at the R2 endpoint.
No files are written to local disk.

All public methods are async — boto3 is synchronous so each call is
dispatched to the default thread-pool executor via asyncio.to_thread(),
keeping the event loop free.
"""

import asyncio
import boto3
import uuid
import os
from botocore.client import Config
from botocore.exceptions import ClientError
from config import settings


class R2Service:

    def __init__(self):
        # boto3 client is not coroutine-safe; we create one per service
        # instance (i.e. per request) and run every call in a thread.
        self._client = boto3.client(
            service_name="s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",  # required by SDK but ignored by R2
        )
        self.bucket = settings.r2_bucket_name

    # ── public async interface ────────────────────────────────────────────────

    async def upload_bytes(
        self,
        file_bytes: bytes,
        filename: str,
        project_id: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes to R2. Returns the R2 object key."""
        ext = os.path.splitext(filename)[1].lower()
        file_id = str(uuid.uuid4())
        key = f"{project_id}/{file_id}{ext}"
        await asyncio.to_thread(self._put_object, key, file_bytes, content_type)
        return key

    async def download_file(self, key: str) -> bytes:
        """Download a file from R2 as bytes."""
        return await asyncio.to_thread(self._get_object, key)

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a temporary presigned GET URL."""
        return await asyncio.to_thread(self._presigned_url, key, expires_in)

    async def delete_file(self, key: str) -> None:
        await asyncio.to_thread(self._delete_object, key)

    async def file_exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._head_object, key)

    # ── sync helpers (run inside thread pool) ────────────────────────────────

    def _put_object(self, key: str, body: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )

    def _get_object(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def _presigned_url(self, key: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def _delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def _head_object(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
