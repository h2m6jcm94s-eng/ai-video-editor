// Shared data for the Stencil landing page.
// Ported from the design handoff (cinema-data.jsx) — a 30-second demo edit at 124 BPM.
// Image references are bare filenames resolved through `asset()` in ./images.

export const DEMO_DURATION = 30.0; // seconds
export const DEMO_BPM = 124;
export const BEATS_PER_SEC = DEMO_BPM / 60; // ~2.07 bps

// Generated beat times across the demo.
export const BEAT_TIMES: number[] = (() => {
  const out: number[] = [];
  for (let t = 0; t < DEMO_DURATION; t += 1 / BEATS_PER_SEC) {
    out.push(t);
  }
  return out;
})();

export interface Section {
  name: string;
  start: number;
  end: number;
  color: string;
}

export const SECTIONS: Section[] = [
  { name: "intro", start: 0, end: 5.5, color: "#3a3530" },
  { name: "verse", start: 5.5, end: 12.0, color: "#2a4a52" },
  { name: "prechorus", start: 12.0, end: 15.5, color: "#5a3a2a" },
  { name: "drop", start: 15.5, end: 24.0, color: "#8a3a1a" },
  { name: "outro", start: 24.0, end: 30.0, color: "#3a3530" },
];

export interface RefShot {
  start: number;
  end: number;
  type: string;
  motion: string;
  tone: string;
  subject: string;
}

// Reference shots — what we parsed from the reference video.
export const REF_SHOTS: RefShot[] = [
  { start: 0.0, end: 1.95, type: "wide", motion: "static", tone: "#1d3540", subject: "skyline establish" },
  { start: 1.95, end: 3.9, type: "medium", motion: "push", tone: "#d4814c", subject: "subject reveal" },
  { start: 3.9, end: 5.5, type: "close", motion: "static", tone: "#e8a872", subject: "face" },
  { start: 5.5, end: 7.5, type: "wide", motion: "tracking", tone: "#1e4248", subject: "movement" },
  { start: 7.5, end: 8.95, type: "medium", motion: "static", tone: "#3a6770", subject: "action" },
  { start: 8.95, end: 10.4, type: "insert", motion: "static", tone: "#1a2830", subject: "object" },
  { start: 10.4, end: 12.0, type: "close", motion: "push", tone: "#dc6f3a", subject: "face" },
  { start: 12.0, end: 13.0, type: "wide", motion: "whip", tone: "#5a2e1a", subject: "build" },
  { start: 13.0, end: 14.0, type: "medium", motion: "static", tone: "#c97648", subject: "build" },
  { start: 14.0, end: 14.8, type: "close", motion: "static", tone: "#e89160", subject: "build" },
  { start: 14.8, end: 15.5, type: "insert", motion: "snap", tone: "#1a2228", subject: "tension" },
  // DROP — fast cuts
  { start: 15.5, end: 16.0, type: "wide", motion: "shake", tone: "#9d3a14", subject: "drop" },
  { start: 16.0, end: 16.5, type: "close", motion: "shake", tone: "#f08040", subject: "drop" },
  { start: 16.5, end: 17.0, type: "medium", motion: "whip", tone: "#a64020", subject: "drop" },
  { start: 17.0, end: 17.5, type: "wide", motion: "ramp", tone: "#dc6428", subject: "drop" },
  { start: 17.5, end: 18.5, type: "close", motion: "static", tone: "#1d3848", subject: "beat" },
  { start: 18.5, end: 19.5, type: "medium", motion: "tracking", tone: "#e87440", subject: "action" },
  { start: 19.5, end: 20.0, type: "insert", motion: "freeze", tone: "#0a1218", subject: "accent" },
  { start: 20.0, end: 21.0, type: "wide", motion: "static", tone: "#1e3a44", subject: "scale" },
  { start: 21.0, end: 22.0, type: "close", motion: "push", tone: "#e8884c", subject: "face" },
  { start: 22.0, end: 23.0, type: "medium", motion: "shake", tone: "#a04020", subject: "release" },
  { start: 23.0, end: 24.0, type: "wide", motion: "ramp", tone: "#dc6c30", subject: "release" },
  { start: 24.0, end: 27.0, type: "wide", motion: "static", tone: "#1a3038", subject: "settle" },
  { start: 27.0, end: 30.0, type: "close", motion: "static", tone: "#3a2820", subject: "outro" },
];

export interface UserClip {
  id: string;
  label: string;
  type: string;
  motion: string;
  duration: number;
  grad: string;
}

// User clip library — what was uploaded. Rendered as CSS-art gradient cards.
export const USER_CLIPS: UserClip[] = [
  {
    id: "C01",
    label: "rooftop wide",
    type: "wide",
    motion: "static",
    duration: 8.2,
    grad: "linear-gradient(135deg, #5a7a8c 0%, #2e4858 100%)",
  },
  {
    id: "C02",
    label: "portrait",
    type: "close",
    motion: "static",
    duration: 4.1,
    grad: "linear-gradient(160deg, #8c6a52 0%, #3e2e26 100%)",
  },
  {
    id: "C03",
    label: "walk-down",
    type: "medium",
    motion: "tracking",
    duration: 6.0,
    grad: "linear-gradient(120deg, #6e8270 0%, #2a3a32 100%)",
  },
  {
    id: "C04",
    label: "hand detail",
    type: "insert",
    motion: "static",
    duration: 3.4,
    grad: "linear-gradient(200deg, #948072 0%, #3a322a 100%)",
  },
  {
    id: "C05",
    label: "city run",
    type: "wide",
    motion: "shake",
    duration: 7.6,
    grad: "linear-gradient(150deg, #b06a3a 0%, #4a2618 100%)",
  },
  {
    id: "C06",
    label: "face / push",
    type: "close",
    motion: "push",
    duration: 3.0,
    grad: "linear-gradient(170deg, #ce8c5e 0%, #4e3624 100%)",
  },
  {
    id: "C07",
    label: "doorway",
    type: "medium",
    motion: "whip",
    duration: 2.4,
    grad: "linear-gradient(110deg, #6c7a8e 0%, #2e3848 100%)",
  },
  {
    id: "C08",
    label: "drink / pour",
    type: "insert",
    motion: "snap",
    duration: 2.2,
    grad: "linear-gradient(190deg, #ae6c44 0%, #44241a 100%)",
  },
  {
    id: "C09",
    label: "crowd",
    type: "wide",
    motion: "shake",
    duration: 5.5,
    grad: "linear-gradient(135deg, #8a4828 0%, #3a1c10 100%)",
  },
  {
    id: "C10",
    label: "reflection",
    type: "close",
    motion: "static",
    duration: 4.0,
    grad: "linear-gradient(180deg, #4e6e7c 0%, #1c2a30 100%)",
  },
];

export interface Assignment {
  shotIdx: number;
  clipId: string;
  confidence: number;
}

// Slot → clip assignment, one per ref shot. Pre-computed so the demo is coherent.
export const ASSIGNMENTS: Assignment[] = REF_SHOTS.map((shot, i) => {
  const candidates = USER_CLIPS.filter((c) => c.type === shot.type);
  const pick = candidates[i % Math.max(1, candidates.length)] || USER_CLIPS[i % USER_CLIPS.length];
  const conf = 0.62 + ((i * 7) % 36) / 100;
  return { shotIdx: i, clipId: pick.id, confidence: Math.min(0.98, conf) };
});

export interface PipelineStage {
  id: string;
  ix: string;
  name: string;
  subtitle: string;
  latency: string;
  headline: string;
  body: string;
  keys: { k: string; v: string }[];
}

export const PIPELINE: PipelineStage[] = [
  {
    id: "ingest",
    ix: "01",
    name: "Ingest",
    subtitle: "shot · beat · energy",
    latency: "~14s",
    headline: "Parse the reference into a structured score.",
    body: "TransNet V2 finds every shot boundary. allin1 emits beats, downbeats, sections — verse, prechorus, drop, outro. librosa fills in the energy curve. The reference becomes a beat-anchored timeline you can read like sheet music.",
    keys: [
      { k: "Shot detection", v: "TransNet V2" },
      { k: "Beat / downbeat", v: "allin1" },
      { k: "Energy", v: "librosa RMS" },
      { k: "Sections", v: "verse · drop · outro" },
    ],
  },
  {
    id: "style",
    ix: "02",
    name: "Style",
    subtitle: "grade · text · effects",
    latency: "~9s",
    headline: "Lift the color, typography, and motion grammar.",
    body: "color-matcher fits a 33-cube LUT from the reference's frames. PaddleOCR finds every overlay; Gemini 2.5 Pro returns font weight, color, and animation per overlay. RAFT-flow plus affine decomposition catalogs every push, whip, shake, freeze, and ramp.",
    keys: [
      { k: "Grade", v: "color-matcher → .cube" },
      { k: "Overlays", v: "PaddleOCR + Gemini" },
      { k: "Motion class", v: "RAFT + affine fit" },
      { k: "Transitions", v: "TransNet gradual head" },
    ],
  },
  {
    id: "embed",
    ix: "03",
    name: "Embed",
    subtitle: "user library",
    latency: "~22s",
    headline: "Index your clips into a searchable space.",
    body: "Every clip you upload is segmented and embedded with Twelve Labs Marengo 3 — 512-dim multimodal vectors that understand 'tracking shot,' 'close-up of a face,' 'low-light interior.' Stored in Qdrant for near-instant retrieval against the reference's slot prompts.",
    keys: [
      { k: "Embeddings", v: "Marengo 3 — 512d" },
      { k: "Shot type", v: "Gemini 2.5 Flash" },
      { k: "Quality", v: "LAION aesthetic + MUSIQ" },
      { k: "Index", v: "Qdrant HNSW" },
    ],
  },
  {
    id: "cutlist",
    ix: "04",
    name: "Cut-list",
    subtitle: "the contract",
    latency: "~6s",
    headline: "Compose the edit as a single, versioned contract.",
    body: "Claude Sonnet 4.6 receives the reference's score and your clip library, then emits a JSON cut-list — globals, sections, per-slot shot type, motion, energy, transition in/out, overlays. Tool-forced output, schema-validated. This is the moat: every model upstream and renderer downstream is replaceable around it.",
    keys: [
      { k: "Model", v: "Claude Sonnet 4.6" },
      { k: "Schema", v: "JSON · enum-gated" },
      { k: "Prompt", v: "cached @ 90% off" },
      { k: "Validator", v: "AJV + re-prompt" },
    ],
  },
  {
    id: "match",
    ix: "05",
    name: "Match",
    subtitle: "rank · diversify",
    latency: "~3s",
    headline: "Score every clip against every slot, then diversify.",
    body: "A weighted score across semantic similarity, shot-type confidence, aesthetic, motion fit, and duration. Greedy MMR penalizes repetition; faces don't repeat in adjacent slots unless continuity demands it. Top-3 surfaced per slot in Assisted mode.",
    keys: [
      { k: "Weights", v: "0.40 / 0.20 / 0.15 / 0.15 / 0.10" },
      { k: "Diversity", v: "MMR · −0.25" },
      { k: "Constraints", v: "no-repeat · 6s window" },
      { k: "Confidence", v: "σ(top1 − top4)" },
    ],
  },
  {
    id: "render",
    ix: "06",
    name: "Render",
    subtitle: "ffmpeg · LUT · drawtext",
    latency: "~90s",
    headline: "Compile to a frame-accurate cut.",
    body: "PyAV probes; FFmpeg renders. trim+setpts gives frame-exact cuts on the beat grid. lut3d applies the reference's grade. xfade for soft transitions, drawtext for overlays, h264_nvenc for the master. 720p first; on-demand 4K upscale via Real-ESRGAN or Topaz.",
    keys: [
      { k: "Engine", v: "FFmpeg + PyAV" },
      { k: "Grade", v: "lut3d 33³" },
      { k: "Encode", v: "h264_nvenc · CRF 18" },
      { k: "Upscale", v: "Real-ESRGAN / Topaz" },
    ],
  },
];

export interface Tier {
  n: string;
  name: string;
  accent?: boolean;
  headline: string;
  render: string;
  cost: string;
  features: { on: boolean; t: string }[];
}

export const TIERS: Tier[] = [
  {
    n: "Tier 01",
    name: "Cut timing",
    headline: "Beat-synced cuts, hard transitions.",
    render: "~1–2 min",
    cost: "$0.39",
    features: [
      { on: true, t: "Shot count + section pacing" },
      { on: true, t: "Beat / downbeat alignment" },
      { on: true, t: "Hard cuts" },
      { on: false, t: "Color grade" },
      { on: false, t: "Text overlays" },
      { on: false, t: "Motion + effects" },
    ],
  },
  {
    n: "Tier 02",
    name: "+ Color grade",
    headline: "Tier 01 plus the reference's LUT.",
    render: "~2–3 min",
    cost: "$0.44",
    features: [
      { on: true, t: "Shot count + section pacing" },
      { on: true, t: "Beat / downbeat alignment" },
      { on: true, t: "Soft transitions (xfade)" },
      { on: true, t: "33³ LUT, applied at 30–70%" },
      { on: false, t: "Text overlays" },
      { on: false, t: "Motion + effects" },
    ],
  },
  {
    n: "Tier 03",
    name: "+ Text overlays",
    headline: "Add the reference's kinetic typography.",
    render: "~2–3 min",
    cost: "$0.51",
    features: [
      { on: true, t: "Cut + grade tiers" },
      { on: true, t: "Title cards, kinetic captions" },
      { on: true, t: "Per-overlay font, color, animation" },
      { on: true, t: "Copy editable before render" },
      { on: false, t: "Motion + effects" },
      { on: false, t: "Speed ramps + freeze frames" },
    ],
  },
  {
    n: "Tier 04",
    name: "Full transfer",
    accent: true,
    headline: "Camera motion, shakes, ramps, freezes — everything.",
    render: "~3–4 min",
    cost: "$0.78",
    features: [
      { on: true, t: "All prior tiers" },
      { on: true, t: "Push, pan, tilt, whip" },
      { on: true, t: "Handheld + gimbal emulation" },
      { on: true, t: "Speed ramps · freeze frames" },
      { on: true, t: "Per-shot effect intent matching" },
      { on: true, t: "Confidence-gated — flags low-fidelity slots" },
    ],
  },
];

export interface Competitor {
  name: string;
  ref: string;
  lib: string;
  song: string;
  grade: string;
  text: string;
  motion: string;
  us?: boolean;
}

export const COMPETITORS: Competitor[] = [
  { name: "STENCIL", ref: "✓", lib: "✓", song: "✓", grade: "✓", text: "✓", motion: "✓", us: true },
  { name: "Runway Gen-4", ref: "~", lib: "✗", song: "✗", grade: "✗", text: "✗", motion: "✓" },
  { name: "Pika 2.2", ref: "✗", lib: "✗", song: "✗", grade: "✗", text: "✗", motion: "✗" },
  { name: "Opus Clip", ref: "✗", lib: "✓", song: "✗", grade: "✗", text: "✓", motion: "✗" },
  { name: "CapCut AI", ref: "✗", lib: "✓", song: "✓", grade: "~", text: "✓", motion: "~" },
  { name: "Firefly Quick Cut", ref: "✗", lib: "✓", song: "~", grade: "✗", text: "~", motion: "✗" },
  { name: "Descript", ref: "✗", lib: "✓", song: "✗", grade: "✗", text: "✓", motion: "✗" },
  { name: "Submagic", ref: "✗", lib: "✓", song: "✗", grade: "✗", text: "✓", motion: "✗" },
];

export const COMPETITOR_COLS: { k: keyof Competitor; label: string }[] = [
  { k: "ref", label: "Reference video → style" },
  { k: "lib", label: "User clip library" },
  { k: "song", label: "Custom song" },
  { k: "grade", label: "Color grade transfer" },
  { k: "text", label: "Overlay parsing" },
  { k: "motion", label: "Motion / effects" },
];

export interface Transition {
  id: string;
  name: string;
  count: number;
  desc: string;
}

export const TRANSITIONS: Transition[] = [
  { id: "hard", name: "Hard cut", count: 11, desc: "Frame-accurate splice on the downbeat." },
  { id: "whip", name: "Whip pan", count: 4, desc: "Motion-blurred horizontal sweep." },
  { id: "crosszoom", name: "Cross-zoom", count: 3, desc: "Zoom-in, dissolve, zoom-out — Sam Kolder energy." },
  { id: "glitch", name: "Glitch", count: 2, desc: "RGB split + frame-shift on impact frames." },
  { id: "ramp", name: "Speed ramp", count: 2, desc: "100% → 25% → 100% across the cut." },
  { id: "freeze", name: "Freeze frame", count: 2, desc: "Held frame, then resumes — drop accent." },
];

export const TRANSITION_AT: { afterShotIdx: number; type: string }[] = [
  { afterShotIdx: 0, type: "hard" },
  { afterShotIdx: 1, type: "crosszoom" },
  { afterShotIdx: 2, type: "hard" },
  { afterShotIdx: 3, type: "whip" },
  { afterShotIdx: 4, type: "hard" },
  { afterShotIdx: 5, type: "hard" },
  { afterShotIdx: 6, type: "ramp" },
  { afterShotIdx: 7, type: "whip" },
  { afterShotIdx: 8, type: "hard" },
  { afterShotIdx: 9, type: "glitch" },
  { afterShotIdx: 10, type: "hard" },
  { afterShotIdx: 11, type: "whip" },
  { afterShotIdx: 12, type: "crosszoom" },
  { afterShotIdx: 13, type: "glitch" },
  { afterShotIdx: 14, type: "hard" },
  { afterShotIdx: 15, type: "ramp" },
  { afterShotIdx: 16, type: "hard" },
  { afterShotIdx: 17, type: "freeze" },
  { afterShotIdx: 18, type: "hard" },
  { afterShotIdx: 19, type: "crosszoom" },
  { afterShotIdx: 20, type: "whip" },
  { afterShotIdx: 21, type: "hard" },
  { afterShotIdx: 22, type: "freeze" },
];

export interface Layer {
  id: string;
  name: string;
  short: string;
  desc: string;
  locked?: boolean;
  cost: number;
  time: number;
  detail: string;
}

export const LAYERS: Layer[] = [
  {
    id: "cuts",
    name: "Cuts & timing",
    short: "REF/CUT",
    desc: "Shot count, pacing, section structure. The skeleton of the edit.",
    locked: true,
    cost: 39,
    time: 60,
    detail: "24 shots · 5 sections",
  },
  {
    id: "transitions",
    name: "Transitions",
    short: "REF/TRN",
    desc: "Whip pans, cross-zooms, glitches, ramps, freezes — placed where the reference places them.",
    cost: 6,
    time: 22,
    detail: "6 styles · 24 placements",
  },
  {
    id: "grade",
    name: "Color grade",
    short: "REF/LUT",
    desc: "A 33³ LUT fit to the reference's frames, applied at 30–70% opacity.",
    cost: 5,
    time: 18,
    detail: "33³ LUT · matched",
  },
  {
    id: "text",
    name: "Text overlays",
    short: "REF/TXT",
    desc: "Kinetic captions, title cards. Same font weight, color, and animation as the reference. Copy is editable.",
    cost: 7,
    time: 14,
    detail: "12 overlays · editable",
  },
  {
    id: "motion",
    name: "Camera motion",
    short: "REF/MOT",
    desc: "Push, pan, tilt, whip, shake, ramps, freezes — applied to your clips to match each ref shot.",
    cost: 14,
    time: 40,
    detail: "8 motion classes",
  },
  {
    id: "beat",
    name: "Beat sync",
    short: "REF/BPM",
    desc: "Snap every cut and effect to your song's beat grid. Downbeats get the loudest cuts.",
    cost: 4,
    time: 8,
    detail: "124 BPM · 4/4 grid",
  },
];

export interface UseCase {
  tag: string;
  sub: string;
  note: string;
  thumb: string;
}

// Use cases — short chips. `thumb` is a filename resolved via asset().
export const USE_CASES: UseCase[] = [
  { tag: "REELS", sub: "9:16 · 15–60s", note: "Instagram, TikTok", thumb: "usecase-tiktok.jpg" },
  { tag: "VLOGS", sub: "16:9 · ≤5min", note: "YouTube", thumb: "usecase-travel.jpg" },
  { tag: "FASHION", sub: "9:16 / 1:1", note: "lookbooks, drops", thumb: "usecase-fashion.jpg" },
  { tag: "MUSIC", sub: "16:9 / 9:16", note: "festival recaps", thumb: "demo-after.jpg" },
  { tag: "FITNESS", sub: "9:16 · 15–60s", note: "training, coaches", thumb: "usecase-fitness.jpg" },
  { tag: "SPORTS", sub: "9:16 · 15–45s", note: "highlights, plays", thumb: "usecase-sports.jpg" },
  { tag: "GAMING", sub: "16:9 · ≤2min", note: "clips, edits", thumb: "usecase-gaming.jpg" },
  { tag: "WEDDINGS", sub: "16:9 · ≤3min", note: "recap films", thumb: "usecase-wedding.jpg" },
  { tag: "REAL ESTATE", sub: "16:9 · 30–90s", note: "listings", thumb: "usecase-realestate.jpg" },
];
