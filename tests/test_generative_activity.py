"""
Tests for the Temporal ``generate_filler_clip`` activity.
"""

import asyncio
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "infra", "temporal"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "shared-py", "src"))

from shared_py.models import Slot


@pytest.fixture
def sample_slot():
    return {
        "index": 3,
        "startS": 6.0,
        "durationS": 2.0,
        "beatIndex": 3,
        "section": "drop",
        "targetShotType": "close_up",
        "subjectHint": " drummer",
        "motionHint": "gimbal",
        "energyLevel": 0.9,
    }


@pytest.mark.skip(reason="infra/temporal/worker.py was removed; generate_filler_clip activity no longer exists")
class TestGenerateFillerClipActivity:
    def test_activity_succeeds_and_uploads(self, monkeypatch, sample_slot):
        from reason_worker import generative_client
        from worker import generate_filler_clip

        fake_video = os.path.join(tempfile.gettempdir(), "ave_fake_gen.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"fake video bytes")

        uploaded = {}

        def fake_upload(local_path, storage_key, content_type=None):
            uploaded["local_path"] = local_path
            uploaded["storage_key"] = storage_key
            uploaded["content_type"] = content_type
            return storage_key

        def fake_provider_factory(*args, **kwargs):
            class FakeProvider:
                def name(self):
                    return "mock"

                def available(self):
                    return True

                def generate(self, prompt, duration, aspect_ratio="16:9"):
                    return generative_client.GenerationResult(
                        provider="mock",
                        status="succeeded",
                        local_path=fake_video,
                        metadata={"prompt": prompt},
                    )

            return FakeProvider()

        monkeypatch.setattr(generative_client, "get_generative_provider", fake_provider_factory)
        monkeypatch.setattr("worker.upload_file", fake_upload)

        result = asyncio.run(
            generate_filler_clip(sample_slot, {}, None, "proj-123", "16:9")
        )

        assert result["status"] == "succeeded"
        assert result["provider"] == "mock"
        assert result["asset_id"].startswith("gen_")
        assert uploaded["storage_key"].startswith("projects/proj-123/generated/")
        assert uploaded["content_type"] == "video/mp4"

    def test_activity_reports_failure_when_provider_fails(self, monkeypatch, sample_slot):
        from reason_worker import generative_client
        from worker import generate_filler_clip

        def fake_provider_factory(*args, **kwargs):
            class FakeProvider:
                def name(self):
                    return "mock"

                def available(self):
                    return True

                def generate(self, prompt, duration, aspect_ratio="16:9"):
                    return generative_client.GenerationResult(
                        provider="mock", status="failed", error="rate limited"
                    )

            return FakeProvider()

        monkeypatch.setattr(generative_client, "get_generative_provider", fake_provider_factory)

        result = asyncio.run(
            generate_filler_clip(sample_slot, {}, None, "proj-123")
        )

        assert result["status"] == "failed"
        assert "rate limited" in result["error"]
