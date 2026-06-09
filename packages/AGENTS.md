# packages/ — AGENTS guide

## Shared-schema rules

1. **Every shared schema lives in `shared-types/src/schemas.ts`.** No route or component defines its own schema for a shape that crosses the API boundary.
2. **Schemas use `.strict()`** — unknown fields are rejected at runtime. Adding a field requires updating the schema AND migrating any stored JSONB.
3. **Types are derived from schemas via `z.infer`.** Never hand-write a type definition that duplicates a schema field.
4. **Field naming: camelCase always.** Snake_case is rejected by contract tests (`apps/api/src/test/contracts.test.ts`).
5. **New shared schema → add a contract test** in `apps/api/src/test/contracts.test.ts` or `apps/api/src/test/routes/*.contract.test.ts`.
6. **Python Pydantic models** that mirror the API contract inherit from `BaseModelCamel` (`services/shared-py/src/shared_py/models.py`) and must serialize with `.model_dump(by_alias=True)` when emitting JSON.

## Python ↔ TypeScript naming

| Concept | TypeScript (Zod) | Python (Pydantic) | JSON wire |
|---|---|---|---|
| Slot start time | `startS` | `start_s` | `startS` |
| Slot duration | `durationS` | `duration_s` | `durationS` |
| Global duration | `totalDurationS` | `total_duration_s` | `totalDurationS` |
| Tempo | `tempoBpm` | `tempo_bpm` | `tempoBpm` |
| Energy curve | `energyCurve` | `energy_curve` | `energyCurve` |
| Section markers | `sectionMarkers` | `section_markers` | `sectionMarkers` |
| Target shot | `targetShotType` | `target_shot_type` | `targetShotType` |
| Transition in | `transitionIn` | `transition_in` | `transitionIn` |
| Font size | `fontSizePx` | `font_size_px` | `fontSizePx` |

Python keeps idiomatic snake_case for attribute access; `alias_generator=to_camel` handles JSON serialization.
