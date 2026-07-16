# TICKET 3 — Reference intent extraction (PySceneDetect + Gemma)

## Verification

### PySceneDetect shot boundary extraction (batch2 reference)
```
shots: 129
first 5: [(0.0, 3.003), (3.003, 5.046708), (5.046708, 6.047708), (6.047708, 7.25725), (7.25725, 9.551208)]
last 5: [(227.143583, 230.188292), (230.188292, 230.939042), (230.939042, 242.7425), (242.7425, 246.037458), (246.037458, 250.20829166666667)]
```

### End-to-end intent profile extraction (batch2 reference, max_shots=10, fake LLM)
```
shots: 10
avg dur: 1.56s
cut density: 38.5 cuts/min
```
This density is consistent with a fast-paced AMV reference.

### Integration
- `services/style-worker/src/style_worker/reference_intent.py` created.
- `services/shared-py/src/shared_py/llm_client.py`: added `LLMTask.REFERENCE_INTENT`.
- `services/style-worker/src/style_worker/reference_analysis.py`: `analyze_reference()` now calls
  `extract_reference_intent_profile()` and stores the result in `ReferenceAnalysis.intent_profile`.

### Tests
`services/style-worker/tests/test_reference_intent.py` added — 4 tests passing.

## Result
PASS — reference videos now produce an intent pattern profile that the downstream intent composer can use.
