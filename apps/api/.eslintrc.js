module.exports = {
  root: true,
  extends: ["@ai-video-editor/eslint-config"],
  parserOptions: { project: "./tsconfig.json" },
  ignorePatterns: ["dist/", "coverage/", "node_modules/", "src/test/"],
};
