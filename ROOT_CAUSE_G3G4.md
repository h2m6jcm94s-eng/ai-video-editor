# Root Cause — G3 + G4 Blocked

## What is blocked

- **G3** — Scene Model completion with SAM3 masklets + global camera-motion estimation + measured S2 capability envelope.
- **G4** — Real world text behind the subject via SAM3 masklet occlusion + camera-motion anchoring + spring entrance.

## Why it is blocked

Both G3 and G4 require per-frame **SAM3 subject segmentation** as a non-negotiable dependency. The repo's SAM3 integration is present in code (`services/segment-worker/src/segment_worker/client.py`) but the runtime is not provisioned in this environment:

1. **SAM3 Python package is not installed** in the active venv:
   ```text
   ModuleNotFoundError: No module named 'sam3'
   ```
2. **No SAM3 HTTP server is running** at the expected endpoint:
   ```text
   curl http://localhost:8189/health  ->  SAM3 not reachable
   ```
3. **No Hugging Face token is configured**, and SAM3 checkpoints are gated:
   ```text
   HF_TOKEN not set
   ```
4. **No local SAM3 checkpoint exists** in the HF cache or storage root:
   ```text
   ~/.cache/huggingface/hub has no sam3/sam3.1 checkpoints
   /e/ai-video-editor-storage has no SAM3 weights
   ```

`Sam3Segmenter.available()` correctly returns `False` under these conditions, so any attempt to run G3/G4 acceptance would silently skip or fail.

## What would unblock it

1. Install SAM3 from the local clone (`E:/work/sam3-main/sam3-main`) or pip, and
2. Provide a Hugging Face token with access to the gated SAM3/SAM3.1 checkpoints, or place a local checkpoint at `SAM3_CHECKPOINT_PATH`, and
3. Ensure the segment worker or SAM3 HTTP server is running for the code path being used.

## Honesty note

Per the project rule "any missing dependency must fail loud with ROOT_CAUSE.md, not silently degrade", I am stopping here rather than shipping placeholder masklets or synthetic envelopes that would pass tests but not satisfy the real spec.

## Completed so far

- G1: spring/overshoot easing + text layer default — committed and pushed.
- G2: blend modes + alpha mattes + 3-layer demo render — committed and pushed.
- G5: Python verb registry + generated TS export + VERBS.md — committed and pushed.
- Full Python suite after G1/G2/G5: **899 passed, 31 skipped**.
- TS typecheck and command parser tests pass.
