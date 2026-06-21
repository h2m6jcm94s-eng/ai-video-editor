#!/usr/bin/env node
// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Select portrait car-meet videos from Pexels + CC0 music from Freesound,
// write manifest to docs/assets/car-meet/ for README demo media.

import { writeFileSync, mkdirSync, readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS_DIR = join(__dirname, "..", "docs", "assets", "car-meet");
const MANIFEST_PATH = join(ASSETS_DIR, "manifest.json");

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

async function pexelsSearch(query, orientation = "portrait") {
  const url = new URL("https://api.pexels.com/videos/search");
  url.searchParams.set("query", query);
  url.searchParams.set("orientation", orientation);
  url.searchParams.set("size", "small");
  url.searchParams.set("per_page", "80");

  const res = await fetch(url, {
    headers: { Authorization: PEXELS_API_KEY },
  });
  if (!res.ok) throw new Error(`Pexels API ${res.status}: ${await res.text()}`);
  return res.json();
}

async function selectCarMeetVideos() {
  const data = await pexelsSearch("car meet");

  const videos = (data.videos || [])
    .filter((v) => v.duration >= 8 && v.duration <= 20)
    .map((v) => {
      const candidates = (v.video_files || []).filter(
        (f) => f.file_type === "video/mp4" && f.width < f.height && f.width >= 720
      );
      if (candidates.length === 0) return null;
      // Pick the highest-resolution portrait MP4 for quality.
      const file = candidates.sort((a, b) => b.width - a.width)[0];
      return { v, file };
    })
    .filter(Boolean)
    .sort((a, b) => a.v.id - b.v.id)
    .slice(0, 4)
    .map(({ v, file }, idx) => {
      const role = idx === 0 ? "reference" : `clip-${idx}`;
      return {
        id: String(v.id),
        source: "pexels",
        type: "video",
        url: file.link,
        filename: `${role}.mp4`,
        durationSec: v.duration,
        width: file.width,
        height: file.height,
        mimeType: file.file_type,
      };
    });

  if (videos.length < 4) {
    console.warn(`Warning: only found ${videos.length} Pexels car-meet videos (wanted 4)`);
  }
  return videos;
}

async function selectSong() {
  const queries = ["phonk", "trap beat", "car music", "drift phonk"];
  for (const query of queries) {
    const url = new URL("https://freesound.org/apiv2/search/text/");
    url.searchParams.set("query", query);
    url.searchParams.set("filter", 'duration:[45 TO 90] license:"Creative Commons 0"');
    url.searchParams.set("sort", "downloads_desc");
    url.searchParams.set("fields", "id,name,previews,duration,type,license");
    url.searchParams.set("page_size", "10");

    const res = await fetch(url, {
      headers: { Authorization: `Token ${FREESOUND_API_TOKEN}` },
    });
    if (!res.ok) throw new Error(`Freesound API ${res.status}: ${await res.text()}`);
    const data = await res.json();

    const sounds = (data.results || [])
      .filter((s) => s.duration >= 45 && s.duration <= 90)
      .slice(0, 1)
      .map((s) => ({
        id: String(s.id),
        source: "freesound",
        type: "audio",
        url: s.previews["preview-hq-mp3"],
        filename: "song.mp3",
        durationSec: Math.round(s.duration),
        mimeType: "audio/mpeg",
      }));

    if (sounds.length > 0) return sounds;
  }
  throw new Error("No suitable CC0 song found on Freesound");
}

async function main() {
  mkdirSync(ASSETS_DIR, { recursive: true });

  console.log("Querying Pexels for car-meet videos...");
  const videos = await selectCarMeetVideos();
  console.log(`Found ${videos.length} car-meet videos`);

  console.log("Querying Freesound for a song...");
  const audios = await selectSong();
  console.log(`Found ${audios.length} song(s)`);

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
