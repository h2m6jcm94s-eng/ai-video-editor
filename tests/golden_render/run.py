#!/usr/bin/env python3
"""Golden Render Regression Suite runner.

Thin wrapper around scripts/golden-render-suite.py that compares the rendered
output against tests/golden_render/expected/expected_signatures.json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUITE = REPO_ROOT / "scripts" / "golden-render-suite.py"
EXPECTED = Path(__file__).resolve().parent / "expected" / "expected_signatures.json"

WAVE10_CRITERIA = {
    "zoom_punch_ins_on_kicks",
    "vignette_on_crisis_or_victory",
    "hm_mvgd_hm_shipped",
}


def _load_expected() -> Dict[str, Any]:
    with open(EXPECTED, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_suite(
    feature_emotion_led_cuts: bool = False,
    skip_render: bool = False,
    feature_wave_8: bool = False,
    feature_wave_9: bool = False,
    feature_wave_10: bool = False,
) -> Dict[str, Any]:
    cmd = [sys.executable, str(SUITE), "--json"]
    if feature_emotion_led_cuts:
        cmd.append("--feature-emotion-led-cuts")
    if feature_wave_8:
        cmd.append("--feature-wave-8")
    if feature_wave_9:
        cmd.append("--feature-wave-9")
    if feature_wave_10:
        cmd.append("--feature-wave-10")
    if skip_render:
        cmd.append("--skip-render")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0 and not result.stdout.strip():
        print(result.stderr or "suite failed with no output", file=sys.stderr)
        sys.exit(1)
    # The suite prints the JSON payload to stdout even on failure. The suite
    # may also emit human-readable log lines before the JSON, so extract the
    # first JSON object rather than parsing stdout as a single document.
    raw = result.stdout
    start = raw.find("{")
    if start == -1:
        print("suite produced no JSON object", file=sys.stderr)
        print(raw[-2000:], file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(raw[start:])
    except json.JSONDecodeError as e:
        print(f"failed to parse suite output: {e}", file=sys.stderr)
        print(raw[-2000:], file=sys.stderr)
        sys.exit(1)


def _check_criterion(
    name: str, actual: Dict[str, Any], spec: Dict[str, Any]
) -> Tuple[bool, str]:
    passed = actual.get("passed", False)
    value = actual.get("value")
    detail = actual.get("detail", "")

    if not spec.get("required", True):
        return passed, f"{name}={value} (optional) {detail}"

    if not passed:
        return False, f"{name}={value} threshold={spec} {detail}"

    # Numeric checks against expected bounds (redundant with the suite, but
    # ensures expected_signatures.json stays in sync).
    if "min" in spec:
        try:
            if float(value) < float(spec["min"]):
                return False, f"{name}={value} < min {spec['min']}"
        except (TypeError, ValueError):
            pass
    if "max" in spec:
        try:
            if float(value) > float(spec["max"]):
                return False, f"{name}={value} > max {spec['max']}"
        except (TypeError, ValueError):
            pass
    if "max_delta" in spec:
        # SSIM delta is checked by the suite; value may be 'n/a'.
        pass

    return True, f"{name}={value} {detail}"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden Render Regression Suite runner")
    parser.add_argument(
        "--feature-emotion-led-cuts",
        action="store_true",
        help="Run the Phase 2 emotion-led narrative arc path.",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Reuse the existing output from a previous run.",
    )
    parser.add_argument(
        "--feature-wave-8",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply Wave 8 criteria.",
    )
    parser.add_argument(
        "--feature-wave-9",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply Wave 9 criteria.",
    )
    parser.add_argument(
        "--feature-wave-10",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Apply Wave 10 criteria.",
    )
    args = parser.parse_args(argv)

    expected = _load_expected()
    if not args.feature_wave_10:
        expected = {
            name: spec
            for name, spec in expected.items()
            if name not in WAVE10_CRITERIA
        }
    suite_cmd = [sys.executable, str(SUITE), "--json"]
    if args.feature_emotion_led_cuts:
        suite_cmd.append("--feature-emotion-led-cuts")
    if args.feature_wave_8:
        suite_cmd.append("--feature-wave-8")
    if args.feature_wave_9:
        suite_cmd.append("--feature-wave-9")
    if args.feature_wave_10:
        suite_cmd.append("--feature-wave-10")
    if args.skip_render:
        suite_cmd.append("--skip-render")

    print(f"Running: {' '.join(suite_cmd)}")
    data = _run_suite(
        feature_emotion_led_cuts=args.feature_emotion_led_cuts,
        skip_render=args.skip_render,
        feature_wave_8=args.feature_wave_8,
        feature_wave_9=args.feature_wave_9,
        feature_wave_10=args.feature_wave_10,
    )

    criteria = {c["name"]: c for c in data.get("criteria", [])}
    required_failures = 0
    optional_failures = 0

    for name, spec in expected.items():
        actual = criteria.get(name)
        if actual is None:
            if spec.get("required", True):
                print(f"FAIL {name}: missing from suite output")
                required_failures += 1
            else:
                print(f"SKIP {name}: missing from suite output (optional)")
            continue
        ok, msg = _check_criterion(name, actual, spec)
        status = "PASS" if ok else ("FAIL" if spec.get("required", True) else "WARN")
        print(f"{status} {msg}")
        if not ok:
            if spec.get("required", True):
                required_failures += 1
            else:
                optional_failures += 1

    print("-" * 60)
    print(
        f"Suite: {data.get('passed', 0)} passed, {data.get('failed', 0)} failed, "
        f"{data.get('skipped', 0)} skipped"
    )
    print(
        f"Expected checks: {len(expected)} checked, "
        f"{required_failures} required failures, {optional_failures} optional failures"
    )

    if required_failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
