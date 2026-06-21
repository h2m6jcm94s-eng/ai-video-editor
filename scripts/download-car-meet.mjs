#!/usr/bin/env node
// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Download car-meet demo assets from manifest, verify magic bytes, skip if cached.

import { readFileSync, existsSync, writeFileSync, mkdirSync, renameSync, statSync } from "fs";
import { join, dirname, basename, resolve } from "path";
import { fileURLToPath } from "url";

const ALLOWED_HOSTS = new Set([
  "videos.pexels.com",
  "video-previews.pexels.com",
  "cdn.pixabay.com",
  "freesound.org",
  "cdn.freesound.org",
]);

function assertSafeUrl(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`Invalid URL: ${url}`);
  }
  if (parsed.protocol !== "https:") throw new Error(`Refusing non-HTTPS URL: ${url}`);
  if (!ALLOWED_HOSTS.has(parsed.hostname)) throw new Error(`Host not in allowlist: ${parsed.hostname}`);
}

function assertSafeFilename(name) {
  if (!name || name !== basename(name) || name === "." || name === "..") throw new Error(`Invalid filename: ${name}`);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS_DIR = join(__dirname, "..", "docs", "assets", "car-meet");
const MANIFEST_PATH = join(ASSETS_DIR, "manifest.json");

const MAGIC = {
  mp4: [0x66, 0x74, 0x79, 0x70],
  mov: [0x66, 0x74, 0x79, 0x70],
  mp3_id3: [0x49, 0x44, 0x33],
  mp3_fffb: [0xff, 0xfb],
};

function checkMagic(bytes, filename) {
  const ext = filename.split(".").pop().toLowerCase();
  if (ext === "mp4" || ext === "mov") {
    const slice = bytes.slice(4, 8);
    return MAGIC.mp4.every((b, i) => slice[i] === b);
  }
  if (ext === "mp3") {
    const id3 = MAGIC.mp3_id3.every((b, i) => bytes[i] === b);
    const fffb = MAGIC.mp3_fffb.every((b, i) => bytes[i] === b);
    return id3 || fffb;
  }
  return true;
}

async function downloadFixture(fixture) {
  assertSafeUrl(fixture.url);
  assertSafeFilename(fixture.filename);
  const assetsAbs = resolve(ASSETS_DIR);
  const outPath = resolve(assetsAbs, fixture.filename);
  if (!outPath.startsWith(assetsAbs + (process.platform === "win32" ? "\\" : "/"))) {
    throw new Error(`Resolved path escapes assets dir: ${outPath}`);
  }

  if (existsSync(outPath)) {
    console.log(`  ✓ ${fixture.filename} (cached)`);
    return outPath;
  }

  console.log(`  ↓ ${fixture.filename} ...`);
  const res = await fetch(fixture.url);
  if (!res.ok) throw new Error(`Download failed: ${res.status} ${fixture.url}`);

  const buf = Buffer.from(await res.arrayBuffer());
  if (!checkMagic(buf, fixture.filename)) {
    throw new Error(`Magic-byte mismatch for ${fixture.filename}`);
  }

  const tmpPath = `${outPath}.part-${process.pid}-${Date.now()}`;
  writeFileSync(tmpPath, buf, { mode: 0o644 });
  renameSync(tmpPath, outPath);

  const wrote = statSync(outPath).size;
  console.log(`  ✓ ${fixture.filename} (${wrote} bytes)`);
  return outPath;
}

async function main() {
  if (!existsSync(MANIFEST_PATH)) {
    console.error(`Manifest not found: ${MANIFEST_PATH}\nRun: node scripts/select-car-meet-assets.mjs`);
    process.exit(1);
  }

  mkdirSync(ASSETS_DIR, { recursive: true });
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf-8"));

  console.log(`Downloading ${manifest.fixtures.length} car-meet assets...`);
  for (const fixture of manifest.fixtures) {
    await downloadFixture(fixture);
  }
  console.log("All car-meet assets ready.");
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
