"""
Tests for the style worker's asset-download activity.
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "style-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))


class TestDownloadReferenceVideo:
    def test_download_activity_uses_storage(self, monkeypatch):
        from style_worker.activities import download_reference_video

        called = {}

        def fake_download(storage_key, local_path):
            called["storage_key"] = storage_key
            called["local_path"] = local_path
            return local_path

        monkeypatch.setattr("style_worker.activities.download_asset", fake_download)

        result = asyncio.run(download_reference_video("asset-123", "projects/p/ref.mp4"))

        assert called["storage_key"] == "projects/p/ref.mp4"
        assert "asset-123" in called["local_path"]
        assert result == called["local_path"]
