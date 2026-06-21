# AI Video Editor — Feature Roadmap

Companion to the demo sprint plan at `C:\Users\devay\.claude\plans\deep-dive-into-the-hashed-music.md`.

This file is the **post-demo roadmap**: every feature we could build, classified by effort and strategic value. The demo sprint (Days 1-14, ending 2026-07-04) is Layer 1. Everything below is what comes after.

**Legend**
- 🟢 days · 🟡 weeks · 🟠 months · 🔴 needs ML specialist · ⚫ blocked by SOTA

---

## TIER A — Easy wins (1-3 weeks each, post-demo)

Massive "feels professional" gains relative to effort. Almost all are FFmpeg, MediaPipe, or single API calls.

| Feature | How | Effort | Wow |
|---|---|---|---|
| J-cuts and L-cuts | Audio offset relative to video on slot boundaries. Timeline math. | 🟢 3 days | ★★★ Biggest single "amateur → pro" jump |
| Stabilization | FFmpeg vidstab two-pass | 🟢 2 days | ★★★ Shaky phone footage → smooth |
| Optical-flow slow motion | FFmpeg `minterpolate=mi_mode=mci:mc_mode=aobmc` or RIFE local | 🟢 3 days | ★★ Smooth slo-mo on action shots |
| Auto-reframe vertical/square | MediaPipe subject tracking → crop window follows | 🟡 1 week | ★★★ One edit → 9:16 + 16:9 + 1:1 |
| Multi-cam audio sync | Cross-correlation on waveforms (librosa) | 🟡 4 days | ★★ Wedding/concert use case |
| Voice isolation | Demucs (Meta) or MDX-Net — separates vocals from music | 🟢 2 days | ★★ Noisy phone recording → clean vocal |
| AI voice-over generation | Text → ElevenLabs voice → drop in audio track | 🟢 2 days | ★★★ "AI narrator" for any video |
| Voice cloning | ElevenLabs custom voice (60s sample) | 🟢 2 days | ★★★ User's own voice reading any text |
| AI b-roll search | Twelve Labs index user library → text search | 🟢 3 days | ★★★ Cursor-like search across footage |
| AI music selection | Tag song moods, match to prompt + reference | 🟡 1 week | ★★ "Pick a song that fits this" |
| Text-based editing | Whisper transcript → editing transcript = editing timeline | 🟡 1.5 weeks | ★★★ THE Descript killer |
| AI thumbnails | First/middle/last frame + SD + brand colors | 🟢 3 days | ★★ One-click YouTube thumbnail |
| Auto-translation + dubbing | Whisper → DeepL → ElevenLabs → align | 🟡 1 week | ★★★ India market: Hindi/Tamil/Telugu reels |
| Lip-sync to dubbed audio | Wav2Lip or HeyGen API on translated voice | 🟡 1 week | ★★★ Makes dubbing convincing |
| Loudness normalization | FFmpeg `loudnorm=I=-14:LRA=11:TP=-1.5` | 🟢 1 day | ★ "Sounds right" on every platform |
| Auto-color from clip | FFmpeg color match via color-matcher | 🟢 2 days | ★★ Consistency across user clips |
| AI script-to-shot-list | LLM converts script → shot descriptions → searches user library | 🟡 1 week | ★★ "Here's my script, find shots" |

**Subtotal: ~10 weeks of work, ~17 features. Makes us competitive with CapCut + adds Descript-killer features.**

---

## TIER B — Multi-week builds (competitive → category-leading)

| Feature | How | Effort |
|---|---|---|
| AI inpainting (remove person/object) | Runway Erase API or self-host ProPainter | 🟡 2 weeks |
| AI outpainting (extend frame) | Runway / Adobe Firefly API | 🟡 1 week |
| AI rotobrush + subject tracking | SAM 2 (Meta, 2024, free) + tracking | 🟡 3 weeks |
| Green-screen / chroma key | FFmpeg chromakey + spill suppression | 🟡 1 week |
| Color grading UI | Lift/gamma/gain + curves + HSL qualifiers | 🟡 3 weeks |
| Conversational color grading | LLM "make it more cinematic" → grading params | 🟡 1 week |
| AI camera move generation | Runway camera control API on any clip | 🟡 1 week |
| Match frames | Embedding search over frames → find similar shot | 🟡 1 week |
| AI auto-cut (5min raw → 30s highlights) | Twelve Labs Pegasus 1.5 + LLM ranks moments | 🟡 2 weeks |
| AI auto b-roll insertion | LLM reads transcript → flags "show this" → fetches stock | 🟡 2 weeks |
| Real-time collaboration | Yjs CRDT + WebSocket; Figma for video | 🟠 6 weeks |
| Frame.io-style review | Timestamped comments + approval workflow | 🟡 2 weeks |
| Multi-track timeline UI | The deferred multi-track editor | 🟠 6 weeks |
| Motion graphics editor | Keyframe-based position/scale/rotation, bezier | 🟠 6 weeks |
| Direct publish to YouTube / TikTok / Instagram | Their APIs + auth | 🟡 2 weeks |
| HDR export (HDR10) | FFmpeg HDR pipeline + tone mapping | 🟡 2 weeks |
| AI face replacement (controlled) | DeepFaceLab, opt-in only ❗ | 🟡 3 weeks |
| Adaptive output (multi-platform from one edit) | One cut list → 4 renders w/ auto-reframe + trim | 🟡 1 week |
| Brand-aware AI editor | Brand kit → AI respects colors/fonts/voice | 🟡 1 week |
| Persistent AI assistant chat | Sidebar sees timeline state, suggests next edit | 🟡 2 weeks |

**Subtotal: ~3-4 months of work, ~20 category-leading features.**

---

## TIER C — Hard but doable with focused engineering (3-6 months each)

| Feature | How | Effort | Note |
|---|---|---|---|
| Real-time generative b-roll | Veo 3.1 / Kling 3.0 / Runway Gen-4.5 APIs | 🟠 6 weeks | $1-3 per generation |
| Character consistency across generated shots | Runway Act-One API | 🟠 8 weeks | Needs orchestration |
| AI VFX assistant ("add explosion here") | Library of effect prompts → Runway VFX | 🟠 6 weeks | |
| Match cuts auto-detection | Motion vector matching between clip A end / B start | 🟠 8 weeks | |
| Morph cuts (face continuity across cut) | Face tracking + frame blending | 🟠 8 weeks | |
| AI emotion-aware editing | Whisper emotion → energy curve → cut on emotional beats | 🟠 6 weeks | Research-y but doable |
| Spectral audio editing | iZotope RX style — UI + DSP | 🟠 6 weeks | |
| AI script-to-storyboard | LLM → image gen → arrange | 🟠 6 weeks | |
| Smart search across user library | Twelve Labs index everything, semantic any query | 🟠 6 weeks | API cost scales linearly |
| Predictive timeline (AI fills next 30s) | Style transfer from first 30s | 🟠 8 weeks | |
| Live AI directing assistant | Watches cuts real-time, suggests next clip | 🟠 8 weeks | Big LLM + state mgmt |

---

## TIER D — Research-grade / capital-intensive (Saksham's "GOOD SHIT")

6-12 months each. Need GPU budget. Possibly need ML hire.

| Feature | Why it's hard |
|---|---|
| 3D Gaussian Splatting reconstruction 🔴 | Bleeding edge for video; needs GPU cluster |
| DROID-SLAM neural camera tracking 🔴 | Model exists but slow; needs optimization |
| SAM 2 + custom segmentation pipeline 🟠 | Open, but productionizing for live edit = latency work |
| Camera pose transfer (drone move → phone footage) 🔴 | Estimate pose from video A + reproject B; PhD-level CV |
| Real-time 4K/8K editing without proxies 🟠 | Neural codec (DCAE); engineering-heavy |
| Physics-aware continuity (track objects across cuts) 🔴 | Identity persistence across cuts; current SOTA limit |
| Custom video generation model ⚫ | $10M+ training; only OpenAI/Runway/ByteDance |
| Diegetic AI sound design 🔴 | Generate sounds matching what's on screen |
| True 3D scene understanding ⚫ | Beyond current SAM/CLIP |
| Brain-computer editing ⚫ | Not yet 😅 |

---

## TIER E — Won't build

| Feature | Why skip |
|---|---|
| AI face replacement (uncontrolled) | Deepfake liability, India ban risk |
| Full DaVinci Resolve clone | Wrong wedge — they have 15 years of feature work |
| Avid Media Composer clone | Pro broadcast market, not our buyer |
| DRM / watermarking pipeline | Distraction unless enterprise asks |
| Plugin marketplace | Needs ecosystem; premature optimization |

---

## Recommended sequencing

### Layer 1 — Demo (Days 1-14, ends 2026-07-04)
Already in `deep-dive-into-the-hashed-music.md`. Reference-driven AI editor with prompt loop, color grade, transitions, focus pulls, text overlays.

### Layer 2 — V1 (3 months post-funding) — the killer feature set
12 features from Tier A + 4 from Tier B:

**From Tier A:**
1. J-cuts and L-cuts
2. Stabilization
3. Auto-reframe (9:16 ↔ 16:9 ↔ 1:1)
4. AI voice-over generation
5. Text-based editing (transcript → timeline)
6. AI b-roll search across user library
7. Auto-translation + dubbing with lip-sync
8. Optical-flow slow motion
9. Voice isolation
10. AI thumbnails
11. Loudness normalization
12. Auto-color match

**From Tier B:**
13. AI rotobrush + subject tracking (SAM 2)
14. AI inpainting (object removal)
15. AI auto-cut (5min → 30s highlights)
16. Direct publish to YouTube/TikTok/Instagram

Total: ~14-16 weeks. Makes us the most-featured AI editor in India + competitive globally.

### Layer 3 — V2 (6-12 months) — moat building
3-4 from Tier C + start research on 1 from Tier D:
- Real-time generative b-roll (Veo/Kling/Runway API integration)
- AI VFX assistant
- Character consistency
- Real-time collaboration
- Begin SAM 2 productionization

### Layer 4 — V3 vision (12-24 months) — Saksham's roadmap
With funding, GPU budget, ML hire:
- 3D Gaussian Splatting reconstruction
- DROID-SLAM camera tracking
- Camera pose transfer
- Custom diegetic sound design model

---

## The strategic wedge

> "The AI editor that takes your reference + your footage and makes a state-of-art edit, with conversational refinement."

Defensible because:
- Runway/Kling/Pika **generate** — they don't edit your footage
- Descript edits **transcripts** — doesn't do visual reference
- CapCut has AI features but **no reference-driven editing**
- DaVinci/Premiere don't have native conversational AI

Stack a few Tier A features and we're already category-leading.
