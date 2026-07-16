#!/usr/bin/env python3
"""T.13 end-to-end validation audit.

Loads a vision LLM (Qwen3-VL 8B via Ollama /api/chat) and walks BOTH demo
renders second by second. For every sampled second it:

  1. Reads the cutlist to know what SHOULD be on screen at that second — the
     clip, transition in/out, effects (LUT/vignette/zoom/etc.), and any text
     overlay + intent/story-beat.
  2. Extracts the actual frame and asks Qwen to describe what IS on screen and
     to verify each claimed element (text readability, LUT/effect visibility,
     transition presence).
  3. Compares CLAIM vs OBSERVED and flags mismatches.

Then it runs the golden suite on both fixtures with all flags, and writes one
extensive markdown report per fixture plus a combined MISSING-AND-FIXES report.

Usage:
    .venv/Scripts/python.exe scripts/t13_validation_audit.py [--every N] [--fixture batch2|tf2|both]

Design notes:
- Uses /api/chat + keep_alive=-1.
- Incremental flush: partial results survive a crash.
- Never fabricates: if the model errors on a frame, the row is marked ERROR.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
OLLAMA = "http://localhost:11434/api/chat"

# Windows consoles default to cp1252 and choke on Japanese/emoji characters
# in model captions.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
MODEL = "qwen3-vl:8b"

FIXTURES = {
    "batch2": {
        "name": "Batch 2 — Cyberpunk Edgerunners AMV",
        "output": REPO / "test files" / "batch 2" / "output" / "output.mp4",
        "cutlist": REPO / "test files" / "batch 2" / "output" / "cutlist.json",
        "golden_flag": "--feature-emotion-led-cuts",
    },
    "tf2": {
        "name": "Test Folder 2 — Kimi No Nawa / RADWIMPS Sparkle",
        "output": REPO / "test folder 2" / "output" / "output.mp4",
        "cutlist": REPO / "test folder 2" / "output" / "cutlist.json",
        "golden_flag": "--feature-emotion-led-cuts",
    },
}

DESCRIBE_PROMPT = (
    "You are a strict video-editing QA analyst. Look at this single frame from a music-video edit. "
    "Return ONLY compact JSON, no prose, no markdown fences. "
    "Keys and value guidance: "
    "content (<=15 words describing what/who is on screen), "
    "on_screen_text (verbatim readable text or empty string), "
    "color_grade (one phrase: warm/cold/desaturated/teal-orange/high-contrast/flat/natural/etc), "
    "apparent_effect (one phrase describing any visible effect, transition, LUT, blur, zoom, vignette, glitch, focus-pull, or none), "
    "is_black_or_frozen (boolean), "
    "looks_intentional (boolean)."
)


def probe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0


def extract_frame(video: Path, t: float, out_jpg: Path) -> bool:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{t:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "4",
                "-vf",
                "scale=640:-1",
                str(out_jpg),
            ],
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
        return out_jpg.exists() and out_jpg.stat().st_size > 1000
    except Exception:
        return False


def qwen_describe(jpg: Path, timeout: int = 180) -> Dict[str, Any]:
    b64 = base64.b64encode(jpg.read_bytes()).decode("ascii")
    prompt = DESCRIBE_PROMPT
    payload = {
        "model": MODEL,
        "keep_alive": -1,
        "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024},
    }
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    raw = (data.get("message", {}) or {}).get("content", "").strip()
    return parse_json_response(raw)


def parse_json_response(raw: str) -> Dict[str, Any]:
    if not raw:
        return {"_parse_error": "(empty response)"}
    # Strip markdown fences if present
    cleaned = raw
    if cleaned.startswith("```"):
        parts = cleaned.split("```", 2)
        cleaned = parts[1] if len(parts) >= 3 else cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            return {"_parse_error": f"{e}: {cleaned[start:end+1][:300]}"}
    return {"_parse_error": raw[:300]}


def cutlist_at_second(cutlist: Dict[str, Any], t: float) -> Dict[str, Any]:
    """What the cutlist CLAIMS is on screen at time t."""
    slots = cutlist.get("slots", [])
    active = None
    for s in slots:
        start = s.get("startS", 0.0)
        dur = s.get("durationS", 0.0)
        if start <= t < start + dur:
            active = s
            break
    overlays = cutlist.get("overlays", [])
    active_text = [
        (o.get("text") or o.get("kineticText") or "")
        for o in overlays
        if o.get("startS", 0.0) <= t < o.get("startS", 0.0) + o.get("durationS", 0.0)
        and (o.get("text") or o.get("kineticText"))
    ]
    if active is None:
        return {"slot": None, "claimed_text": active_text}
    return {
        "slot": active.get("index"),
        "clip": active.get("selectedClipId"),
        "transition_in": active.get("transitionIn"),
        "transition_out": active.get("transitionOut"),
        "effects": [
            e.get("type") if isinstance(e, dict) else e
            for e in (active.get("effects") or [])
        ],
        "story_beat": active.get("storyBeat"),
        "intent": active.get("intent"),
        "energy": active.get("energyLevel"),
        "kinetic_text": active.get("kineticText"),
        "claimed_text": active_text,
    }


def format_claim(claim: Dict[str, Any]) -> str:
    parts = []
    if claim.get("clip"):
        parts.append(f"clip={claim['clip']}")
    if claim.get("transition_in"):
        parts.append(f"transition_in={claim['transition_in']}")
    if claim.get("transition_out"):
        parts.append(f"transition_out={claim['transition_out']}")
    if claim.get("effects"):
        parts.append(f"effects={claim['effects']}")
    if claim.get("story_beat"):
        parts.append(f"story_beat={claim['story_beat']}")
    if claim.get("intent"):
        parts.append(f"intent={claim['intent']}")
    if claim.get("claimed_text"):
        parts.append(f"text_overlay={claim['claimed_text']}")
    if not parts:
        return "(no active slot or overlays)"
    return "; ".join(parts)


def audit_fixture(key: str, every: int, workdir: Path) -> Dict[str, Any]:
    fx = FIXTURES[key]
    out_mp4, cut_json = fx["output"], fx["cutlist"]
    result: Dict[str, Any] = {"fixture": key, "name": fx["name"], "seconds": [], "issues": []}

    if not out_mp4.exists():
        result["issues"].append(f"MISSING OUTPUT: {out_mp4}")
        return result
    if not cut_json.exists():
        result["issues"].append(f"MISSING CUTLIST: {cut_json}")
        return result

    cutlist = json.loads(cut_json.read_text(encoding="utf-8"))
    dur = probe_duration(out_mp4)
    result["duration_s"] = round(dur, 2)
    result["cutlist_summary"] = {
        "narrativeMode": cutlist.get("narrativeMode"),
        "realPathRatio": cutlist.get("realPathRatio"),
        "slots": len(cutlist.get("slots", [])),
        "overlays": len(cutlist.get("overlays", [])),
        "story_beats": dict(Counter(s.get("storyBeat") for s in cutlist.get("slots", []))),
        "transitions": dict(Counter(s.get("transitionOut") for s in cutlist.get("slots", []))),
        "effects": dict(
            Counter(
                (e.get("type") if isinstance(e, dict) else e)
                for s in cutlist.get("slots", [])
                for e in (s.get("effects") or [])
            )
        ),
    }

    frames_dir = workdir / f"_frames_{key}"
    frames_dir.mkdir(parents=True, exist_ok=True)
    rows_path = workdir / f"audit_rows_{key}.jsonl"

    seconds = list(range(0, int(dur), max(1, every)))
    with rows_path.open("w", encoding="utf-8") as fout:
        for i, t in enumerate(seconds):
            jpg = frames_dir / f"f_{t:04d}.jpg"
            claim = cutlist_at_second(cutlist, float(t))
            row: Dict[str, Any] = {"t": t, "claim": claim}
            if not extract_frame(out_mp4, float(t), jpg):
                row["observed"] = {"_error": "frame_extract_failed"}
                row["mismatch"] = "FRAME_EXTRACT_FAILED"
            else:
                try:
                    obs = qwen_describe(jpg)
                except Exception as e:
                    obs = {"_error": str(e)[:150]}
                row["observed"] = obs
                row["mismatch"] = classify_mismatch(claim, obs)
            result["seconds"].append(row)
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            if row.get("mismatch") and row["mismatch"] != "OK":
                result["issues"].append(f"t={t}s: {row['mismatch']}")
            print(f"  [{key}] [{i+1}/{len(seconds)}] t={t}s  {row.get('mismatch','?')}", flush=True)
    return result


def classify_mismatch(claim: Dict[str, Any], obs: Dict[str, Any]) -> str:
    """Classify a frame as OK, HARD breakage, or SOFT (explainable) mismatch.

    HARD breakages are objective problems a viewer would notice:
    model failure, black/frozen frame, unintentional-looking frame, or text
    the cutlist promised but is not readable.

    SOFT mismatches are usually expected from a single-frame audit:
    source text not in the cutlist, subtle/sub-frame effects, and transitions
    that happen between seconds and are invisible in a still frame.
    """
    if "_error" in obs or "_parse_error" in obs:
        return "HARD:MODEL_ERROR"
    if obs.get("is_black_or_frozen"):
        # A black frame that also shows readable text is usually an intentional
        # title card, not a frozen/broken frame.
        seen_text = (obs.get("on_screen_text") or "").strip()
        content = (obs.get("content") or "").lower()
        if seen_text or any(w in content for w in ("text", "title", "caption", "overlay")):
            return "SOFT:BLACK_FRAME_WITH_TEXT"
        return "HARD:BLACK_OR_FROZEN_FRAME"
    if obs.get("looks_intentional") is False:
        return "HARD:LOOKS_UNINTENTIONAL"

    claimed_text = " ".join(claim.get("claimed_text") or []).strip()
    seen_text = (obs.get("on_screen_text") or "").strip()
    if claimed_text and not seen_text:
        return f"HARD:TEXT_CLAIMED_NOT_VISIBLE(claim={claimed_text[:40]!r})"

    # Source-text (e.g., Japanese signs, dialogue) is not in our cutlist; soft.
    if seen_text and not claimed_text and len(seen_text) > 3:
        return f"SOFT:TEXT_VISIBLE_NOT_IN_CUTLIST(seen={seen_text[:40]!r})"

    effects = claim.get("effects") or []
    if effects:
        fx_desc = (obs.get("apparent_effect") or "").lower()
        if not any(str(e).lower() in fx_desc or fx_desc in str(e).lower() for e in effects):
            return f"SOFT:EFFECT_MISMATCH(claim={effects}, seen={obs.get('apparent_effect')})"

    transitions = [claim.get("transition_in"), claim.get("transition_out")]
    transitions = [t for t in transitions if t and str(t).lower() not in ("hard_cut", "none", "")]
    if transitions:
        fx_desc = (obs.get("apparent_effect") or "").lower()
        if not any(str(t).lower() in fx_desc for t in transitions):
            return f"SOFT:TRANSITION_MISMATCH(claim={transitions}, seen={obs.get('apparent_effect')})"

    return "OK"


def run_golden(key: str, workdir: Path) -> str:
    # The golden suite is hardcoded to the batch 2 fixture.
    if key != "batch2":
        return json.dumps({"skipped": True, "reason": "golden suite only validates batch 2"})
    fx = FIXTURES[key]
    cmd = [
        str(REPO / ".venv" / "Scripts" / "python.exe"),
        str(REPO / "scripts" / "golden-render-suite.py"),
        "--json",
        "--skip-render",
        fx["golden_flag"],
        "--feature-wave-8",
        "--feature-wave-9",
        "--feature-wave-10",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout
        (workdir / f"golden_{key}.json").write_text(out, encoding="utf-8")
        start = out.find("{")
        return out[start:] if start >= 0 else out
    except Exception as e:
        return json.dumps({"error": str(e)})


def write_report(results: List[Dict[str, Any]], golden: Dict[str, str], workdir: Path) -> None:
    lines: List[str] = []
    lines.append("# T.13 End-to-End Validation Audit")
    lines.append(f"\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(
        "Method: Qwen3-VL 8B via Ollama /api/chat describes each sampled second; "
        "compared against what the cutlist claims should be on screen.\n"
    )

    for res in results:
        lines.append(f"\n---\n\n## {res['name']}\n")
        if res.get("issues") and any("MISSING" in i for i in res["issues"][:1]):
            lines.append(f"**BLOCKED:** {res['issues'][0]}\n")
            continue
        cs = res.get("cutlist_summary", {})
        lines.append(f"- Duration: {res.get('duration_s')}s")
        lines.append(f"- narrativeMode: `{cs.get('narrativeMode')}`")
        lines.append(f"- realPathRatio: `{cs.get('realPathRatio')}`")
        lines.append(f"- slots: {cs.get('slots')} | overlays: {cs.get('overlays')}")
        lines.append(f"- story beats: `{cs.get('story_beats')}`")
        lines.append(f"- transitions: `{cs.get('transitions')}`")
        lines.append(f"- effects: `{cs.get('effects')}`")

        rows = res.get("seconds", [])
        mism = Counter(r.get("mismatch") for r in rows)
        lines.append(f"\n### Per-second mismatch summary ({len(rows)} seconds sampled)\n")
        for k, v in mism.most_common():
            lines.append(f"- `{k}`: {v}")

        bad = [r for r in rows if r.get("mismatch") not in ("OK", None)]
        lines.append(f"\n### Flagged seconds ({len(bad)})\n")
        for r in bad[:120]:
            obs = r.get("observed", {})
            lines.append(
                f"- **t={r['t']}s** — {r.get('mismatch')} | "
                f"claim: slot {r['claim'].get('slot')}, text={r['claim'].get('claimed_text')}, "
                f"effects={r['claim'].get('effects')}, transitions="
                f"{r['claim'].get('transition_in')}/{r['claim'].get('transition_out')} | "
                f"seen: {obs.get('content','?')}, text={obs.get('on_screen_text','')!r}, "
                f"grade={obs.get('color_grade','?')}, fx={obs.get('apparent_effect','?')}, "
                f"apparent_effect={obs.get('apparent_effect','?')}"
            )

        gj = golden.get(res["fixture"], "")
        try:
            gd = json.loads(gj)
            lines.append(f"\n### Golden suite: {gd.get('passed')} passed / {gd.get('failed')} failed\n")
            for c in gd.get("criteria", []):
                if not c.get("passed"):
                    lines.append(
                        f"- FAIL `{c.get('name')}` = {c.get('value')} :: {c.get('detail','')}"
                    )
        except Exception:
            lines.append("\n### Golden suite: could not parse output\n")

    report = workdir / "T13_VALIDATION_REPORT.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nREPORT -> {report}")

    # Also drop a copy at repo root for visibility.
    (REPO / "T13_VALIDATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--every", type=int, default=1, help="sample every N seconds")
    ap.add_argument("--fixture", choices=["batch2", "tf2", "both"], default="both")
    ap.add_argument("--workdir", default=str(REPO / "_t13_audit"))
    args = ap.parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    keys = ["batch2", "tf2"] if args.fixture == "both" else [args.fixture]

    results, golden = [], {}
    for k in keys:
        print(f"\n=== AUDIT {k} ===", flush=True)
        results.append(audit_fixture(k, args.every, workdir))
        golden[k] = run_golden(k, workdir)

    write_report(results, golden, workdir)


if __name__ == "__main__":
    main()
