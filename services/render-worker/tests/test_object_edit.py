# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from render_worker.object_edit import (
    MONTHLY_GENERATION_BUDGET_USD,
    ObjectEditResult,
    run_object_edit,
)
from render_worker.sam3_client import Sam3UnavailableError, SegmentationResult


@pytest.fixture
def mock_env(monkeypatch, tmp_path):
    """Use an isolated SAM3 cache directory and low budget for tests."""
    monkeypatch.setenv("SAM3_MASK_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("MONTHLY_GENERATION_BUDGET_USD", "10.0")


@pytest.fixture
def fake_clip(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake video")
    return str(path)


@pytest.fixture
def fake_mask_result(tmp_path):
    cache = tmp_path / "mask.npz"
    cache.write_bytes(b"")
    return SegmentationResult(
        masks=["mask"],
        boxes=[[0, 0, 10, 10]],
        scores=[0.9],
        prompt_type="text",
        prompt="a red car",
        cache_path=str(cache),
    )


@pytest.mark.asyncio
async def test_run_object_edit_color_shift(mock_env, fake_clip, fake_mask_result, monkeypatch):
    called = {}

    async def fake_segment(*args, **kwargs):
        called["segment"] = (args, kwargs)
        return fake_mask_result

    def fake_classify(prompt):
        called["classify"] = prompt
        return "color_shift"

    def fake_brand(prompt):
        return False

    def fake_face(*args, **kwargs):
        return False

    def fake_color_shift(clip_path, mask, spec):
        called["tier"] = ("color_shift", clip_path, mask, spec)
        return "/out/color.mp4"

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.classify_edit_intent", fake_classify)
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", fake_brand)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", fake_face)
    monkeypatch.setattr("render_worker.object_edit.apply_color_shift_tier", fake_color_shift)

    result = await run_object_edit(fake_clip, "make it warmer", prompt_type="text")

    assert isinstance(result, ObjectEditResult)
    assert result.output_path == "/out/color.mp4"
    assert result.tier == "color_shift"
    assert result.cost_usd == 0.05
    assert result.skipped is False
    assert result.mask_result is fake_mask_result


@pytest.mark.asyncio
async def test_run_object_edit_texture_replace(mock_env, fake_clip, fake_mask_result, monkeypatch):
    async def fake_segment(*args, **kwargs):
        return fake_mask_result

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.classify_edit_intent", lambda p: "texture_replace")
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", lambda p: False)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", lambda *a, **k: False)

    async def fake_texture_replace(clip_path, mask, prompt):
        return "/out/texture.mp4"

    monkeypatch.setattr("render_worker.object_edit.apply_texture_replace_tier", fake_texture_replace)

    result = await run_object_edit(fake_clip, "turn the car into gold")
    assert result.tier == "texture_replace"
    assert result.cost_usd == 0.50
    assert result.output_path == "/out/texture.mp4"


@pytest.mark.asyncio
async def test_run_object_edit_structural_change(mock_env, fake_clip, fake_mask_result, monkeypatch):
    async def fake_segment(*args, **kwargs):
        return fake_mask_result

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.classify_edit_intent", lambda p: "structural_change")
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", lambda p: False)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", lambda *a, **k: False)

    async def fake_structural(clip_path, mask, prompt):
        return "/out/structural.mp4"

    monkeypatch.setattr("render_worker.object_edit.apply_structural_change_tier", fake_structural)

    result = await run_object_edit(fake_clip, "replace the car with a dragon")
    assert result.tier == "structural_change"
    assert result.cost_usd == 2.00
    assert result.output_path == "/out/structural.mp4"


@pytest.mark.asyncio
async def test_run_object_edit_sam3_unavailable(mock_env, fake_clip, monkeypatch):
    async def fake_segment(*args, **kwargs):
        raise Sam3UnavailableError("down")

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)

    result = await run_object_edit(fake_clip, "anything")
    assert result.skipped is True
    assert "SAM3 server unavailable" in (result.skip_reason or "")
    assert result.output_path == fake_clip


@pytest.mark.asyncio
async def test_run_object_edit_no_masks(mock_env, fake_clip, monkeypatch):
    empty_mask = SegmentationResult(
        masks=[],
        boxes=[],
        scores=[],
        prompt_type="text",
        prompt="x",
    )

    async def fake_segment(*args, **kwargs):
        return empty_mask

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)

    result = await run_object_edit(fake_clip, "anything")
    assert result.skipped is True
    assert "no masks" in (result.skip_reason or "").lower()


@pytest.mark.asyncio
async def test_run_object_edit_brand_ip_blocked(mock_env, fake_clip, fake_mask_result, monkeypatch):
    async def fake_segment(*args, **kwargs):
        return fake_mask_result

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.classify_edit_intent", lambda p: "texture_replace")
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", lambda p: True)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", lambda *a, **k: False)

    result = await run_object_edit(fake_clip, "make it look like Nike")
    assert result.skipped is True
    assert "brand/IP" in (result.skip_reason or "")
    assert result.output_path == fake_clip


@pytest.mark.asyncio
async def test_run_object_edit_budget_exceeded(mock_env, fake_clip, fake_mask_result, monkeypatch):
    async def fake_segment(*args, **kwargs):
        return fake_mask_result

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.classify_edit_intent", lambda p: "structural_change")
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", lambda p: False)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", lambda *a, **k: False)

    with pytest.raises(RuntimeError, match="budget exceeded"):
        await run_object_edit(
            fake_clip,
            "replace the car with a dragon",
            current_monthly_spend=MONTHLY_GENERATION_BUDGET_USD,
        )


@pytest.mark.asyncio
async def test_run_object_edit_non_text_prompt_defaults_to_structural(
    mock_env, fake_clip, fake_mask_result, monkeypatch
):
    async def fake_segment(*args, **kwargs):
        return fake_mask_result

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", lambda p: False)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", lambda *a, **k: False)

    async def fake_structural(clip_path, mask, prompt):
        return "/out/structural.mp4"

    monkeypatch.setattr("render_worker.object_edit.apply_structural_change_tier", fake_structural)

    result = await run_object_edit(fake_clip, [10, 20, 30, 40], prompt_type="box")
    assert result.tier == "structural_change"


@pytest.mark.asyncio
async def test_run_object_edit_face_edit_gate_skipped(mock_env, fake_clip, fake_mask_result, monkeypatch):
    async def fake_segment(*args, **kwargs):
        return fake_mask_result

    monkeypatch.setattr("render_worker.object_edit.segment_object_in_clip", fake_segment)
    monkeypatch.setattr("render_worker.object_edit.classify_edit_intent", lambda p: "texture_replace")
    monkeypatch.setattr("render_worker.object_edit.is_brand_ip_violation", lambda p: False)
    monkeypatch.setattr("render_worker.object_edit.is_face_edit", lambda *a, **k: True)

    result = await run_object_edit(fake_clip, "change the person's shirt")
    assert result.skipped is True
    assert "Face edit" in (result.skip_reason or "")
