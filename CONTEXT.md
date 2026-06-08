# CONTEXT.md — Domain Glossary

## Core terms

**Cut list** — JSONB structure stored on `projects.cut_list`. Contains:
- `globals`: total duration, tempo, time signature, energy curve, section markers, aspect ratio, preview effects
- `slots`: ordered array of rendered segments
- `overlays`: text/shape/effect overlays
- `subtitles`: optional subtitle segments
- `audioTracks`: optional multi-song audio tracks (v2)

**Slot** — One rendered segment of the output. Key fields:
- `startS`, `duration_s`, `selectedClipId`, `transitionIn`, `transitionOut`, `effects[]`

**Asset** — Uploaded media. Types: `reference_video`, `song`, `clip`, `render`, `preview`, `subtitle`, `lut`, `sfx`.

**Style Tier** — 5-tier ladder: `cuts_only` → `color_grade` → `with_text` → `with_effects` → `full_remix`. Gates which Temporal pipeline stages run.

**Reference** — Project-level inspiration video (1 per project).

**Sample** — One-shot reference attached to a single prompt edit (via paperclip). Stored as `prompt_sample` asset, deleted after edit applies.

**Edit Mode** — `auto` (one-shot render) vs `assisted` (waits for cut-list approval signal).

## Naming rules

- Use camelCase in TypeScript / Python models that touch the cut list.
- Use snake_case only in Drizzle column names and raw SQL.
- Use `S` suffix for seconds (`startS`, `durationS`, `totalDurationS`).
