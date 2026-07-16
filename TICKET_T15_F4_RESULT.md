# T.15 F4 — ViewerState + Operation Ledger

## Acceptance

```text
services\shared-py\tests\test_viewer_state.py ........
============================== 8 passed in 0.88s ===============================
```

## What was built

- `services/shared-py/src/shared_py/viewer_state.py`
  - `ViewerState` model (attention, arousal, valence, tension, load)
  - `OperationEffect` model (d_attention, d_arousal, d_valence, d_tension, d_load, novelty_family, duration_s)
  - `RegisteredOperation` model (id, category, params_schema, prerequisites, effect)
  - `OperationLedger` registry
  - `ViewerStateSimulator` with decay-scaled delta application and trajectory simulation
  - `make_default_ledger()` seeds existing verbs/effects/transitions/text/audio
- `services/shared-py/src/shared_py/__init__.py` exports the new types
- `services/shared-py/tests/test_viewer_state.py` unit tests

## Notes

- F4 is foundational for T16.3 state-tracking composer.
- All existing effect verbs are now registered with honest ViewerState deltas.
