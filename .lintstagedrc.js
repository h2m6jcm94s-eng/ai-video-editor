module.exports = {
  "packages/shared-types/**/*.{ts,tsx}":
    "pnpm --filter @ai-video-editor/shared-types build",
  "apps/api/**/*.{ts,tsx}": ["eslint --fix", () => "pnpm typecheck"],
  "*.{ts,tsx}": () => "pnpm typecheck",
};
