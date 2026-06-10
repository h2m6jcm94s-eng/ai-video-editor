module.exports = {
  "*.{ts,tsx,js,jsx,json,md}": ["biome check --write --no-errors-on-unmatched"],
  "*.{ts,tsx}": [() => "pnpm typecheck"],
};
