#!/usr/bin/env python3
"""Pre-download long-lead models for the AI video editor stack.

Usage:
    .venv/Scripts/python scripts/download_models.py --token <HF_TOKEN>

Models queued:
    - RVM v2 (PytorchVideo / robust video matting)
    - allin1 + natten (real song-structure analysis)
    - Demucs v4 (music source separation for stems)
    - SAM 3 / SAM 3.1 checkpoints (subject segmentation)

Gated models (SAM 3) require Hugging Face access approval *before* download.
Run this script to surface missing access early.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "models"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Model spec: (repo_id, filename, subfolder)
MODEL_QUEUE = [
    ("facebook/sam3", "sam3.1_hiera_t.yaml", None),
    ("facebook/sam3", "sam3.1_hiera_t.pt", None),
    ("facebook/sam3.1", "sam3.1_hiera_s.yaml", None),
    ("facebook/sam3.1", "sam3.1_hiera_s.pt", None),
]

# Non-gated / PyTorch Hub identifiers
HUB_QUEUE = [
    ("rvm", "rvm_resnet50.pth"),
]


def _hf_api(token: str | None):
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("huggingface_hub not installed. Run: uv pip install huggingface_hub")
        sys.exit(1)
    return HfApi(token=token)


def check_access(api, repo_id: str) -> bool:
    """Return True if the current token can access repo_id."""
    try:
        from huggingface_hub.utils import GatedRepoError, HfHubHTTPError
    except ImportError:
        return False
    try:
        api.repo_info(repo_id)
        return True
    except GatedRepoError:
        print(f"  ❌ {repo_id}: access not granted. Request access at https://huggingface.co/{repo_id}")
        return False
    except HfHubHTTPError as e:
        print(f"  ⚠️  {repo_id}: HTTP error ({e})")
        return False
    except Exception as e:
        print(f"  ⚠️  {repo_id}: {e}")
        return False


def download_hf_model(repo_id: str, filename: str, subfolder: str | None, token: str | None) -> str | None:
    from huggingface_hub import hf_hub_download
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            subfolder=subfolder or None,
            cache_dir=str(CACHE_DIR),
            token=token,
            local_files_only=False,
        )
        print(f"  ✅ {repo_id}/{filename} -> {path}")
        return path
    except Exception as e:
        print(f"  ❌ {repo_id}/{filename}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Pre-download models")
    parser.add_argument("--token", default=None, help="Hugging Face access token")
    parser.add_argument("--skip-gated", action="store_true", help="Skip gated SAM3 models")
    args = parser.parse_args()

    print(f"Cache directory: {CACHE_DIR}")
    api = _hf_api(args.token)

    print("\nChecking gated model access...")
    for repo_id, _, _ in MODEL_QUEUE:
        if args.skip_gated:
            continue
        ok = check_access(api, repo_id)
        if ok:
            print(f"  ✅ {repo_id}: access granted")

    print("\nDownloading queued models...")
    for repo_id, filename, subfolder in MODEL_QUEUE:
        if args.skip_gated and ("sam3" in repo_id.lower()):
            print(f"  ⏭️  {repo_id}/{filename} (skipped gated)")
            continue
        download_hf_model(repo_id, filename, subfolder, args.token)

    print("\nDone. If any gated models failed, request access at the URLs above.")


if __name__ == "__main__":
    main()
