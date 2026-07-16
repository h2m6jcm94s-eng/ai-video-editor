# G5 — Python Verb Registry + Generated TS Export

## Acceptance

```text
services\shared-py\tests\test_verb_registry.py .....
============================== 5 passed in 0.86s ==============================

pnpm --filter @ai-video-editor/api test -- src/test/commands.test.ts
1 passed (5 tests)

pnpm typecheck
4 successful

Full Python suite: 899 passed, 31 skipped
```

## What was built

- `services/shared-py/src/shared_py/verb_registry.py`
  - `VerbDefinition` dataclass: id, category, params_schema, prerequisites, ledger_ref, implemented, description.
  - `VerbRegistry` with register/get/list/to_json/to_markdown.
  - `make_default_registry()` seeds every implemented command verb, effect verb, and ledger operation.
- `scripts/generate_verb_registry.py`
  - Regenerates `packages/shared-types/src/verbs.generated.json`, `packages/shared-types/src/verbs.generated.ts`, and `VERBS.md`.
- `packages/shared-types/src/verbs.generated.ts`
  - Exports `EDIT_VERB` const consumed by the TypeScript parser.
- `packages/shared-types/src/commandVerbs.ts`
  - Imports `EDIT_VERB` from generated source; no local hardcoded list.
- `VERBS.md`
  - Human-readable canonical verb table at repo root.
- Tests
  - `services/shared-py/tests/test_verb_registry.py`: registry coverage, JSON export, markdown output.
  - `apps/api/src/test/commands.test.ts`: deterministic parser still passes against generated verb list.

## Notes

- The TypeScript parser (`commandParser.ts`) continues to define matcher logic; the canonical verb enum is now generated from Python.
- Two pre-existing API test failures in `ai.test.ts` (CUTLIST_SCHEMA_DRIFT) are unrelated to this change.
