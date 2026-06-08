# packages/AGENTS.md

## Contract package rules

1. `packages/shared-types` must have **zero runtime dependencies** except `zod`.
2. Every const enum array is `as const` with a derived union type.
3. Every Zod schema has a corresponding exported TypeScript type via `z.infer<typeof xxxSchema>`.
4. Error codes live in `src/errors.ts` as a single const array. Add new codes to the end.
5. Effect schemas live in `src/effects.ts`. Each effect must define `params` with sensible defaults.
