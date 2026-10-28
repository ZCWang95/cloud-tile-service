import logging
import mimetypes
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Tiles for a given date never change once written.
TILE_CACHE_CONTROL = "public, max-age=604800"


class S3Storage:
    def __init__(self, bucket: str, client=None, max_pool_connections: int = 64):
        self.bucket = bucket
        self.client = client or boto3.client(
            "s3", config=Config(max_pool_connections=max_pool_connections, retries={"mode": "adaptive"})
        )

    def read_text(self, key: str) -> Optional[str]:
        """Return the object's text, or None if it does not exist."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        return response["Body"].read().decode("utf-8")

    def write_text(self, key: str, text: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=text.encode("utf-8"), ContentType="text/plain; charset=utf-8"
        )

    def upload_dir(self, local_dir: str, prefix: str, workers: int = 32) -> int:
        """Upload every file under local_dir to s3://bucket/prefix/<relative path>."""
        root = Path(local_dir)
        files = [p for p in root.rglob("*") if p.is_file()]
        prefix = prefix.strip("/")

        def upload(path: Path):
            key = f"{prefix}/{path.relative_to(root).as_posix()}"
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.client.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type, "CacheControl": TILE_CACHE_CONTROL},
            )

        logger.info("Uploading %d files to s3://%s/%s", len(files), self.bucket, prefix)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            # list() re-raises the first upload error, if any.
            list(pool.map(upload, files))
        return len(files)


def file_count(directory: str) -> int:
    return sum(len(files) for _, _, files in os.walk(directory))
