module.exports = {
  "packages/shared-types/**/*.{ts,tsx}":
    "pnpm --filter @ai-video-editor/shared-types build",
  "*.{ts,tsx}": () => "pnpm typecheck",
};
