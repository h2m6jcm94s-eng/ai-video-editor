#!/usr/bin/env node
// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Download fixtures from manifest, verify magic bytes, skip if cached.

import { readFileSync, existsSync, writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

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
  const outPath = join(FIXTURES_DIR, fixture.filename);

  if (existsSync(outPath)) {
    const headRes = await fetch(fixture.url, { method: "HEAD" });
    const remoteSize = parseInt(headRes.headers.get("content-length") || "0", 10);
    const localSize = (await import("fs")).statSync(outPath).size;
    if (localSize === remoteSize && remoteSize > 0) {
      console.log(`  ✓ ${fixture.filename} already cached (${localSize} bytes)`);
      return outPath;
    }
  }

  console.log(`  ↓ ${fixture.filename} ...`);
  const res = await fetch(fixture.url);
  if (!res.ok) throw new Error(`Download failed: ${res.status} ${fixture.url}`);

  const buf = Buffer.from(await res.arrayBuffer());
  if (!checkMagic(buf, fixture.filename)) {
    throw new Error(`Magic-byte mismatch for ${fixture.filename}`);
  }

  writeFileSync(outPath, buf);
  console.log(`  ✓ ${fixture.filename} (${buf.length} bytes)`);
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
