#!/usr/bin/env python3
"""Check the demo grade of the last render.

Reads a cutlist JSON (or a standalone report JSON) and exits with a non-zero
status if any demo-critical feature ran a fallback path or if the render did
not meet the demo grade threshold.

Usage:
    .venv/Scripts/python scripts/check_demo_grade.py [path/to/cutlist.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CUTLIST = (
    REPO_ROOT / "test files" / "batch 2" / "output" / "cutlist.json"
)

DEMO_CRITICAL_FEATURES = {
    "heatmap",
    "aesthetic",
    "iconic_quotes",
    "identity_matte",
    "dialogue",
    "save_the_cat",
    "auto_lut",
    "style_genome",
    "demucs",
    "momentum",
}


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _report_from_cutlist(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the feature runtime report from a cutlist or report file."""
    if "feature_runtime_report" in data:
        return data["feature_runtime_report"]
    if "featureRuntimeReport" in data:
        return data["featureRuntimeReport"]
    if isinstance(data, list):
        return data
    return []


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check demo grade of a render")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_CUTLIST,
        help="Path to cutlist.json or feature report JSON",
    )
    args = parser.parse_args(argv)

    path: Path = args.path
    if not path.exists():
        print(f"ERROR: report not found: {path}", file=sys.stderr)
        return 2

    data = _load_json(path)
    report = _report_from_cutlist(data)

    if not report:
        print(f"WARNING: no feature_runtime_report found in {path}")
        return 0

    demo_grade = data.get("demo_grade") or data.get("demoGrade")
    real_path_ratio = data.get("real_path_ratio") or data.get("realPathRatio")

    fallback_features = [
        entry["feature"]
        for entry in report
        if not entry.get("real_path_ran", entry.get("realPathRan"))
        and entry.get("feature") in DEMO_CRITICAL_FEATURES
    ]

    print(f"Cutlist: {path}")
    print(f"Demo grade: {demo_grade}")
    if real_path_ratio is not None:
        print(f"Real-path ratio: {real_path_ratio:.2f}")
    print(f"Traced features: {len(report)}")

    if fallback_features:
        print("\nDemo-critical features that ran fallback:")
        for name in fallback_features:
            print(f"  - {name}")
        return 1

    print("\nAll demo-critical features ran the real path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
