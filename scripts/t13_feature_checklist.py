#!/usr/bin/env python3
"""T.13 feature checklist verifier.

Checks that the features built across Waves 5X-10 and Tickets 0-3 actually
appear in the two demo renders:
  - batch 2 (Cyberpunk Edgerunners AMV)
  - test folder 2 (Kimi No Nawa / Sparkle)

For batch 2 it also runs the existing golden-render-suite.py with all flags.
For test folder 2 it runs a cutlist-based check equivalent to the golden checks
that do not depend on the Cyberpunk fixture.

Outputs:
  _t13_checklist/feature_checklist.json
  T13_FEATURE_CHECKLIST.md
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parent.parent
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

WORK_DIR = REPO / "_t13_checklist"
WORK_DIR.mkdir(parents=True, exist_ok=True)

BATCH_CUTLIST = REPO / "test files" / "batch 2" / "output" / "cutlist.json"
TF2_CUTLIST = REPO / "test folder 2" / "output" / "cutlist.json"


def load_cutlist(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_golden_batch2() -> Dict[str, Any]:
    cmd = [
        str(REPO / ".venv" / "Scripts" / "python.exe"),
        str(REPO / "scripts" / "golden-render-suite.py"),
        "--json",
        "--skip-render",
        "--feature-emotion-led-cuts",
        "--feature-wave-8",
        "--feature-wave-9",
        "--feature-wave-10",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
        start = out.find("{")
        if start >= 0:
            return json.loads(out[start:])
    except Exception as e:
        return {"error": str(e)}
    return {"error": "no json output"}


def cutlist_checks(name: str, cutlist: Dict[str, Any]) -> Dict[str, Any]:
    slots = cutlist.get("slots", [])
    overlays = cutlist.get("overlays", [])
    effects_counter: Counter = Counter()
    trans_counter: Counter = Counter()
    story_beats_counter: Counter = Counter()
    intents_counter: Counter = Counter()
    texts: List[str] = []
    for s in slots:
        story_beats_counter[s.get("storyBeat")] += 1
        intents_counter[s.get("intent")] += 1
        trans_counter[s.get("transitionIn")] += 1
        trans_counter[s.get("transitionOut")] += 1
        for e in s.get("effects", []) or []:
            effects_counter[e.get("type") if isinstance(e, dict) else e] += 1
    for o in overlays:
        t = o.get("text") or o.get("kineticText") or ""
        if t:
            texts.append(t)

    narrative_mode = cutlist.get("narrativeMode")
    real_path_ratio = cutlist.get("realPathRatio")

    checks = {
        "narrative_mode_present": narrative_mode not in (None, ""),
        "narrative_mode": narrative_mode,
        "real_path_ratio": real_path_ratio,
        "real_path_ratio_ok": isinstance(real_path_ratio, (int, float)) and real_path_ratio >= 0.7,
        "slots_count": len(slots),
        "overlays_count": len(overlays),
        "story_beats": dict(story_beats_counter),
        "transitions": {k: v for k, v in trans_counter.items() if k},
        "effects": dict(effects_counter),
        "intents": dict(intents_counter),
        "sample_overlays": texts[:10],
        "transition_variety_ok": len({k for k in trans_counter if k and k.lower() not in ("hard_cut", "none")}) >= 2,
        "effects_present": len(effects_counter) > 0,
        "has_story_beats": any(b for b in story_beats_counter if b),
        "has_overlays": len(overlays) > 0,
    }

    # Wave 8: text animations / karaoke reveal / bundled fonts
    checks["wave_8_text_animations"] = len(overlays) > 0
    checks["wave_8_karaoke_reveal"] = any(
        (o.get("animation") or "").lower() == "karaoke_reveal"
        or (o.get("revealStyle") or "").lower().startswith("karaoke")
        or (o.get("style") or "").lower().startswith("karaoke")
        for o in overlays
    ) or any(
        (s.get("kineticTextAnimation") or s.get("kinetic_text_animation") or "").lower() == "karaoke_reveal"
        for s in slots
    )
    # We cannot cheaply verify bundled fonts from the cutlist alone; rely on golden suite for batch2.

    # Wave 9: emphasis words (uppercase/shouted overlays) and no word banks
    checks["wave_9_emphasis_words"] = any(
        t.isupper() and len(t.split()) <= 3 for t in texts
    )
    checks["wave_9_no_word_bank"] = not any(
        t.upper() in {
            "RISE", "UNBREAKABLE", "LEGEND", "VICTORY", "EMPIRE", "GLORY", "CONQUER",
            "UNSTOPPABLE", "FOREVER", "THRIVE", "DOMINATE", "ASCEND", "POWER",
            "CHAOS", "FURY", "IMPACT", "SHATTER", "BREAK", "FORCE", "STRIKE",
            "RUN", "HUNT", "CRASH", "BURN", "RECKLESS", "WAR",
            "GHOST", "BROKEN", "SILENCE", "FADE", "ALONE", "MEMORY", "REGRET",
            "VOID", "WASTED", "LOST", "GOODBYE", "HOLLOW", "DROWN",
            "NEON", "SYSTEM", "UPGRADE", "OVERRIDE", "GLITCH", "DATA", "SYNTH",
            "UPLOAD", "REBOOT", "PULSE", "WIRED", "CIRCUIT", "HACK",
        }
        for t in texts
    )

    # Wave 10: dedicated effect modules
    checks["wave_10_zoom_punch"] = any("zoom" in str(e).lower() or "punch" in str(e).lower() for e in effects_counter)
    checks["wave_10_vignette_crisis_victory"] = bool(
        effects_counter.get("vignette") or effects_counter.get("vignette_crisis") or effects_counter.get("vignette_victory")
    )
    checks["wave_10_hm_mvgd_hm"] = (
        effects_counter.get("hm_mvgd_hm", 0) > 0
        or any(
            "hm_mvgd_hm" in str(o.get("style", "")) or "hm_mvgd_hm" in str(o.get("text", ""))
            for o in overlays
        )
    )

    # Ticket 1 / emotion-led cuts
    checks["emotion_led_cuts_signaled"] = any(s.get("emotionMatchScore") is not None for s in slots)

    # Ticket 2 / SongMeaning arc selection
    checks["song_meaning_arc_selected"] = narrative_mode not in (None, "")

    # Ticket 3 / reference intent
    # The cutlist itself does not carry the reference-intent signal; we note it as build-only.
    checks["reference_intent_module_built"] = (
        REPO / "services" / "style-worker" / "src" / "style_worker" / "reference_intent.py"
    ).exists()

    return checks


def main() -> int:
    results: Dict[str, Any] = {"batch2": {}, "tf2": {}}

    print("=== Running golden suite for batch 2 ===", flush=True)
    results["batch2"]["golden_suite"] = run_golden_batch2()

    print("=== Cutlist checks for batch 2 ===", flush=True)
    batch_cutlist = load_cutlist(BATCH_CUTLIST)
    results["batch2"]["cutlist_checks"] = cutlist_checks("batch2", batch_cutlist)

    print("=== Cutlist checks for test folder 2 ===", flush=True)
    tf2_cutlist = load_cutlist(TF2_CUTLIST)
    results["tf2"]["cutlist_checks"] = cutlist_checks("tf2", tf2_cutlist)

    json_path = WORK_DIR / "feature_checklist.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"JSON -> {json_path}", flush=True)

    # Markdown report
    lines: List[str] = [
        "# T.13 Feature Checklist",
        "",
        f"Generated: {__import__('time').strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "This report cross-checks every major feature built in Waves 5X-10 and Tickets 0-3",
        "against the two demo renders.",
        "",
        "## Summary",
        "",
    ]

    for fixture, data in results.items():
        title = "Batch 2 (Cyberpunk AMV)" if fixture == "batch2" else "Test Folder 2 (Kimi No Nawa / Sparkle)"
        lines.append(f"### {title}")
        cc = data.get("cutlist_checks", {})
        lines.append(f"- narrativeMode: `{cc.get('narrative_mode')}`")
        lines.append(f"- realPathRatio: `{cc.get('real_path_ratio')}`")
        lines.append(f"- slots: {cc.get('slots_count')} | overlays: {cc.get('overlays_count')}")
        lines.append(f"- transitions: `{cc.get('transitions')}`")
        lines.append(f"- effects: `{cc.get('effects')}`")
        lines.append(f"- story beats: `{cc.get('story_beats')}`")
        lines.append("")

    lines.append("## Batch 2 Golden Suite Detail")
    lines.append("")
    gs = results["batch2"].get("golden_suite", {})
    if gs.get("error"):
        lines.append(f"**Suite error:** {gs['error']}")
    else:
        lines.append(f"- passed: {gs.get('passed')}")
        lines.append(f"- failed: {gs.get('failed')}")
        lines.append(f"- skipped: {gs.get('skipped')}")
        lines.append("")
        lines.append("| Criterion | Passed | Value | Threshold | Detail |")
        lines.append("|-----------|--------|-------|-----------|--------|")
        for c in gs.get("criteria", []):
            lines.append(
                f"| {c.get('name')} | {'PASS' if c.get('passed') else 'FAIL'} | "
                f"{c.get('value')} | {c.get('threshold')} | {c.get('detail', '')} |"
            )

    lines.append("")
    lines.append("## Per-Feature Build vs Shipped")
    lines.append("")

    feature_rows = [
        ("SongMeaning narrative arc selection", "song_meaning_arc_selected", True),
        ("Emotion-led cut placement", "emotion_led_cuts_signaled", True),
        ("Real-path ratio >= 0.7", "real_path_ratio_ok", True),
        ("Transition variety (>=2 non-hard-cut types)", "transition_variety_ok", True),
        ("Effects present in cutlist", "effects_present", True),
        ("Story beats assigned", "has_story_beats", True),
        ("Text overlays present", "has_overlays", True),
        ("Wave 8 text animations", "wave_8_text_animations", True),
        ("Wave 8 karaoke reveal", "wave_8_karaoke_reveal", False),
        ("Wave 9 emphasis words", "wave_9_emphasis_words", True),
        ("Wave 9 no word banks", "wave_9_no_word_bank", True),
        ("Wave 10 zoom/punch effects", "wave_10_zoom_punch", True),
        ("Wave 10 vignette on crisis/victory", "wave_10_vignette_crisis_victory", True),
        ("Wave 10 hm_mvgd_hm shipped", "wave_10_hm_mvgd_hm", False),
        ("Reference intent module built", "reference_intent_module_built", False),
    ]

    lines.append("| Feature | Batch 2 | Test Folder 2 | Notes |")
    lines.append("|---------|---------|---------------|-------|")
    for label, key, required in feature_rows:
        b = results["batch2"].get("cutlist_checks", {}).get(key)
        t = results["tf2"].get("cutlist_checks", {}).get(key)
        status_b = "YES" if b else ("NO" if required else "n/a")
        status_t = "YES" if t else ("NO" if required else "n/a")
        note = "required" if required else "optional/build-only"
        lines.append(f"| {label} | {status_b} | {status_t} | {note} |")

    lines.append("")
    lines.append("## Missing / Fix List")
    lines.append("")
    missing: List[str] = []
    for label, key, required in feature_rows:
        if not required:
            continue
        for fixture, title in [("batch2", "Batch 2"), ("tf2", "Test Folder 2")]:
            val = results[fixture].get("cutlist_checks", {}).get(key)
            if not val:
                missing.append(f"- [{title}] {label} (`{key}`) is missing or failed.")
    if gs.get("failed"):
        for c in gs.get("criteria", []):
            if not c.get("passed"):
                missing.append(f"- [Batch 2 golden] `{c.get('name')}` failed: {c.get('detail', '')}")
    if missing:
        lines.extend(missing)
    else:
        lines.append("- No required features missing in either fixture.")

    md = "\n".join(lines)
    (WORK_DIR / "T13_FEATURE_CHECKLIST.md").write_text(md, encoding="utf-8")
    (REPO / "T13_FEATURE_CHECKLIST.md").write_text(md, encoding="utf-8")
    print(f"MARKDOWN -> {WORK_DIR / 'T13_FEATURE_CHECKLIST.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
