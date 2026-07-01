# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for the shared storage abstraction."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from shared_py.storage import LocalStorage, R2Storage, StorageBackend, get_storage


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    """Return a local storage instance rooted in a temporary directory."""
    return LocalStorage(root=str(tmp_path))


class TestLocalStorage:
    def test_put_and_get_bytes(self, storage: LocalStorage, tmp_path: Path) -> None:
        key = "test/hello.txt"
        storage.put(b"hello world", key)

        local_path = str(tmp_path / "out.txt")
        storage.get(key, local_path)

        with open(local_path, "r", encoding="utf-8") as f:
            assert f.read() == "hello world"

    def test_put_and_get_file(self, storage: LocalStorage, tmp_path: Path) -> None:
        source = tmp_path / "source.bin"
        source.write_bytes(b"binary data")

        key = "nested/path/file.bin"
        storage.put(str(source), key)

        dest = tmp_path / "dest.bin"
        storage.get(key, str(dest))
        assert dest.read_bytes() == b"binary data"

    def test_put_returns_key(self, storage: LocalStorage) -> None:
        key = "foo/bar.txt"
        assert storage.put(b"data", key) == key

    def test_exists_and_delete(self, storage: LocalStorage) -> None:
        key = "delete-me.txt"
        assert not storage.exists(key)
        storage.put(b"x", key)
        assert storage.exists(key)
        storage.delete(key)
        assert not storage.exists(key)

    def test_delete_missing_is_noop(self, storage: LocalStorage) -> None:
        storage.delete("does/not/exist.txt")

    def test_url_is_local_proxy_path(self, storage: LocalStorage) -> None:
        key = "a/b.txt"
        storage.put(b"x", key)
        url = storage.url(key)
        assert url == "/storage/a/b.txt"

    def test_rejects_path_traversal(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="traversal"):
            storage.put(b"x", "../etc/passwd")

    def test_rejects_absolute_key(self, storage: LocalStorage) -> None:
        with pytest.raises(ValueError, match="relative"):
            storage.put(b"x", "/etc/passwd")

    def test_atomic_write(self, storage: LocalStorage, tmp_path: Path) -> None:
        key = "atomic.txt"
        storage.put(b"final", key)
        # No partial .tmp file should be left behind.
        tmp_files = list(Path(storage.root).rglob("*.tmp"))
        assert not tmp_files

    def test_get_creates_parent_dirs(self, storage: LocalStorage, tmp_path: Path) -> None:
        storage.put(b"data", "x.txt")
        local_path = str(tmp_path / "deep" / "nested" / "out.txt")
        storage.get("x.txt", local_path)
        assert Path(local_path).read_bytes() == b"data"


class TestFactory:
    def test_defaults_to_local(self) -> None:
        backend = get_storage()
        assert isinstance(backend, LocalStorage)

    def test_r2_backend(self) -> None:
        with patch.dict(os.environ, {"STORAGE_BACKEND": "r2"}):
            backend = get_storage()
        assert isinstance(backend, R2Storage)

    def test_storage_root_env_override(self, tmp_path: Path) -> None:
        custom_root = str(tmp_path / "custom")
        with patch.dict(os.environ, {"STORAGE_ROOT": custom_root}):
            backend = get_storage()
        assert isinstance(backend, LocalStorage)
        assert backend.root == str(Path(custom_root).resolve())


class TestProtocol:
    def test_local_storage_satisfies_protocol(self) -> None:
        assert isinstance(LocalStorage(), StorageBackend)

    def test_r2_storage_satisfies_protocol(self) -> None:
        assert isinstance(R2Storage(), StorageBackend)
