# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Pluggable object storage backend.

Supports a local filesystem backend (default) and an R2/S3-compatible backend.
The local backend is rooted at ``E:\\ai-video-editor-storage`` by default and
uses atomic writes (temp file + rename) to avoid partial reads.

Legacy module-level helpers (:func:`download_asset`, :func:`upload_file`, etc.)
remain as thin wrappers around :func:`get_storage` for backward compatibility.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Protocol, Union, runtime_checkable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


_DEFAULT_LOCAL_ROOT = r"E:\ai-video-editor-storage"


@runtime_checkable
class StorageBackend(Protocol):
    """Abstract storage interface used across Python workers."""

    def get(self, key: str, local_path: str) -> str:
        """Download ``key`` from storage to ``local_path``.

        Returns:
            The absolute path to the downloaded file.
        """
        ...

    def put(
        self,
        source: Union[str, Path, bytes],
        key: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload ``source`` (path or bytes) to ``key``.

        Returns:
            The storage key.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove ``key`` from storage."""
        ...

    def exists(self, key: str) -> bool:
        """Return True if ``key`` exists in storage."""
        ...

    def url(self, key: str, expires_in: int = 3600) -> str:
        """Return a URL that can be used to retrieve ``key``.

        For the local backend this is a ``file://`` URL. For R2/S3 this is a
        presigned URL.
        """
        ...


class LocalStorage:
    """Filesystem-backed storage rooted at a single directory.

    Writes are atomic: data is first written to a sibling ``.tmp`` file and
    then renamed into place so concurrent readers never see partial content.
    """

    def __init__(self, root: Optional[str] = None) -> None:
        self.root = os.path.abspath(root or os.environ.get("STORAGE_ROOT", _DEFAULT_LOCAL_ROOT))
        os.makedirs(self.root, exist_ok=True)

    def _safe_path(self, key: str) -> str:
        """Resolve ``key`` under the storage root, rejecting traversal."""
        # Normalize forward/backward slashes and strip leading/trailing slashes.
        if key.startswith("/") or key.startswith("\\"):
            raise ValueError(f"Storage key must be relative: {key}")
        normalized = key.replace("\\", "/").strip("/")
        if not normalized:
            raise ValueError("Storage key cannot be empty")
        if ".." in normalized.split("/"):
            raise ValueError(f"Storage key contains path traversal: {key}")
        if os.path.isabs(normalized):
            raise ValueError(f"Storage key must be relative: {key}")
        return os.path.join(self.root, *normalized.split("/"))

    def get(self, key: str, local_path: str) -> str:
        src = self._safe_path(key)
        dst = os.path.abspath(local_path)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)
        return dst

    def put(
        self,
        source: Union[str, Path, bytes],
        key: str,
        content_type: Optional[str] = None,
    ) -> str:
        target = self._safe_path(key)
        os.makedirs(os.path.dirname(target) or self.root, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(target) or self.root, suffix=".tmp")
        try:
            if isinstance(source, (str, Path)):
                with open(source, "rb") as f:
                    data = f.read()
            else:
                data = source
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise
        return key

    def delete(self, key: str) -> None:
        path = self._safe_path(key)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return os.path.exists(self._safe_path(key))

    def url(self, key: str, expires_in: int = 3600) -> str:
        # ``expires_in`` is ignored for local files. Return a relative URL that
        # the API serves via the ``/storage/{key}`` static route.
        normalized = key.replace("\\", "/").lstrip("/")
        return f"/storage/{normalized}"


class R2Storage:
    """R2/S3-compatible storage backend.

    Currently delegates to the legacy boto3 helpers. In the future this can be
    inlined and extended with streaming, multipart, and ACL support.
    """

    def get(self, key: str, local_path: str) -> str:
        return _r2_download(key, local_path)

    def put(
        self,
        source: Union[str, Path, bytes],
        key: str,
        content_type: Optional[str] = None,
    ) -> str:
        if isinstance(source, (str, Path)):
            return _r2_upload(str(source), key, content_type=content_type)
        # Bytes path: write to a temp file first, then upload.
        ext = os.path.splitext(key)[1] or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(source)
            tmp_path = tmp.name
        try:
            return _r2_upload(tmp_path, key, content_type=content_type)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def delete(self, key: str) -> None:
        _r2_delete(key)

    def exists(self, key: str) -> bool:
        try:
            _r2_head(key)
            return True
        except Exception:
            return False

    def url(self, key: str, expires_in: int = 3600) -> str:
        return _r2_presigned_url(key, expires_in=expires_in)


# ── Legacy boto3 helpers (kept private; used by R2Storage) ───────────────────


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


def _r2_download(storage_key: str, local_path: str) -> str:
    s3 = _get_s3_client()
    bucket = _bucket()
    local_path = os.path.abspath(local_path)
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

    try:
        s3.download_file(bucket, storage_key, local_path)
    except ClientError as e:
        try:
            os.remove(local_path)
        except OSError:
            pass
        raise RuntimeError(f"Failed to download {storage_key}: {e}") from e

    return local_path


def _r2_upload(local_path: str, storage_key: str, content_type: Optional[str] = None) -> str:
    s3 = _get_s3_client()
    bucket = _bucket()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        s3.upload_file(local_path, bucket, storage_key, ExtraArgs=extra_args)
    except ClientError as e:
        raise RuntimeError(f"Failed to upload {local_path} to {storage_key}: {e}") from e

    return storage_key


def _r2_delete(storage_key: str) -> None:
    s3 = _get_s3_client()
    bucket = _bucket()
    try:
        s3.delete_object(Bucket=bucket, Key=storage_key)
    except ClientError as e:
        raise RuntimeError(f"Failed to delete {storage_key}: {e}") from e


def _r2_head(storage_key: str):
    s3 = _get_s3_client()
    bucket = _bucket()
    return s3.head_object(Bucket=bucket, Key=storage_key)


def _r2_presigned_url(storage_key: str, expires_in: int = 3600) -> str:
    s3 = _get_s3_client()
    bucket = _bucket()
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )


# ── Factory and legacy public helpers ────────────────────────────────────────


def get_storage() -> StorageBackend:
    """Return the configured storage backend.

    Reads ``STORAGE_BACKEND`` (``local`` or ``r2``). Defaults to ``local``.
    """
    backend = os.environ.get("STORAGE_BACKEND", "local").lower()
    if backend == "r2":
        return R2Storage()
    return LocalStorage()


def download_asset(storage_key: str, local_path: Optional[str] = None) -> str:
    """Download an asset from storage to a local path."""
    if local_path is None:
        ext = os.path.splitext(storage_key)[1] or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, prefix="ave_", suffix=ext) as tmp:
            local_path = tmp.name
    return get_storage().get(storage_key, local_path)


def upload_file(local_path: str, storage_key: str, content_type: Optional[str] = None) -> str:
    """Upload a local file to storage."""
    return get_storage().put(local_path, storage_key, content_type=content_type)


def delete_asset(storage_key: str) -> None:
    """Delete an asset from storage."""
    get_storage().delete(storage_key)


def get_presigned_download_url(storage_key: str, expires_in: int = 3600) -> str:
    """Generate a download URL for an asset."""
    return get_storage().url(storage_key, expires_in=expires_in)
