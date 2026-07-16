# Mathematical Foundations of the AI Video Editor Pipeline

This document explains the math and algorithms that power the AI Video Editor monorepo.  It is organized to follow the data flow from raw media ingestion → analysis → ranking → rendering, with concrete code references (file paths, function names, and key variables).

---

## 1. Beat Detection

**Primary file:** `services/ingest-worker/src/ingest_worker/beat_detect.py`

The beat detector produces a `BeatGrid` (`shared_py.models.BeatGrid`) containing BPM, beat times, downbeats, beat positions, and song-section labels.  It tries `allin1` first; if that is unavailable or fails, it falls back to `librosa`.

### 1.1 Pre-processing

- `decode_to_wav(audio_path)` decodes any input audio to a 44.1 kHz stereo WAV (`pcm_s16le`) using FFmpeg.  This normalizes sample rate and channel layout before analysis.

### 1.2 Onset strength envelope and beat tracking (librosa fallback)

In `detect_beats_librosa`:

1. Load audio at `sr=44100` mono: `y, sr = librosa.load(audio_path, sr=44100, mono=True)`.
2. Compute tempo and beat frames: `tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)`.
3. Convert frames to seconds: `beat_times = librosa.frames_to_time(beat_frames, sr=sr)`.

If `librosa.beat.beat_track` returns zero or near-zero beats (common for ambient/synthetic audio), a reliable tempo is recovered from the onset envelope:

```text
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
onset_tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr)
```

The final BPM is sanitized to a positive finite value, defaulting to `120.0` if everything fails.

### 1.3 Beat-grid fallback

If fewer than two beats are detected, a synthetic regular grid is emitted:

```text
beat_period = 60.0 / estimated_bpm
beat_times  = arange(0.0, duration, beat_period)
```

This guarantees downstream components always have beat anchors.

### 1.4 Downbeat inference

- `allin1` returns model-predicted downbeats directly.
- In the librosa fallback, the first detected beat is assumed to be the downbeat and every fourth beat after it is marked a downbeat: `downbeats = beat_times[::4]`.
- Beat positions cycle through `[1, 2, 3, 4]`.

### 1.5 Song-structure segmentation

`_detect_structure_librosa` segments the track into intro/verse/chorus/drop/bridge/outro using chroma + energy clustering:

1. Resample to `sr=22050`, `hop_length=512`.
2. Compute:
   - `chroma = librosa.feature.chroma_cqt`
   - `mel = librosa.feature.melspectrogram`
   - `logmel = librosa.power_to_db(mel, ref=np.max)`
   - `rms = librosa.feature.rms`
3. Beat-synchronize features with `librosa.util.sync`.
4. Stack features, weighting RMS by `5×` so energy influences clustering while chroma preserves harmonic similarity.
5. Build an affinity recurrence matrix:
   ```text
   R = librosa.segment.recurrence_matrix(features, mode="affinity", width=3, sym=True)
   R = librosa.segment.path_enhance(R, 5)
   ```
6. Run agglomerative segmentation: `boundary_indices = librosa.segment.agglomerative(features, k)`.
7. Choose `k = max(3, min(6, duration // 20))`, clamped to at most half the number of beats.
8. `_label_structure_segments` assigns labels heuristically from segment energy: highest-energy segment is `drop`, second highest is `chorus`, first is `intro`, last is `outro`, and remaining segments are `verse` or `bridge` depending on position relative to the drop/chorus. When the song is detected as calm/acoustic (low energy, low dynamic range, warm spectrum, sustained tones), the highest-energy segment is labelled `chorus` instead of `drop` so piano-ballad sections are not falsely described as EDM drops.

### 1.6 Energy curve

`compute_energy_curve(audio_path, num_points=64)` returns a down-sampled, normalized loudness curve used by style analysis and UI visualizations:

1. Compute RMS at `hop_length=512`.
2. Smooth with `scipy.ndimage.gaussian_filter1d` (`sigma = sr/512 * 0.2`).
3. Sample `num_points` evenly and min-max normalize to `[0, 1]`.

---

## 2. Shot Detection

**Primary file:** `services/ingest-worker/src/ingest_worker/shot_detect.py`

Shot boundaries are returned as `ShotBoundary` objects with start/end frame, start/end time, gradual flag, and confidence.  Two backends are supported: PySceneDetect (fast, CPU) and TransNet V2 (higher quality, GPU optional).

### 2.1 PySceneDetect content detector

`detect_shot_boundaries_pyscenedetect(video_path, threshold=27.0)` uses `scenedetect.detect` with a `ContentDetector`:

- `threshold=27.0` is the default content-difference threshold (lower = more sensitive).
- The detector computes a content distance between consecutive frames and flags a cut when the distance exceeds the threshold.
- Each returned scene becomes a `ShotBoundary` with `confidence=0.8` and `is_gradual=False`.

### 2.2 TransNet V2 deep shot detector

`detect_shot_boundaries_transnet(video_path, device, fps)` runs the TransNet V2 CNN:

1. Decode frames with PyAV and resize each to TransNet’s native input size `(48, 27)` with `INTER_LINEAR`.
2. Stack frames, normalize to `[0, 1]`, and run inference:
   ```text
   single_frame_pred, all_frames_pred = model(frames_tensor)
   probs = sigmoid(single_frame_pred)
   ```
3. Find boundary peaks with `scipy.signal.find_peaks`:
   - `height=0.5`
   - `distance=8` frames (minimum separation)
4. Gradual transitions are detected from `all_frames_pred` when the sigmoid at a peak exceeds `0.3`.
5. Boundaries are converted from frame indices to seconds using the supplied `fps`.

### 2.3 Choosing a backend

`detect_shot_boundaries` defaults to PySceneDetect.  When `use_transnet=True` and TransNet is importable, it attempts TransNet first and falls back to PySceneDetect on failure.

---

## 3. Heatmap Scoring

**Primary file:** `services/ingest-worker/src/ingest_worker/heatmap.py`

A *heatmap* is a per-clip list of overlapping quality windows.  Each window receives a fused `0..1` score and a component breakdown.  The reason worker later uses these windows to pick the best source start for each slot.

### 3.1 Sampling

`_sample_frames(video_path, stride_s, target_height=240)`:

- Opens the clip with OpenCV.
- Steps through frames in increments of `stride_s * fps`.
- Skips dark/letterboxed frames (`mean_brightness` outside `[15, 240]`).
- Resizes frames to `target_height` (default 240 px) for flow, keeping the original frame for aesthetic/sharpness scoring.

### 3.2 Optical flow

Between consecutive samples, dense optical flow is computed with OpenCV Farneback:

```python
cv2.calcOpticalFlowFarneback(
    prev_gray, curr_gray, None,
    pyr_scale=0.5, levels=3, winsize=15,
    iterations=3, poly_n=5, poly_sigma=1.2, flags=0
)
```

These parameters are also reused by the momentum/anticipation modules (see §5).

### 3.3 Per-window components

For each sample timestamp `t`, a window `[t - window_s/2, t + window_s/2]` is scored on five axes (weights defined in `WEIGHTS`):

| Component | Weight | Computation |
|-----------|--------|-------------|
| `motion` | 0.30 | Mean magnitude of Farneback flow, clipped to `[0, 1]`: `mean(sqrt(dx²+dy²)) / 10` |
| `aesthetic` | 0.25 | `score_image(frame)` from `shared_py.aesthetic` |
| `sharpness` | 0.20 | `clip(Laplacian variance / 500, 0, 1)` |
| `audio` | 0.15 | Mean librosa onset strength in the window, normalized |
| `stability` | 0.10 | Fraction of low-frequency power in the flow-magnitude FFT (penalizes camera shake) |

The fused score is the weighted sum:

```text
score = Σ components[k] * WEIGHTS[k]
```

### 3.4 Dominant motion

`_dominant_motion` averages flow vectors across the window and classifies direction as `left`, `right`, `up`, `down`, or `still` based on the sign and magnitude of the mean `(dx, dy)`.

### 3.5 Window and stride sizes

`compute_clip_heatmap` defaults to:

- `window_s = 0.5` seconds
- `stride_s = 0.25` seconds

These defaults give two samples per second with half-second overlap, balancing temporal resolution and compute cost.

### 3.6 Caching and metadata export

- `_cache_key` builds a SHA-256 key from file path, mtime, size, and algorithm parameters.
- `compute_clip_heatmap_cached` reads/writes `*.heatmap.json` files.
- `heatmap_to_metadata` serializes windows as dictionaries with `start_s`, `end_s`, `score`, `components`, and `dominant_motion`, which are stored in clip metadata and consumed by the ranker.

---

## 4. Clip Ranking

**Primary files:**

- `services/reason-worker/src/reason_worker/clip_rank.py`
- `services/shared-py/src/shared_py/tuning.py` (`RankTuning`)

`rank_clips_for_slots` assigns the best user clip to each cut-list slot using a weighted multi-objective score, then applies momentum re-ranking and anticipation offsets.

### 4.1 Core scoring formula

`_score_clip` computes the per-slot/per-clip total:

```text
total = SEMANTIC_WEIGHT   * semantic
      + SHOT_TYPE_WEIGHT  * shot_type_score
      + AESTHETIC_WEIGHT  * aesthetic
      + MOTION_WEIGHT     * motion_score
      + DURATION_WEIGHT   * duration_score
      + WINDOW_WEIGHT     * window_score
      - DIVERSITY_WEIGHT  * diversity
      - repetition_penalty
      - exhaust_bonus
```

Default weights come from `RankTuning`:

```text
SEMANTIC_WEIGHT  = 0.30
SHOT_TYPE_WEIGHT = 0.15
AESTHETIC_WEIGHT = 0.10
MOTION_WEIGHT    = 0.10
DURATION_WEIGHT  = 0.05
WINDOW_WEIGHT    = 0.25
DIVERSITY_WEIGHT = 0.40
MOMENTUM_WEIGHT  = 0.30
```

### 4.2 Component definitions

- **Semantic score** (`_semantic_score`):
  - If Marengo embeddings exist for both slot text and clip, uses cosine similarity rescaled from `[-1, 1]` to `[0, 1]`:
    ```text
    semantic = 0.5 + 0.5 * cosine_similarity(slot_emb, clip_emb)
    ```
  - Otherwise falls back to `DEFAULT_SEMANTIC_SCORE = 0.7`.
- **Shot type score**:
  ```text
  1.0 if meta["shot_type"] == slot.target_shot_type else 0.3
  ```
- **Aesthetic score**: `meta["aesthetic_score"]` (default 0.5).
- **Motion score**:
  ```text
  1.0 - abs(meta["motion_energy"] - slot.energy_level)
  ```
- **Duration score**: Gaussian penalty around the slot duration:
  ```text
  duration_score = exp(-(abs(clip_dur - slot.duration_s) / max(slot.duration_s, 0.1))² / DURATION_SCORE_DIVISOR)
  ```
  with `DURATION_SCORE_DIVISOR = 0.5`.
- **Window score**: Highest-scoring heatmap window that still leaves room for the full slot duration within the clip.  Reusing the exact same window subtracts `WINDOW_REUSE_PENALTY = 0.5`.
- **Diversity penalty**: Max cosine similarity between the candidate clip embedding and all already-chosen clip embeddings.  This penalizes repeated visual content.
- **Repetition penalty**:
  ```text
  repetition_penalty = REPEAT_BASE_PENALTY * repeat_count
  if last_chosen_clip_id == clip_id:
      repetition_penalty += LAST_REPEAT_PENALTY
  if at_usage_cap:
      repetition_penalty += USAGE_CAP_PENALTY
  ```
  Defaults: `REPEAT_BASE_PENALTY = 0.25`, `LAST_REPEAT_PENALTY = 0.4`, `USAGE_CAP_PENALTY = 10.0`.

### 4.3 Usage caps and exhaust fairness

`rank_clips_for_slots` computes a per-clip usage cap based on the slot-to-clip ratio:

```text
if num_slots <= num_clips:
    usage_cap = 1
else:
    usage_cap = max(2, ceil((num_slots / num_clips) * USAGE_CAP_OVERFLOW_FACTOR))
```

with `USAGE_CAP_OVERFLOW_FACTOR = 1.2`.

When `force_exhaust=True`:

- Unused clips receive `EXHAUST_UNUSED_BONUS = -1.5` (subtracted, i.e. a strong positive boost).
- Clips used less than the fair share `num_slots / num_clips` receive `EXHAUST_FAIR_BONUS = -0.4`.
- If `num_slots > num_clips`, no clip may repeat until every clip has been chosen at least once.

This prevents a single high-scoring clip from dominating the edit and encourages balanced clip usage.

### 4.4 Momentum re-ranking

`rerank_with_momentum` (detailed in §5) adds a motion-continuity bonus after the initial sort.  The top candidate per slot becomes the chosen clip; its embedding is added to `chosen_embeddings` for diversity tracking in subsequent slots.

### 4.5 Confidence

`compute_confidence` derives a per-slot confidence from the score gap:

- If at least four candidates: `gap = score[0] - score[3]`, scaled by `CONFIDENCE_TOP4_MULTIPLIER = 1.5`.
- Otherwise: `gap = score[0] - score[-1]`, scaled by `CONFIDENCE_TAIL_MULTIPLIER = 2.0`.
- Clamped to `[0, 1]`.

---

## 5. Momentum & Anticipation

**Primary files:**

- `services/reason-worker/src/reason_worker/momentum.py`
- `services/reason-worker/src/reason_worker/anticipation.py`
- `services/shared-py/src/shared_py/tuning.py` (`FlowTuning`, `MomentumTuning`, `AnticipationTuning`)

### 5.1 Shared optical-flow parameters

`FlowTuning` centralizes Farneback settings used by heatmap, momentum, and anticipation:

```text
TARGET_SIZE = (256, 144)
N_FRAMES    = 8
PYR_SCALE   = 0.5
LEVELS      = 3
WINSIZE     = 15
ITERATIONS  = 3
POLY_N      = 5
POLY_SIGMA  = 1.2
FLAGS       = 0
```

Frames are downscaled to 256×144 before flow to keep compute cheap while preserving coarse motion direction.

### 5.2 Mean flow vector

`compute_mean_flow_vector(clip_path, start_s, n_frames=8)` in `momentum.py`:

1. Seek to `frame_idx = round(start_s * fps)`, clamped so `n_frames` frames remain.
2. Read `n_frames` consecutive downscaled frames.
3. Compute Farneback flow between each pair.
4. Accumulate and average the mean flow vector `(dx, dy)`.

### 5.3 Momentum coherence

`momentum_coherence(v_out, v_in)` returns a `0..1` score for how well the incoming clip continues the outgoing motion:

```text
if both vectors are zero:  return 0.5   # neutral
cos_sim = (ax*bx + ay*by) / (|a| * |b|)
cos_sim = clip(cos_sim, -1, 1)
coherence = 0.5 + 0.5 * cos_sim
```

Identical directions score 1.0, opposite directions score 0.0, and orthogonal or still motion is 0.5.

In `rerank_with_momentum`, the bonus is:

```text
bonus = MOMENTUM_WEIGHT * momentum_coherence(prev_end_motion, candidate_start_motion)
```

The bonus is forced to `0` when the candidate clip is the same as the previously chosen clip, preventing a “gravity well” that would keep the edit on one clip.

### 5.4 Anticipation offset

`anticipation.py` shifts a chosen clip’s source start so that the cut lands slightly *before* the dominant motion peak, making the edit feel punchy.

#### 5.4.1 Pre-computing the motion curve

`precompute_clip_motion_curve(clip_path, fps_sample=8.0)`:

1. Sample frames at 8 fps (`fps_sample` from `AnticipationTuning`).
2. Compute Farneback flow between consecutive samples.
3. Store the mean motion magnitude per sample as `clip_path.motion.npz`.

#### 5.4.2 Peak detection

`find_motion_peaks_in_window` min-max normalizes the curve and runs `scipy.signal.find_peaks` with `MIN_PROMINENCE = 0.3`, so peak detection is independent of absolute motion scale.

#### 5.4.3 Offset calculation

`compute_anticipation_offset`:

1. Maps the source window to frame indices in the motion curve.
2. Finds the dominant peak in that window.
3. Computes the desired start so the cut lands `TARGET_OFFSET_MS = 333 ms` before the peak:
   ```text
   desired_start_s = peak_time_s - 333/1000
   offset_s        = desired_start_s - source_window_start_s
   ```
4. Clamps the offset so the start does not move before `0` or past `duration - MAX_OFFSET_PAD_S` (`MAX_OFFSET_PAD_S = 0.05`).

The compiler later adds this offset to `slot.source_window_start_s`.

---

## 6. Audio Ducking / Sidechain Compression

**Primary files:**

- `services/render-worker/src/render_worker/compiler.py`
- `services/reason-worker/src/reason_worker/audio_mix.py`

The renderer builds a two-pass FFmpeg graph: video is assembled first, then audio is mixed separately so `sidechaincompress` can use filtered sidechain streams (an FFmpeg limitation when video filters are present).

### 6.1 dB-to-linear conversion

`_db_to_linear(gain_db)` in `compiler.py` converts decibel gains to amplitude ratios:

```text
linear = 10^(gain_db / 20)
```

This is used for:

- Per-track `volume=gain_dB` filters (FFmpeg accepts dB directly, but the music volume automation uses linear values via `asendcmd`).
- `_duck_ratio(duck_gain_db) = max(1.0, round(10^(abs(duck_gain_db)/20), 2))`, which converts a negative duck gain into a compressor ratio ≥ 1.

### 6.2 Music volume automation

`_build_music_volume_filter` in `compiler.py` writes an `asendcmd` file that changes the music bed gain per slot:

1. Collect `(start_s, end_s, song_level_db)` segments from `SlotAudioMix` decisions.
2. Merge adjacent segments with identical gain.
3. Fill pre/post gaps with `DEFAULT_MUSIC_GAIN_DB = -3.0`.
4. Convert each segment gain to linear with `_db_to_linear` and emit commands such as:
   ```text
   {start:.3f} volume volume {linear:.4f};
   ```
5. The filter chain `volume='{initial_linear}':eval=frame,asendcmd=f={cmd_file},aresample=48000` applies the automation.

### 6.3 Dialogue bus gate and compressor

`_build_dialogue_bus` in `compiler.py` pre-mixes all dialogue segments into a single gated/compressed bus:

1. Each dialogue segment is delayed to its timeline position (`adelay=delays={delay_ms}|{delay_ms}:all=1`).
2. Segments are mixed with `amix=inputs=N:duration=longest:normalize=0`.
3. A gate (`agate`) removes room tone and breath noise:
   - `threshold = DIALOGUE_BUS_GATE_THRESHOLD_DB = -50 dB`
   - `ratio = DIALOGUE_BUS_GATE_RATIO = 10`
   - `attack = 20 ms`, `release = 200 ms`
4. A compressor (`acompressor`) evens out dialogue levels:
   - `threshold = DIALOGUE_BUS_COMP_THRESHOLD_DB = -18 dB`
   - `ratio = DIALOGUE_BUS_COMP_RATIO = 3`
   - `attack = 5 ms`, `release = 100 ms`

### 6.4 Sidechain ducking

`_build_audio_filter_v2` implements the final mix:

1. Music volume curve → `[music]`.
2. Each dialogue track is faded, gated (`agate=threshold=-45dB:ratio=10:attack=10:release=100`), resampled, delayed, and `asplit` into two streams: one for the sidechain key bus and one for the final mix.
3. Dialogue sidechain streams are summed without normalization (`amix=inputs=N:normalize=0`) and padded to the total output duration (`apad=whole_len={total_samples}`) so the sidechain key does not truncate the music.
4. Music is ducked with:
   ```text
   [music][dlg_sc_padded]sidechaincompress=threshold=0.12:ratio=4:attack=150:release=350[music_ducked]
   ```
5. Final mix weights dialogue slightly above music (`weights='1.0 1.3'`) and a safety `alimiter` prevents clipping.

### 6.5 Section-aware mix policies

`audio_mix.py` defines `DEFAULT_POLICIES` per section label:

```text
intro:  music_gain_db=-4.0, duck_gain_db=-10.0, fade_in_s=1.0
verse:  music_gain_db=-2.0, duck_gain_db=-14.0
chorus: music_gain_db= 0.0, duck_gain_db=-10.0
drop:   music_gain_db= 0.0, duck_gain_db=-6.0, music_full=True
bridge: music_gain_db=-2.0, duck_gain_db=-12.0
outro:  music_gain_db=-4.0, duck_gain_db=-8.0, fade_out_s=2.0
```

`build_audio_tracks` splits the music bed into per-section `AudioTrack`s, disables ducking in drops (`music_full=True`), and keeps only the highest-scoring dialogue segment per slot to avoid flooding the mixer.

---

## 7. Face Detection & Identity Clustering

**Primary files:**

- `services/ingest-worker/src/ingest_worker/identity.py`
- `services/shared-py/src/shared_py/identity_cluster.py`
- `services/reason-worker/src/reason_worker/protagonist_pick.py`
- `services/shared-py/src/shared_py/tuning.py` (`IdentityTuning`)

### 7.1 Face detection and embedding extraction

`identity.py` uses InsightFace (`buffalo_l` model, det size 640×640) with CUDA fallback to CPU.

`extract_faces_from_clips`:

1. Samples each clip at `SAMPLE_FPS = 2.0` frames per second (from `IdentityTuning`).
2. Buffers sampled frames into chunks of `max_batch_frames=64`.
3. Runs `app.get(frame)` for each sampled frame.
4. For each face, stores:
   - `bbox` and `bbox_norm` (normalized to frame dimensions)
   - `embedding` (InsightFace 512-D vector)
   - `confidence` (detection score)
   - `face_area_ratio` (face area / frame area)
   - `t_s` (timestamp)

Results are cached as `{clip_path}.faces.json`.

### 7.2 Identity clustering

`cluster_project_identities` in `identity_cluster.py` clusters all face embeddings across clips:

```text
DBSCAN(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, metric="cosine")
```

Defaults from `IdentityTuning`:

- `DBSCAN_EPS = 0.4` (maximum cosine distance for a neighborhood)
- `DBSCAN_MIN_SAMPLES = 5`

DBSCAN noise points (`label == -1`) are discarded.  For each cluster, an `Identity` is created with:

- `centroid_embedding = mean(embeddings of cluster members, axis=0)`
- `avg_confidence = mean(confidence)`
- `avg_face_size = mean(face_area_ratio)`
- `screen_time_s = sum(clip durations for clips that contributed at least one face to the cluster)`

### 7.3 Protagonist selection

`pick_protagonists` ranks identities by:

```text
score = screen_time_s * avg_confidence * sqrt(avg_face_size)
```

The square root on face size keeps the score from being dominated by extreme close-ups while still rewarding visible subjects.  The top `TOP_N = 2` identities are returned as project protagonists.

`select_protagonists` in `protagonist_pick.py` loads cached `.faces.json` files, estimates clip durations from detection timestamps, calls `cluster_project_identities`, and returns the selected protagonist IDs.

---

## 8. Style Genome

**Primary files:**

- `services/style-worker/src/style_worker/genome/extract.py`
- `services/style-worker/src/style_worker/genome/families/audio_align.py`
- `services/style-worker/src/style_worker/genome/families/composition.py`
- `services/style-worker/src/style_worker/genome/families/cut_rhythm.py`
- `services/style-worker/src/style_worker/genome/families/dwell.py`
- `services/style-worker/src/style_worker/genome/families/motion.py`

The Style Genome is a 50-feature fingerprint (`feature_count=50` in `shared_py.models.StyleGenome`) describing the editing style of a reference video.  Features are grouped into five families:

| Family | Features | File |
|--------|----------|------|
| Cut rhythm | 15 | `families/cut_rhythm.py` |
| Motion | 12 | `families/motion.py` |
| Dwell | 8 | `families/dwell.py` |
| Audio alignment | 10 | `families/audio_align.py` |
| Composition | 5 | `families/composition.py` |

### 8.1 Entry point

`extract_genome(reference_video_path, beat_grid, shot_boundaries, style_analysis, project_clips)` in `extract.py`:

1. Reads video metadata (fps, frame count, duration, resolution) with OpenCV.
2. If no shot boundaries are supplied, falls back to `_detect_shot_boundaries`, which samples at 2 fps, computes inter-frame `absdiff`, and thresholds at `mean + 2*std`.
3. Normalizes `style_analysis` so every shot has a `camera_motion` and a `transition_in` label.
4. Calls each family extractor.

### 8.2 Cut rhythm family (`extract_cut_rhythm`)

Computes from `shot_boundaries` and `beat_grid`:

- Per-shot durations: `avg`, `std`, `min`, `max`.
- `cut_density_per_min = total_cuts / (duration_s / 60)`.
- Section-specific cut densities for verse, chorus, drop, intro, outro, build-up.
- `hard_cut_ratio` and `gradual_transition_ratio` from transition labels.
- `cuts_on_downbeat_ratio` by comparing cut times to `beat_grid.downbeats` within a tolerance of `beat_period / 4`.

### 8.3 Motion family (`extract_motion_genome`)

Uses `style_analysis.camera_motions` and per-shot inter-frame difference energy:

- `avg_motion_energy`, `max_motion_energy`, `motion_energy_std`.
- Percentages of shots labeled `static`, `pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `zoom_in`, `zoom_out`, `handheld`, `gimbal`.

Energy is computed by sampling each shot at 4 fps and averaging `cv2.absdiff(gray, prev_gray).mean() / 255.0`.

### 8.4 Dwell family (`extract_dwell_genome`)

Analyzes face presence using project-clip face metadata or a lightweight InsightFace sample of the reference video:

- `avg_face_size_ratio`, `max_face_size_ratio`, `face_size_variance`.
- `avg_subjects_per_shot` and `pct_shots_with_face` from per-shot max face counts.
- `avg_face_screen_time_s` and `protagonist_present_ratio` (placeholder zeros when identity tracking is unavailable).

### 8.5 Audio alignment family (`extract_audio_align_genome`)

Measures how editorial cuts relate to the beat grid:

- `cut_to_beat_alignment`: fraction of cuts within `beat_period/4` of any beat.
- `cut_to_downbeat_alignment`: fraction within tolerance of a downbeat.
- Section-beat ratios for verse, chorus, and drop.
- `avg_cut_to_nearest_beat_s`: mean distance from each cut to its nearest beat.
- From `audio_tracks`: `music_duck_frequency`, `dialogue_clip_ratio`, `avg_dialogue_duration_s`.

### 8.6 Composition family (`extract_composition_genome`)

For the middle frame of each shot:

1. Detects up to 100 good feature corners with `cv2.goodFeaturesToTrack`.
2. Classifies shot size from corner spread and centroid centrality:
   - `close_up` if centroid is near center and spread is tight.
   - `wide` if spread is large.
   - `medium` otherwise.
3. Computes `rule_of_thirds_ratio`: fraction of corners within a 10% margin of the rule-of-thirds lines.

Outputs: dominant shot size plus percentages of close-up, medium, and wide shots.

---

## 9. NVENC / FFmpeg Encoding

**Primary file:** `services/render-worker/src/render_worker/compiler.py`

`compile_timeline` renders the final video in two passes: segment extraction, then filter-complex concatenation with transitions.

### 9.1 CQ vs CRF

The encoder args are selected by `_video_encode_args(config)` and `_segment_video_args(config)`:

- **Software (libx264/libx265):** uses CRF (Constant Rate Factor):
  ```text
  -crf {video_crf}
  ```
  Lower CRF = higher quality.  Profiles are stored in `CompilerTuning.QUALITY_PROFILES` (preview=28, draft=23, demo=19, export=17, archive=15).

- **Hardware NVENC:** uses CQ (Constant Quality) with VBR rate control:
  ```text
  -c:v h264_nvenc -preset p5 -tune hq -rc vbr -cq {cq}
  ```
  Default CQ is 19; fallback `NVENC_DEFAULT_CQ = 20` is used when the config value is missing or invalid.

CRF is codec-agnostic and targets perceptual quality for software encoders; CQ is NVENC’s quality target and behaves similarly but is not numerically equivalent to x264 CRF.

### 9.2 Preset mapping

`CompilerTuning.QUALITY_PROFILES` maps quality names to libx264 presets:

```text
preview  -> ultrafast, crf 28
draft    -> veryfast, crf 23
demo     -> medium,   crf 19
export   -> slow,     crf 17
archive  -> veryslow, crf 15
```

For NVENC, presets are `p1` (fastest) through `p7` (slowest/best).  `_segment_video_args` validates the preset against `_NVENC_PRESETS`; otherwise it defaults to `p5`.

### 9.3 Segment extraction

Each slot is extracted in parallel via `_extract_segment` (using `ThreadPoolExecutor`, capped at 8 workers to avoid GPU oversubscription).  Segments are re-encoded with `_segment_video_args` and have audio stripped (`-an`) so the video pass is independent of the audio mix.

### 9.4 filter_complex concat and xfade

The final video graph is built in `compile_timeline` Stage 2:

1. Reset timestamps on each segment:
   ```text
   [i:v]setpts=PTS-STARTPTS[v{i}]
   ```
2. Chain adjacent segments with `xfade`:
   ```text
   [current][v{i+1}]xfade=transition={type}:duration={xfade_duration}:offset={offset}[vx{i}]
   ```
   - Transition names are mapped through `XFADE_MAP` (e.g. `dissolve` → `fade`, `whip` → `hlslice`).
   - `xfade_duration = min(0.3, slot_dur*0.5, next_dur*0.5)`.
   - `offset = max(0.0, current_duration - xfade_duration)`.
   - The running duration is updated as `current_duration += next_dur - xfade_duration`.
3. Optional LUT, text overlays, and subtitles are appended as additional filter stages.
4. Final output is formatted to `yuv420p` for compatibility.

Slot durations are scaled before extraction to compensate for xfade overlap:

```text
estimated_overlap = (num_slots - 1) * 0.3
desired_slot_sum    = target_duration + estimated_overlap
duration_scale      = desired_slot_sum / raw_slot_sum
```

This ensures the concatenated result, after transitions consume overlap, matches the cutlist’s declared `total_duration_s`.

### 9.5 Final mux

After the video-only intermediate is produced:

1. Audio inputs are assembled (video-only intermediate, music bed, optional pre-mixed dialogue bus).
2. `_build_audio_filter_v2` creates the ducking/mix graph.
3. Final FFmpeg command maps video from the first input (`0:v`) and audio from `[a_out]`, copies the already-encoded video, and encodes audio with the configured codec/bitrate.

---

## Summary

The pipeline combines classic signal-processing ideas (onset envelopes, histogram/content differences, optical flow, DBSCAN) with modern deep-learning components (TransNet V2, InsightFace, Marengo text-to-video embeddings) and FFmpeg-based rendering.  All numerical knobs are centralized in `services/shared-py/src/shared_py/tuning.py`, making the system easy to tune across ingest, reason, style, and render workers.
