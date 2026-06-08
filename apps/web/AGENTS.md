# apps/web/AGENTS.md

## Editor conventions

1. `useEditor.ts` is the single state machine for the cut list. Add new actions there; don't create parallel state.
2. Every form must use `react-hook-form` + `zodResolver` + a shared schema from `packages/shared-types`.
3. Toasts go through `sonner`. Error messages come from `APIError.userMessage`.
4. Keyboard shortcuts are registered in `EditorLayout.tsx` `handleKeyDown`.
5. The Cmd+K command palette actions are defined in `EditorLayout.tsx` — register new features there.
6. Tailwind only. Dynamic state styles (overlay positions) use inline `style={{}}` with typed props.
