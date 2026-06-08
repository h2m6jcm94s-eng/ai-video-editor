# AI Video Editor — Desktop App

Tauri v2 desktop wrapper for the AI Video Editor web app.

## Prerequisites

- [Rust](https://rustup.rs/)
- [Tauri CLI](https://v2.tauri.app/reference/cli/): `cargo install tauri-cli`

## Development

```bash
# From the monorepo root
pnpm --filter @ai-video-editor/desktop tauri dev
```

## Build

```bash
pnpm --filter @ai-video-editor/desktop tauri build
```

Outputs:
- Windows: `src-tauri/target/release/bundle/msi/*.msi`
- macOS: `src-tauri/target/release/bundle/dmg/*.dmg`
- Linux: `src-tauri/target/release/bundle/appimage/*.AppImage`
