# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""R2 / S3-compatible object storage helpers for worker downloads and uploads."""

import os
import tempfile
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


# Paths are restricted to temp directories and the current working directory to
# prevent storage keys or caller-supplied local paths from becoming path-traversal
# vectors (e.g. storage_key = "../../../etc/passwd").
_ALLOWED_ROOTS = {
    os.path.abspath(tempfile.gettempdir()),
    os.path.abspath(os.getcwd()),
}


def _get_s3_client():
    endpoint = os.environ.get("R2_ENDPOINT", "")
    is_local = any(
        h in endpoint.lower()
        for h in ("localhost", "127.0.0.1", "minio", ":9000")
    )

    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name="auto",
        endpoint_url=endpoint or None,
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
        config=Config(
            s3={"addressing_style": "path" if is_local else "auto"},
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "adaptive"},
        ),
    )


def _bucket() -> str:
    return os.environ.get("R2_BUCKET_NAME", "ai-video-editor")


def _safe_local_path(local_path: str) -> str:
    """Resolve local_path, ensure it is absolute and does not escape allowed roots."""
    abs_path = os.path.abspath(local_path)
    norm_path = os.path.normpath(abs_path)
    if ".." in norm_path.split(os.sep):
        raise ValueError(f"Refusing unsafe local path: {local_path}")
    for root in _ALLOWED_ROOTS:
        if norm_path == root or norm_path.startswith(root + os.sep):
            return abs_path
    raise ValueError(f"Local path outside allowed roots: {local_path}")


def download_asset(storage_key: str, local_path: Optional[str] = None) -> str:
    """Download an asset from R2 to a local path.

    Args:
        storage_key: The S3/R2 object key.
        local_path: Where to save the file. If None, uses a unique temp file.

    Returns:
        Absolute path to the downloaded file.
    """
    s3 = _get_s3_client()
    bucket = _bucket()

    if local_path is None:
        ext = os.path.splitext(storage_key)[1] or ".tmp"
        # Use a unique temp file to avoid collisions between concurrent workers.
        with tempfile.NamedTemporaryFile(delete=False, prefix="ave_", suffix=ext) as tmp:
            local_path = tmp.name

    local_path = _safe_local_path(local_path)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:
        s3.download_file(bucket, storage_key, local_path)
    except ClientError as e:
        # Clean up the partial/empty file on failure so it does not leak.
        try:
            os.remove(local_path)
        except OSError:
            pass
        raise RuntimeError(f"Failed to download {storage_key}: {e}") from e

    return local_path


def upload_file(local_path: str, storage_key: str, content_type: Optional[str] = None) -> str:
    """Upload a local file to R2.

    Args:
        local_path: Path to the local file.
        storage_key: Destination S3/R2 object key.
        content_type: Optional MIME type.

    Returns:
        The storage key.
    """
    s3 = _get_s3_client()
    bucket = _bucket()

    local_path = _safe_local_path(local_path)

    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        s3.upload_file(local_path, bucket, storage_key, ExtraArgs=extra_args)
    except ClientError as e:
        raise RuntimeError(f"Failed to upload {local_path} to {storage_key}: {e}") from e

    return storage_key


def delete_asset(storage_key: str) -> None:
    """Delete an asset from R2."""
    s3 = _get_s3_client()
    bucket = _bucket()
    try:
        s3.delete_object(Bucket=bucket, Key=storage_key)
    except ClientError as e:
        raise RuntimeError(f"Failed to delete {storage_key}: {e}") from e


def get_presigned_download_url(storage_key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for downloading an asset."""
    s3 = _get_s3_client()
    bucket = _bucket()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )
