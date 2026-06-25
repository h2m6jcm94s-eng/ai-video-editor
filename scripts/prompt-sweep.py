#!/usr/bin/env python3
"""Run prompt edits against a baseline cutlist and score the results.

Modes:
    sweep    - Apply each prompt to the same baseline and log all results.
    improve  - Hill-climb: apply prompts sequentially to the current best
               cutlist, keep changes that raise the score, and maintain a
               changelog.

Usage (from repo root, with dev stack running):
    uv run python scripts/prompt-sweep.py
    uv run python scripts/prompt-sweep.py --mode improve

Environment:
    BASE_API_URL  - API base URL (default http://localhost:4000)
    FIXTURES_DIR  - Directory with reference/song/clips (default docs/assets/car-meet)
    AI_PROVIDER   - Ignored by this script; the API uses its own env.
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from cutlist_scorer import format_score, score_cutlist

BASE_URL = os.environ.get("BASE_API_URL", "http://localhost:4000").rstrip("/")
FIXTURES_DIR = Path(os.environ.get("FIXTURES_DIR", "docs/assets/car-meet"))
PROMPTS = [
    "Make the edit feel more energetic and fast-paced.",
    "Slow everything down and add a cinematic, moody vibe.",
    "Cut on every beat of the song.",
    "Use only the most dramatic clips and drop the quiet ones.",
    "Add smooth fade transitions between every cut.",
    "Make the first half calm and the second half intense.",
    "Reorder the cuts to build tension progressively.",
    "Shorten the total length by removing weaker moments.",
    "Give it a vintage film look with warm tones.",
    "Make it feel like a high-end car commercial.",
    "Add more contrast between day and night scenes.",
    "Keep the focus on the car; remove people shots.",
    "Make the pacing syncopated — cut just before the beat.",
    "Create a looping structure where the ending mirrors the beginning.",
    "Make each cut exactly 1 second long.",
]


def api(client: httpx.Client, method: str, path: str, **kwargs) -> Any:
    url = f"{BASE_URL}{path}" if path.startswith("/") else f"{BASE_URL}/{path}"
    resp = client.request(method, url, timeout=60.0, **kwargs)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code} {method} {path}: {exc.response.text[:500]}")
        raise
    return resp.json() if resp.text else None


def wait_for_asset(client: httpx.Client, project_id: str, asset_id: str, timeout_s: float = 120.0) -> dict:
    """Poll until the ingest worker populates duration/width/height."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        data = api(client, "GET", f"/api/projects/{project_id}")
        asset = next((a for a in data.get("project", {}).get("assets", []) if a.get("id") == asset_id), None)
        duration = asset.get("durationSec") if asset else None
        print(f"  asset {asset_id[:8]}... duration={duration}")
        if duration is not None:
            return asset
        if asset and asset.get("metadata", {}).get("error"):
            raise RuntimeError(f"Asset {asset_id} ingestion failed: {asset['metadata']['error']}")
        time.sleep(2.0)
    raise TimeoutError(f"Asset {asset_id} did not ingest within {timeout_s}s")


def upload_asset(client: httpx.Client, project_id: str, asset_type: str, path: Path) -> dict:
    print(f"Uploading {asset_type}: {path.name}")
    presigned = api(
        client,
        "POST",
        "/api/uploads/presigned",
        json={
            "projectId": project_id,
            "filename": path.name,
            "mimeType": "video/mp4" if path.suffix == ".mp4" else "audio/mpeg",
            "type": asset_type,
        },
    )
    upload_url = presigned["url"]
    asset_id = presigned["assetId"]
    fields = presigned.get("fields", {})

    with path.open("rb") as f:
        files = {"file": (path.name, f, presigned.get("contentType", "application/octet-stream"))}
        # MinIO presigned POST returns fields; presigned PUT returns just URL.
        if fields:
            upload_resp = httpx.post(upload_url, data=fields, files=files, timeout=120.0)
        else:
            upload_resp = httpx.put(upload_url, content=f, timeout=120.0)
    upload_resp.raise_for_status()
    etag = upload_resp.headers.get("ETag", "")

    api(
        client,
        "POST",
        f"/api/uploads/{asset_id}/complete",
        json={"sizeBytes": path.stat().st_size, "etag": etag},
    )
    return wait_for_asset(client, project_id, asset_id)


def create_project(client: httpx.Client) -> str:
    name = f"prompt-sweep-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    data = api(client, "POST", "/api/projects", json={"name": name, "styleTier": "with_effects", "mode": "auto"})
    return data["project"]["id"]


def wait_for_generation(client: httpx.Client, project_id: str, timeout_s: float = 300.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        data = api(client, "GET", f"/api/projects/{project_id}/generation")
        status = data.get("job", {}).get("status") if isinstance(data, dict) else None
        print(f"  generation job status={status}")
        if status in ("completed", "complete"):
            return api(client, "GET", f"/api/projects/{project_id}")["project"]
        if status in ("failed", "error"):
            raise RuntimeError(f"Generation job failed: {data}")
        time.sleep(3.0)
    raise TimeoutError(f"Generation job did not complete within {timeout_s}s")


def generate_baseline(client: httpx.Client, project_id: str) -> dict:
    print("Starting baseline cutlist generation...")
    api(client, "POST", f"/api/projects/{project_id}/generate", json={"options": {"durationSec": 15}})
    project = wait_for_generation(client, project_id)
    return project["cutList"]


def set_cutlist(client: httpx.Client, project_id: str, cutlist: dict) -> None:
    api(client, "PATCH", f"/api/projects/{project_id}/cutlist", json={"cutList": cutlist})


def apply_prompt(client: httpx.Client, project_id: str, prompt: str) -> dict:
    return api(client, "POST", f"/api/projects/{project_id}/prompt", json={"prompt": prompt})


def run_sweep(client: httpx.Client, project_id: str, baseline: dict) -> list[dict]:
    results = []
    for idx, prompt in enumerate(PROMPTS, 1):
        print(f"\n[{idx}/{len(PROMPTS)}] Prompt: {prompt}")
        set_cutlist(client, project_id, baseline)
        resp = apply_prompt(client, project_id, prompt)
        cutlist = resp.get("project", {}).get("cutList") or baseline
        results.append({
            "index": idx,
            "prompt": prompt,
            "explanation": resp.get("explanation"),
            "diff": resp.get("diff"),
            "usage": resp.get("usage"),
            "score": score_cutlist(cutlist),
            "resultCutList": cutlist,
        })
    return results


def run_improvement_loop(client: httpx.Client, project_id: str, baseline: dict) -> dict:
    """Hill-climb through prompts, keeping edits that raise the total score."""
    best_cutlist = baseline
    best_score = score_cutlist(baseline)
    print(f"\nBaseline score: {format_score(best_score)}")

    iterations = [
        {
            "index": 0,
            "prompt": "*baseline*",
            "scoreBefore": best_score,
            "scoreAfter": best_score,
            "decision": "keep",
            "explanation": "Starting generated cutlist.",
            "diff": [],
        }
    ]

    for idx, prompt in enumerate(PROMPTS, 1):
        print(f"\n[{idx}/{len(PROMPTS)}] Prompt: {prompt}")
        set_cutlist(client, project_id, best_cutlist)
        try:
            resp = apply_prompt(client, project_id, prompt)
            cutlist = resp.get("project", {}).get("cutList") or best_cutlist
            explanation = resp.get("explanation", "")
            diff = resp.get("diff", [])
            usage = resp.get("usage")
        except Exception as exc:
            print(f"  Prompt edit failed: {exc}")
            iterations.append({
                "index": idx,
                "prompt": prompt,
                "scoreBefore": best_score,
                "scoreAfter": best_score,
                "decision": "error",
                "explanation": f"Error: {exc}",
                "diff": [],
                "error": traceback.format_exc(),
            })
            continue

        before = best_score
        after = score_cutlist(cutlist)
        delta = after["total"] - before["total"]

        if delta > 0.001:
            decision = "keep"
            best_cutlist = cutlist
            best_score = after
            print(f"  Improved by {delta:+.3f} -> {format_score(after)} (kept)")
        else:
            decision = "revert"
            print(f"  Changed by {delta:+.3f} -> {format_score(after)} (reverted)")

        iterations.append({
            "index": idx,
            "prompt": prompt,
            "scoreBefore": before,
            "scoreAfter": after,
            "decision": decision,
            "explanation": explanation,
            "diff": diff,
            "usage": usage,
        })

    # Persist the best cutlist on the project.
    set_cutlist(client, project_id, best_cutlist)

    return {
        "baseline": baseline,
        "baselineScore": score_cutlist(baseline),
        "bestCutList": best_cutlist,
        "bestScore": best_score,
        "iterations": iterations,
    }


def write_changelog(project_id: str, improvement: dict, output_path: Path) -> None:
    baseline_score = improvement["baselineScore"]
    best_score = improvement["bestScore"]
    iterations = improvement["iterations"]
    timestamp = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Prompt-Edit Improvement Changelog\n",
        "\n",
        "This document tracks iterative prompt edits on the car-meet fixture project.\n",
        "\n",
        "## Run metadata\n",
        "\n",
        f"| Field | Value |\n",
        f"|-------|-------|\n",
        f"| Project ID | `{project_id}` |\n",
        f"| Baseline score | `{format_score(baseline_score)}` |\n",
        f"| Best score | `{format_score(best_score)}` |\n",
        f"| Total iterations | `{len(iterations) - 1}` |\n",
        f"| Timestamp | `{timestamp}` |\n",
        "\n",
        "## Scoring weights\n",
        "\n",
        "| Dimension | Weight | Rationale |\n",
        "|-----------|--------|-----------|\n",
        "| Pacing | 0.25 | Moderate shot-duration variety keeps energy without jarring cuts. |\n",
        "| Sync | 0.20 | Cuts aligned to the beat grid feel musical and intentional. |\n",
        "| Diversity | 0.20 | Reusing clips and shot types too often makes the edit repetitive. |\n",
        "| Energy arc | 0.20 | A rising/falling energy curve matches song structure and viewer attention. |\n",
        "| Transition variety | 0.15 | Mixing transitions adds polish; all hard cuts feel raw. |\n",
        "\n",
        "## Iterations\n",
        "\n",
        "| # | Prompt | Score before | Score after | Decision | What changed |\n",
        "|---|--------|--------------|-------------|----------|--------------|\n",
    ]

    for it in iterations:
        idx = it["index"]
        prompt = it["prompt"].replace("|", "\\|")
        before = format_score(it["scoreBefore"]) if isinstance(it["scoreBefore"], dict) else str(it["scoreBefore"])
        after = format_score(it["scoreAfter"]) if isinstance(it["scoreAfter"], dict) else str(it["scoreAfter"])
        decision = it["decision"]
        explanation = (it.get("explanation") or "").replace("\n", " ").replace("|", "\\|")[:120]
        lines.append(f"| {idx} | {prompt} | {before} | {after} | {decision} | {explanation} |\n")

    lines += [
        "\n",
        "## Summary\n",
        "\n",
        f"Best total score: `{format_score(best_score)}`. "
        f"Kept {sum(1 for it in iterations if it['decision'] == 'keep') - 1} of {len(iterations) - 1} prompt edits.\n",
    ]

    output_path.write_text("".join(lines), encoding="utf-8")
    print(f"Saved changelog: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run prompt edits and score the resulting cutlists.")
    parser.add_argument("--mode", choices=["sweep", "improve"], default="sweep", help="Edit strategy.")
    args = parser.parse_args()

    print(f"API: {BASE_URL}")
    print(f"Fixtures: {FIXTURES_DIR.resolve()}")
    print(f"Mode: {args.mode}")

    required = ["reference.mp4", "song.mp3", "clip-1.mp4", "clip-2.mp4", "clip-3.mp4"]
    missing = [f for f in required if not (FIXTURES_DIR / f).exists()]
    if missing:
        print(f"Missing fixtures: {missing}")
        return 1

    with httpx.Client() as client:
        try:
            api(client, "GET", "/api/health")
        except Exception as exc:
            print(f"API health check failed: {exc}")
            print("Make sure the dev stack is running (pnpm dev:full).")
            return 1

        project_id = create_project(client)
        print(f"Created project: {project_id}")

        upload_asset(client, project_id, "reference_video", FIXTURES_DIR / "reference.mp4")
        upload_asset(client, project_id, "song", FIXTURES_DIR / "song.mp3")
        upload_asset(client, project_id, "clip", FIXTURES_DIR / "clip-1.mp4")
        upload_asset(client, project_id, "clip", FIXTURES_DIR / "clip-2.mp4")
        upload_asset(client, project_id, "clip", FIXTURES_DIR / "clip-3.mp4")

        baseline = generate_baseline(client, project_id)
        print(f"\nBaseline cutlist: {len(baseline.get('slots', []))} slots")
        print(f"Baseline score: {format_score(score_cutlist(baseline))}")

        if args.mode == "improve":
            improvement = run_improvement_loop(client, project_id, baseline)
        else:
            results = run_sweep(client, project_id, baseline)
            improvement = {
                "baseline": baseline,
                "baselineScore": score_cutlist(baseline),
                "bestCutList": baseline,
                "bestScore": score_cutlist(baseline),
                "iterations": results,
            }

    output_dir = Path(".tmp")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_path = output_dir / f"prompt-sweep-{args.mode}-{timestamp}.json"
    log = {
        "mode": args.mode,
        "projectId": project_id,
        "baseUrl": BASE_URL,
        "fixturesDir": str(FIXTURES_DIR),
        "baselineCutList": baseline,
        "baselineScore": improvement["baselineScore"],
        "bestCutList": improvement["bestCutList"],
        "bestScore": improvement["bestScore"],
        "iterations": improvement["iterations"],
    }
    output_path.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved sweep log: {output_path}")

    if args.mode == "improve":
        changelog_path = Path("docs/prompt-edit-changelog.md")
        write_changelog(project_id, improvement, changelog_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
