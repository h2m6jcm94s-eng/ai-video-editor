#!/usr/bin/env node
// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Select portrait videos from Pexels + CC0 audio from Freesound, write manifest.

import { writeFileSync, mkdirSync, readFileSync } from "fs";
import { dirname, join } from "path";
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

const PEXELS_API_KEY = process.env.PEXELS_API_KEY;
const FREESOUND_API_TOKEN = process.env.FREESOUND_API_TOKEN;

if (!PEXELS_API_KEY) {
  console.error("Missing PEXELS_API_KEY");
  process.exit(1);
}
if (!FREESOUND_API_TOKEN) {
  console.error("Missing FREESOUND_API_TOKEN");
  process.exit(1);
}

async function pexelsSearch() {
  const url = new URL("https://api.pexels.com/videos/search");
  url.searchParams.set("query", "portrait person");
  url.searchParams.set("orientation", "portrait");
  url.searchParams.set("size", "small");
  url.searchParams.set("per_page", "20");

  const res = await fetch(url, {
    headers: { Authorization: PEXELS_API_KEY },
  });
  if (!res.ok) throw new Error(`Pexels API ${res.status}: ${await res.text()}`);
  const data = await res.json();

  // Filter 6–18s portrait videos with MP4/MOV files
  const videos = (data.videos || [])
    .filter((v) => v.duration >= 6 && v.duration <= 18)
    .filter((v) => v.video_files?.some((f) => f.file_type === "video/mp4" || f.file_type === "video/quicktime"))
    .sort((a, b) => a.id - b.id) // deterministic
    .slice(0, 4)
    .map((v) => {
      const file = v.video_files.find((f) => f.file_type === "video/mp4" && f.width < f.height)
        || v.video_files.find((f) => f.file_type === "video/mp4")
        || v.video_files.find((f) => f.file_type === "video/quicktime")
        || v.video_files[0];
      return {
        id: String(v.id),
        source: "pexels",
        type: "video",
        url: file.link,
        filename: `pexels-${v.id}.${file.file_type === "video/quicktime" ? "mov" : "mp4"}`,
        durationSec: v.duration,
        width: file.width,
        height: file.height,
        mimeType: file.file_type,
      };
    });

  if (videos.length < 4) {
    console.warn(`Warning: only found ${videos.length} Pexels videos (wanted 4)`);
  }
  return videos;
}

async function freesoundSearch() {
  const url = new URL("https://freesound.org/apiv2/search/text/");
  url.searchParams.set("query", "ambient music background");
  url.searchParams.set("filter", 'duration:[50 TO 70] license:"Creative Commons 0"');
  url.searchParams.set("sort", "downloads_desc");
  url.searchParams.set("fields", "id,name,previews,duration,type,license");
  url.searchParams.set("page_size", "10");

  const res = await fetch(url, {
    headers: { Authorization: `Token ${FREESOUND_API_TOKEN}` },
  });
  if (!res.ok) throw new Error(`Freesound API ${res.status}: ${await res.text()}`);
  const data = await res.json();

  const sounds = (data.results || [])
    .filter((s) => s.duration >= 50 && s.duration <= 70)
    .slice(0, 1)
    .map((s) => ({
      id: String(s.id),
      source: "freesound",
      type: "audio",
      url: s.previews["preview-hq-mp3"],
      filename: `freesound-${s.id}.mp3`,
      durationSec: Math.round(s.duration),
      mimeType: "audio/mpeg",
    }));

  if (sounds.length === 0) {
    throw new Error("No suitable Freesound audio found (need CC0, 50–70s)");
  }
  return sounds;
}

async function main() {
  mkdirSync(FIXTURES_DIR, { recursive: true });

  console.log("Querying Pexels...");
  const videos = await pexelsSearch();
  console.log(`Found ${videos.length} videos`);

  console.log("Querying Freesound...");
  const audios = await freesoundSearch();
  console.log(`Found ${audios.length} audio tracks`);

  const manifest = {
    generatedAt: new Date().toISOString(),
    fixtures: [...videos, ...audios],
  };

  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2));
  console.log(`Wrote manifest → ${MANIFEST_PATH}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
