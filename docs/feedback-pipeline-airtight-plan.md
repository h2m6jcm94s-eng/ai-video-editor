# Airtight feedback-pipeline plan

This document hardens the PR-1 → PR-8 line of work against logical loopholes that let expensive features run in the wrong context, let noisy feedback poison the model, or let the system pretend competence it does not have.

It does **not** replace the original PRs. It adds **10 hardening PRs (PR-A1 → PR-A10)** that should ship in parallel with, or immediately after, the feedback-pipeline PRs.

---

## 1. Loophole audit

### A. Embedding-gating loopholes (features running where they should not)

Expensive or stylistically specific features currently fire unconditionally once their feature flag is on. The iconic-quote detector was the worst offender (Claude Haiku on every transcript segment of every clip). The same logic applies elsewhere:

| Feature | Wrong context | Cost / artifact |
|---|---|---|
| Iconic quote detection | Podcasts, tutorials, talking-head explainers | Wasted LLM calls; meaningless scores |
| Audio ducking | Projects with no song / instrumental-only | Sidechains silence / produces artifacts |
| Identity matting | Multi-character ensemble, no clear protagonist | Wrong matte, visual glitches |
| Anticipation cuts | Static talking heads, no motion peaks | Cuts feel random / jarring |
| POV / persistence inserts | Calm content (weddings, interviews) | Flashing inserts feel wrong |
| Auto-LUT | Reference has no distinct color treatment | Wasted compute; may degrade image |
| Pegasus labels | 200+ shot projects | Unbounded label cost |
| Demucs stem separation | Instrumental songs | No vocals to separate; wasted compute |
| Heatmap aesthetic scoring | Screen recordings / slides | LAION model misgeneralizes |
| Z-index text compositing | Projects with no lyrics/expected text | Wasted matting compute |

**Fix pattern:** every expensive feature gets a `should_run_<feature>(signals)` gate based on cosine distance to a hand-anchored relevance centroid. Phase 1: hard-coded centroids. Phase 4: data-driven centroids learned from accepted projects in the corpus.

### B. Reference-quality loopholes

- A 360p, shaky, over-compressed reference is currently analyzed and imitated silently.
- A reference with multiple distinct styles (e.g., music video cut mixed with behind-the-scenes) produces a confused average.
- `StyleGenome`, `Auto-LUT`, and `styleAnalysis` may disagree because they are separate extractors.

**Fix:** single `ReferenceAnalysis` cache per reference asset, with a `quality_score`, `is_consistent_style`, and a list of warnings surfaced to the user before render. Low-quality references require explicit confirmation.

### C. Feedback-signal noise

- `exported` does not mean "good" (user may share with an editor).
- `regenerated` may be exploratory A/B testing, not rejection.
- `abandoned` is confounded by lunch, phone calls, browser crashes.
- `inferred_quality_score` is computed at render time, before the user has actually watched and decided.
- Concurrent edits in multiple browser tabs create conflicting `cutlist_edits` attribution.

**Fix:** outcomes are labeled as "early" for 7 days and only become "final" after that window. `abandoned` requires explicit user dismissal, not idle timeout. Edits use an optimistic-locking/conflict-log mechanism (last-write-wins is not enough).

### D. Corpus poisoning / adversarial vectors

- Bots can mass-export low-quality renders to bias the global model.
- A single heavy user can disproportionately shape the corpus.
- Weird references can be uploaded to nudge the model.
- Predictor-v1-era entries can poison predictor-v2 training.

**Fix:** per-user weekly corpus cap (10 entries/week). Anomaly detection: entries > 3σ from their cluster centroid are quarantined. Every corpus entry is tagged with `producing_predictor_version` so future predictors can downweight stale data.

### E. Cold-start / sparsity failure modes

- Niche content (ASMR cooking, drone montages) may have no near neighbors.
- A global "50 entries" threshold ignores per-cluster sparsity.
- A new user with an unusual first project gets a bad result and churns.

**Fix:** per-cluster confidence, not global coverage. The engine returns a `confidence` score based on neighbor distance and local density. If `confidence < 0.4`, the UI surfaces uncertainty explicitly and offers 2-3 candidate renders instead of one.

### F. Attribution ambiguity

- One slot shortened can mean "global cut_density is too low" or "that slot specifically was bad".
- A user’s vlog edits can pollute their podcast taste profile.
- Adding an effect can mean "always add effects" or "the system missed this one effect".

**Fix:** distinguish global vs. local edits. If 8+ slots move in the same direction, attribute globally. If 1-2 slots change, attribute locally. Maintain per-content-cluster taste profiles (`vlog`, `podcast`, `music_video`, etc.).

### G. Privacy, biometric, and cost

- Face embeddings are not currently stored, but any future face-feature work needs explicit consent.
- LLM calls are unbounded per user.
- There is no "experimental render" opt-out.

**Fix:** explicit opt-in for face recognition (separate from telemetry). Monthly LLM call cap per user with graceful degradation to heuristic scoring. Per-project `exclude_from_learning` toggle.

### H. Math / engineering

- KNN over 20+ raw signal dimensions is dominated by scale (e.g., `clip_count` 0-1000 vs `speech_ratio` 0-1).
- Beat-detection failure cascades with no fallback.
- Audio mix has no final limiter; many dialogue tracks can clip.

**Fix:** z-score normalize signals before distance computation; use weighted Euclidean / Mahalanobis distance. Beat detection fallback cascade: madmom → librosa → synthetic 120 BPM grid. Final audio master: multi-band compressor + brick-wall limiter at -1 dBTP.

### I. Additional gaps discovered during PR-1 → PR-8 implementation

- `song_has_vocals` is referenced in the MV centroid but is not yet emitted in `ContentSignals`. It must be added to the signal extraction path.
- `cutlist_edits.patch` currently stores full `before`/`after` cutlists. For long projects this is large JSONB and leaks irrelevant personal content. It should store a JSON Patch (RFC 6902) diff instead.
- `renders.user_id` migration backfills from `projects.user_id`, but orphaned render rows (if any) would fail. The migration should backfill or delete orphans explicitly.
- The current `BehaviorEngine` does not return confidence; downstream code cannot ask the user when it is uncertain.
- `render_outcomes.exported` is set by the render worker on completion. That conflates "render produced" with "user exported", which PR-A6 addresses.

---

## 2. Airtightening PRs

### PR-A1 — Universal embedding-gate helper

**Goal:** one shared utility that every expensive feature uses to decide whether to run and how much budget to allocate.

**New file:** `services/shared-py/src/shared_py/feature_gating.py`

```python
FEATURE_RELEVANCE_CENTROIDS = {
    "iconic_quotes": {"speech_ratio": 0.05, "motion_density": 0.7,
                      "song_present": 1.0, "song_has_vocals": 1.0},
    "audio_ducking": {"song_present": 1.0, "speech_ratio": 0.3},
    "identity_matting": {"face_screentime_ratio": 0.6, "multi_face_ratio": 0.3},
    "anticipation_cuts": {"motion_density": 0.5},
    "pov_inserts": {"motion_density": 0.6, "song_energy_mean": 0.6},
    "auto_lut": {"reference_present": 1.0, "reference_color_variance": 0.3},
    "pegasus_labels": {"reference_present": 1.0},
    "demucs_stems": {"song_present": 1.0, "song_has_vocals": 1.0},
    "aesthetic_scoring": {"screen_capture": 0.0},
    "zindex_text": {"song_present": 1.0, "song_has_vocals": 1.0},
}

def should_run_feature(name: str, signals: dict, threshold: float = 0.3) -> tuple[bool, float]:
    centroid = FEATURE_RELEVANCE_CENTROIDS[name]
    relevance = cosine_similarity(signals, centroid)
    return relevance > threshold, relevance

def gated_budget(relevance: float, min_budget: int, max_budget: int) -> int:
    return int(min_budget + (max_budget - min_budget) * clip((relevance - 0.3) / 0.7, 0, 1))
```

**Work:**
- Move `_cosine_similarity` from `iconic_quotes.py` into `feature_gating.py` and re-export.
- Replace the iconic-quote gate with the shared helper.
- Wire gates into `audio_mix.py` (ducking, iconic quotes), `identity_matte.py` (matting), `anticipation_seek.py` (anticipation), `audio_mix.py` / POV inserts, `style_worker` (auto-LUT), `shot_detect.py` / Pegasus path, `demucs` stem path, `aesthetic_scoring.py`, and `text_overlay.py` / z-index text.
- Each feature keeps its own flag, but the gate runs even when the flag is on.

**Tests:** `services/shared-py/tests/test_feature_gating.py` with table-driven cases for each centroid.

---

### PR-A2 — Reference quality + shared analysis cache

**Goal:** one source of truth for reference analysis, with user-visible quality warnings.

**New file:** `services/style-worker/src/style_worker/reference_analysis.py`

```python
@dataclass
class ReferenceAnalysis:
    asset_id: str
    quality_score: float
    is_consistent_style: bool
    style_genome: StyleGenome
    lut_path: Optional[Path]
    color_variance_across_shots: float
    technical_quality: dict
    warnings: list[str]
```

**Work:**
- Compute `quality_score` from resolution, bitrate, aesthetic score, and frame-rate stability.
- Detect style consistency by comparing per-shot color histograms / genome families.
- Cache result per `(asset_id, extractor_version)` in asset metadata or a new `reference_analyses` table.
- Update `projects.generate` and `renders.start` flows to read this cache and surface warnings.
- Add `GET /api/projects/:id/reference-warnings` for the UI.

**Tests:** unit tests for quality/heuristic scoring; API test for warning endpoint.

---

### PR-A3 — Per-cluster confidence + uncertainty UX

**Goal:** the engine admits when it is guessing and offers alternatives.

**Change:** `BehaviorEngine.predict()` returns `(BehaviorVector, confidence: float)`.

```python
def knn_with_cluster_confidence(signals, neighbors):
    pairwise = [euclidean(a.signals, b.signals) for a, b in combinations(neighbors, 2)]
    cluster_density = 1 / (np.mean(pairwise) + 1e-9)
    query_distance = neighbors[0][1]
    confidence = sigmoid(cluster_density - query_distance)
    return behavior, confidence
```

**Work:**
- Update `BehaviorEngine` and `predict_behavior_activity` to return confidence.
- Update reason-worker workflow: if `confidence < 0.4`, generate 2-3 candidate cutlists (e.g., low/medium/high cut density) and pass them to the UI.
- New UI endpoint `POST /api/renders/:id/candidate-cutlists` or use existing cutlist with metadata.
- When user picks a candidate, write a strong outcome signal.

**Tests:** `test_behavior_engine.py` confidence cases; API test for candidate endpoint.

---

### PR-A4 — Spam detection + per-user contribution cap

**Goal:** prevent corpus poisoning.

**Work:**
- Add `behavior_corpus_entries.status` enum: `active`, `quarantined`, `rejected`.
- In `POST /api/internal/behavior-corpus`, compute z-score distance from the nearest cluster centroid using corpus stats; if `|z| > 3`, set status to `quarantined` and do not expose in KNN.
- Add weekly cap: count entries per user in the last 7 days; reject if >= 10.
- Add `producing_predictor_version` to corpus entries (from `render_behavior.predictor_version`).
- Add background review query `GET /api/admin/corpus-quarantine`.

**Tests:** quarantine logic; cap logic; KNN excludes quarantined entries.

---

### PR-A5 — Multi-cluster taste profile

**Goal:** a user’s vlog edits do not pollute their podcast taste.

**Change:** `user_taste_profiles.personal_bias_vector` → `cluster_bias_vectors: jsonb`.

```python
cluster_bias_vectors = {
    "music_video": {"cut_density_per_sec": 0.1, ...},
    "podcast": {...},
    "vlog": {...},
}
```

**Work:**
- Migration to rename/expand column.
- Classify a project’s content cluster from its signals (reuse `feature_gating` centroids).
- In `BehaviorEngine`, fetch the bias vector for the project’s cluster only.
- Update internal bias-merge endpoint and UI taste-profile endpoint.

**Tests:** migration; bias application per cluster; fallback to empty bias for unknown clusters.

---

### PR-A6 — 7-day outcome labeling window

**Goal:** do not treat early events as final learning signals.

**Work:**
- Add `render_outcomes.finalized_at` and `is_finalized` columns.
- Render worker should record `exported` as an early event only; do not set final score.
- Daily background job ( Temporal cron or simple scheduled function) finalizes outcomes older than 7 days:
  - compute `inferred_quality_score` from final state (exported + rating + thumbs + regenerated + abandoned).
  - only finalized outcomes feed corpus ingestion.
- Update corpus ingestion to skip non-finalized outcomes.

**Tests:** job unit test with mocked dates; API test that early outcomes are not final.

---

### PR-A7 — Per-project "ignore for learning" toggle

**Goal:** users can experiment without polluting the model.

**Work:**
- Migration: `projects.exclude_from_learning boolean default false`.
- UI: checkbox in project settings.
- API: respect `exclude_from_learning` in `POST /api/internal/renders/:id/ingest-to-corpus`.
- If `exclude_from_learning = true`, still write signals/behavior/outcomes for telemetry, but do not create corpus entries.

**Tests:** project patch test; corpus ingestion test with flag true/false.

---

### PR-A8 — Signal normalization + weighted distance

**Goal:** fix the math in KNN.

**Work:**
- Compute and cache `CORPUS_SIGNAL_MEAN` and `CORPUS_SIGNAL_STD` from active corpus entries.
- `normalize_signals(signals)` z-scores each dimension.
- Add `SIGNAL_DISTANCE_WEIGHTS` (e.g., `speech_ratio: 2.0`, `clip_count: 0.3`).
- `BehaviorEngine` uses weighted Euclidean: `sqrt(sum(weights * (a - b)^2))`.
- Recompute weights monthly from corpus (Phase 2 calibration).

**Tests:** normalized distance cases; weight dominance cases.

---

### PR-A9 — Audio master pass

**Goal:** prevent clipping and distortion in the final mix.

**Work:**
- In `render_worker/compiler.py`, append to the audio filter chain:
  - multi-band compressor (`acompressor` bands=4)
  - brick-wall limiter at -1 dBTP (`alimiter=limit=-1dB`)
- Make it unconditional (no flag needed; this is a correctness fix).

**Tests:** render output peak level <= -1 dBTP on test mix.

---

### PR-A10 — Beat detection fallback cascade

**Goal:** never fail silently when beat detection fails.

**Work:**
- In `ingest_worker/beat_detect.py`:
  - try `madmom`
  - on failure, try `librosa`
  - on failure, fall back to synthetic 120 BPM 4/4 grid for the song duration
- Log warnings at each fallback.
- Return a confidence score alongside the beat grid.
- Reason worker uses confidence to decide whether to trust beat-synced cuts or fall back to time-based cuts.

**Tests:** each fallback path; confidence output.

---

## 3. Execution order

```
PR-1 (slot density)              ── FIRST ── fixes visible repeat bug
PR-A1 (embedding gating)         ── SECOND ── required by PR-2/PR-3
PR-2 (audio policy) + PR-3 (iconic quotes)   ── gated by PR-A1
PR-4 (feedback schema) → PR-5 (persist signals/behavior) → PR-6 (outcomes) → PR-7 (attribution) → PR-8 (corpus/KNN)
PR-A2, PR-A3, PR-A8              ── parallel with PR-6/7/8, strengthen KNN
PR-A4, PR-A5, PR-A6, PR-A7       ── after PR-8, harden corpus/taste/outcomes
PR-A9, PR-A10                    ── independent correctness fixes, can ship anytime
```

**Critical path:** PR-1 → PR-A1 → PR-2/3 → PR-4..8 → PR-A4..A7.

---

## 4. Definition of done for the whole line of work

- Every expensive feature is gated by embedding relevance.
- Every render/outcome path has explicit handling for low-confidence / low-quality / ambiguous cases.
- Corpus writes are capped, quarantined, and version-tagged.
- User taste is separated by content cluster.
- Audio does not clip; beats always exist.
- All new code has unit tests; all integration paths have API tests.
- Full test suite: `vitest run` passes; `pytest --ignore=.../test_workflow.py` passes.

---

## 5. After this work is done — runbook and Phase 4

### Week 1-2: observe
- Dashboard metrics:
  - `feature_gate_skip_rate` per feature
  - `llm_calls_per_render` (target: podcast ≈ 0, MV ≈ 5-30)
  - `corpus_entries_quarantined_rate`
  - `outcome_finalization_7d_rate`
  - `render_confidence_distribution` (histogram of KNN confidence)
- Alert if any feature is skipped > 80% of the time (centroid may be mis-calibrated).
- Alert if LLM cost per user exceeds the monthly cap.

### Week 3-4: calibrate
- Recompute `SIGNAL_DISTANCE_WEIGHTS` from the first month of corpus data.
- Review quarantined corpus entries; label false positives/negatives and update anomaly threshold if needed.
- Adjust `MV_CLUSTER_CENTROID` and other centroids based on accepted-project embeddings.

### Month 2: Phase 4 — data-driven centroids
- Replace hand-anchored centroids with k-means/medoid centroids learned from accepted projects.
- Add automatic cluster naming from top signals.
- A/B test data-driven vs hand-anchored gates on a holdout set.

### Month 3: personalization at scale
- Use finalized outcomes + candidate selections to train a small MLP predictor.
- Run MLP alongside KNN; serve blend weighted by per-cluster confidence.
- Expand multi-cluster taste profiles to per-genre (e.g., electronic MV vs acoustic MV).

### Ongoing hygiene
- Re-run reference-quality analysis whenever a reference asset is re-uploaded.
- Recompute corpus signal mean/std weekly.
- Review per-user contribution caps monthly.
- Keep `producing_predictor_version` up to date on every corpus entry.

---

## 6. Quick reference: signals that must exist

For the gates to work, `ContentSignals` (and `render_signals`) must emit at least:

- `speech_ratio`
- `avg_speech_segment_duration_s`
- `multi_speaker_ratio`
- `song_present`
- **`song_has_vocals`** ← missing; add in PR-A1
- `song_energy_mean`
- `song_tempo_bpm`
- `song_section_count`
- `clip_count`
- `clip_avg_duration_s`
- `motion_density`
- `motion_variance`
- `aesthetic_score_mean`
- `face_screentime_ratio`
- `multi_face_ratio`
- `shot_diversity`
- `reference_present`
- `reference_color_variance` ← add in PR-A2
- `screen_capture` ← add in PR-A1

---

*Last updated: 2026-06-29. This plan should be treated as a living document; adjust thresholds and centroids as real data arrives.*
