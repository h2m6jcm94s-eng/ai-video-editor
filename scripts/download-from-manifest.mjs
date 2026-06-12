#!/usr/bin/env node
// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Download fixtures from manifest, verify magic bytes, skip if cached.

import { readFileSync, existsSync, writeFileSync, mkdirSync, renameSync, statSync } from "fs";
import { join, dirname, basename, resolve } from "path";
import { fileURLToPath } from "url";

// Strict allowlist of fixture-source hosts. Manifest URLs from outside this
// list are rejected — defangs the "outbound request from file data" risk.
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
  if (!ALLOWED_HOSTS.has(parsed.hostname))
    throw new Error(`Host not in allowlist: ${parsed.hostname}`);
}

function assertSafeFilename(name) {
  // Reject path separators, parent refs, absolute paths — filename must be a leaf.
  if (!name || name !== basename(name) || name === "." || name === "..")
    throw new Error(`Invalid filename: ${name}`);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = join(__dirname, "..", "e2e", "fixtures");
const MANIFEST_PATH = join(FIXTURES_DIR, "manifest.json");

function loadEnv(path) {
  try {
    const text = readFileSync(path, "utf-8");
    for (const line of text.split("\n")) {
      const m = line.match(/^([A-Za-z0-9_]+)=(.*)$/);
      if (m && !process.env[m[1]]) {
        process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
      }
    }
  } catch {}
}
loadEnv(join(__dirname, "..", ".env"));

const MAGIC = {
  mp4: [0x66, 0x74, 0x79, 0x70], // ftyp at offset 4
  mov: [0x6d, 0x6f, 0x6f, 0x76], // moov at offset 4 (loose)
  wav: [0x52, 0x49, 0x46, 0x46], // RIFF at offset 0
  mp3_id3: [0x49, 0x44, 0x33], // ID3 at offset 0
  mp3_fffb: [0xff, 0xfb], // MPEG frame at offset 0
};

function checkMagic(bytes, filename) {
  const ext = filename.split(".").pop().toLowerCase();
  if (ext === "mp4") {
    const slice = bytes.slice(4, 8);
    return MAGIC.mp4.every((b, i) => slice[i] === b);
  }
  if (ext === "mov") {
    // QuickTime files: first 4 bytes are size, next 4 are 'ftyp' or 'moov'
    const ftyp = bytes.slice(4, 8);
    return [0x66, 0x74, 0x79, 0x70].every((b, i) => ftyp[i] === b);
  }
  if (ext === "wav") {
    return MAGIC.wav.every((b, i) => bytes[i] === b);
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
  const fixturesAbs = resolve(FIXTURES_DIR);
  const outPath = resolve(fixturesAbs, fixture.filename);
  // Defence-in-depth: confirm resolved path stays inside FIXTURES_DIR.
  if (!outPath.startsWith(fixturesAbs + (process.platform === "win32" ? "\\" : "/"))) {
    throw new Error(`Resolved path escapes fixtures dir: ${outPath}`);
  }

  // Download → write to temp → atomic rename. No HEAD-then-GET race; if the
  // file exists we still re-download and replace in one syscall.
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
    console.error(`Manifest not found: ${MANIFEST_PATH}\nRun: pnpm select-fixtures`);
    process.exit(1);
  }

  mkdirSync(FIXTURES_DIR, { recursive: true });
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf-8"));

  console.log(`Downloading ${manifest.fixtures.length} fixtures...`);
  for (const fixture of manifest.fixtures) {
    await downloadFixture(fixture);
  }
  console.log("All fixtures ready.");
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
