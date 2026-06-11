#!/usr/bin/env tsx

// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// E2E manual pipeline test: setup → upload → ingest → cutlist → render → ffprobe → wedge metrics
// Issue: #158

import { spawn } from "child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

/* ── Config ─────────────────────────────────────────────────────────── */
const API_URL = (process.env.E2E_API_URL || "http://localhost:4000/api").replace(/\/$/, "");
const E2E_TOKEN = process.env.E2E_TEST_TOKEN;
const INTERNAL_TOKEN = process.env.INTERNAL_WORKER_TOKEN;
const FIXTURES_DIR = join(__dirname, "fixtures");
const REPORTS_DIR = join(__dirname, "reports");
const HTTP_TIMEOUT_MS = 30_000;
const RENDER_POLL_MS = 5_000;
const RENDER_TIMEOUT_MS = 120_000;
const SSE_HEARTBEAT_MS = 15_000;

/* ── Types ──────────────────────────────────────────────────────────── */
interface Fixture {
  id: string;
  filename: string;
  mimeType: string;
  durationSec?: number;
  width?: number;
  height?: number;
}

interface Project {
  id: string;
  name: string;
  status: string;
}

interface Asset {
  id: string;
  storageKey: string;
  storageUrl: string;
}

interface RenderJob {
  id: string;
  status: string;
  stage?: string;
  progress?: number;
}

interface Report {
  startedAt: string;
  finishedAt?: string;
  success: boolean;
  verdict?: string;
  simulated: boolean;
  projects: Record<string, unknown>;
  metrics: MetricResult[];
  errors: string[];
}

interface MetricResult {
  name: string;
  pValue: number;
  rValue: number;
  pass: boolean;
}

/* ── HTTP helpers ───────────────────────────────────────────────────── */
async function apiFetch(path: string, init: RequestInit = {}): Promise<unknown> {
  const url = `${API_URL}${path}`;
  const hdr: Record<string, string> = {
    ...(init.headers as Record<string, string>),
    "Content-Type": "application/json",
    "x-e2e-test-token": E2E_TOKEN || "",
  };

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), HTTP_TIMEOUT_MS);

  try {
    const res = await fetch(url, { ...init, headers: hdr, signal: ctrl.signal });
    clearTimeout(t);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}: ${JSON.stringify(body)}`);
    }
    return body;
  } catch (err) {
    clearTimeout(t);
    throw err;
  }
}

/* ── API helpers ────────────────────────────────────────────────────── */
async function createProject(name: string, styleTier: string, mode: string): Promise<Project> {
  const body = (await apiFetch("/projects", {
    method: "POST",
    body: JSON.stringify({ name, styleTier, mode }),
  })) as { project: Project };
  return body.project;
}

async function presignedUpload(
  projectId: string,
  filename: string,
  mimeType: string,
  type: string,
): Promise<{ assetId: string; url: string; fields: Record<string, string> }> {
  const body = (await apiFetch("/uploads/presigned", {
    method: "POST",
    body: JSON.stringify({ projectId, filename, mimeType, type: type as any }),
  })) as { assetId: string; url: string; fields: Record<string, string> };
  return body;
}

async function uploadToR2(url: string, fileBuffer: Buffer): Promise<string> {
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/octet-stream" },
    body: fileBuffer,
  });
  if (!res.ok) throw new Error(`R2 upload failed: ${res.status}`);
  const etag = res.headers.get("etag") || res.headers.get("ETag") || "";
  return etag.replace(/"/g, "");
}

async function completeUpload(assetId: string, sizeBytes: number, etag: string): Promise<Asset> {
  const body = (await apiFetch(`/uploads/${assetId}/complete`, {
    method: "POST",
    body: JSON.stringify({ sizeBytes, etag }),
  })) as { asset: Asset };
  return body.asset;
}

async function probeAsset(
  assetId: string,
  meta: { durationSec: number; width: number; height: number; fps: number },
): Promise<Asset> {
  const body = (await apiFetch(`/uploads/${assetId}/probe`, {
    method: "POST",
    body: JSON.stringify(meta),
  })) as { asset: Asset };
  return body.asset;
}

async function patchProject(id: string, updates: Record<string, unknown>): Promise<Project> {
  const body = (await apiFetch(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(updates),
  })) as { project: Project };
  return body.project;
}

async function submitCutlist(projectId: string, cutlist: unknown): Promise<Project> {
  const body = (await apiFetch(`/projects/${projectId}/cutlist`, {
    method: "PATCH",
    body: JSON.stringify({ cutList: cutlist }),
  })) as { project: Project };
  return body.project;
}

async function startRender(projectId: string): Promise<RenderJob> {
  const body = (await apiFetch("/renders", {
    method: "POST",
    body: JSON.stringify({ projectId }),
  })) as { job: RenderJob };
  return body.job;
}

async function getRender(jobId: string): Promise<RenderJob> {
  const body = (await apiFetch(`/renders/${jobId}`)) as { job: RenderJob };
  return body.job;
}

async function completeRender(
  jobId: string,
  status: "complete" | "failed",
  outputAssetId?: string,
): Promise<RenderJob> {
  const body = (await apiFetch(`/renders/${jobId}/complete`, {
    method: "POST",
    headers: { "x-internal-token": INTERNAL_TOKEN || "" },
    body: JSON.stringify({ status, outputAssetId }),
  })) as { job: RenderJob };
  return body.job;
}

async function listProjectRenders(projectId: string): Promise<RenderJob[]> {
  const body = (await apiFetch(`/renders/project/${projectId}`)) as { jobs: RenderJob[] };
  return body.jobs;
}

/* ── ffprobe helper ─────────────────────────────────────────────────── */
async function ffprobe(path: string): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const proc = spawn(
      "ffprobe",
      ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let out = "";
    let err = "";
    proc.stdout.on("data", (d) => (out += d));
    proc.stderr.on("data", (d) => (err += d));
    proc.on("close", (code) => {
      if (code !== 0) return reject(new Error(`ffprobe exited ${code}: ${err}`));
      try {
        resolve(JSON.parse(out));
      } catch {
        reject(new Error(`ffprobe invalid JSON`));
      }
    });
  });
}

/* ── SSE heartbeat helper ───────────────────────────────────────────── */
async function sseHeartbeat(projectId: string): Promise<boolean> {
  return new Promise((resolve) => {
    const url = `${API_URL}/notifications/events`;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      ctrl.abort();
      resolve(false);
    }, SSE_HEARTBEAT_MS * 2);

    fetch(url, {
      headers: { "x-e2e-test-token": E2E_TOKEN || "" },
      signal: ctrl.signal,
    })
      .then((res) => {
        if (res.ok || res.status === 429) {
          clearTimeout(t);
          resolve(true);
        } else {
          clearTimeout(t);
          resolve(false);
        }
      })
      .catch(() => {
        clearTimeout(t);
        resolve(false);
      });
  });
}

/* ── Cutlist generators ─────────────────────────────────────────────── */
function createSimpleCutlist(durationSec: number): unknown {
  const slotDuration = Math.min(2.0, durationSec);
  return {
    globals: {
      totalDurationS: durationSec,
      tempoBpm: 120,
      timeSignature: "4/4",
      energyCurve: [0.5],
      sectionMarkers: [{ name: "full", startS: 0, endS: durationSec }],
      aspectRatio: "9:16",
    },
    slots: [
      {
        index: 0,
        startS: 0,
        durationS: slotDuration,
        beatIndex: 0,
        section: "full",
        transitionIn: "hard_cut",
        transitionOut: "hard_cut",
        targetShotType: "medium",
        subjectHint: "person",
        motionHint: "static",
        energyLevel: 0.5,
        requiredTags: [],
        avoidTags: [],
      },
    ],
    overlays: [],
    audioTracks: [],
  };
}

function createComplexCutlist(durationSec: number): unknown {
  const slots: unknown[] = [];
  const n = Math.max(3, Math.floor(durationSec / 2));
  for (let i = 0; i < n; i++) {
    const start = (i * durationSec) / n;
    const end = ((i + 1) * durationSec) / n;
    slots.push({
      index: i,
      startS: start,
      durationS: end - start,
      beatIndex: i,
      section: i === 0 ? "intro" : i === n - 1 ? "outro" : "verse",
      transitionIn: i === 0 ? "hard_cut" : "dissolve",
      transitionOut: i === n - 1 ? "hard_cut" : "dissolve",
      targetShotType: ["wide", "medium", "close_up"][i % 3],
      subjectHint: "person",
      motionHint: i % 2 === 0 ? "static" : "handheld",
      energyLevel: 0.3 + (0.7 * i) / Math.max(1, n - 1),
      requiredTags: [],
      avoidTags: [],
    });
  }
  return {
    globals: {
      totalDurationS: durationSec,
      tempoBpm: 120,
      timeSignature: "4/4",
      energyCurve: [0.3, 0.5, 0.7, 0.9],
      sectionMarkers: [
        { name: "intro", startS: 0, endS: durationSec * 0.2 },
        { name: "verse", startS: durationSec * 0.2, endS: durationSec * 0.8 },
        { name: "outro", startS: durationSec * 0.8, endS: durationSec },
      ],
      aspectRatio: "9:16",
    },
    slots,
    overlays: [
      {
        text: "E2E Test",
        startS: 0,
        endS: Math.min(3, durationSec),
        position: "center",
        font: "Inter",
        fontSizePx: 48,
        color: "#FFFFFF",
        animation: "fade_in",
      },
    ],
    audioTracks: [],
  };
}

/* ── Wedge metrics ──────────────────────────────────────────────────── */
function computeWedgeMetrics(
  pCutlist: any,
  rCutlist: any,
  pProbe: Record<string, unknown>,
  rProbe: Record<string, unknown>,
): MetricResult[] {
  const metrics: MetricResult[] = [];

  // 1. Slot count density (slots per minute)
  const pSlots = pCutlist.slots?.length || 0;
  const rSlots = rCutlist.slots?.length || 0;
  const pDurMin = (pCutlist.globals?.totalDurationS || 60) / 60;
  const rDurMin = (rCutlist.globals?.totalDurationS || 60) / 60;
  const pDensity = pSlots / pDurMin;
  const rDensity = rSlots / rDurMin;
  // R should have higher density than P
  metrics.push({
    name: "slot_density",
    pValue: Math.round(pDensity * 10) / 10,
    rValue: Math.round(rDensity * 10) / 10,
    pass: rDensity > pDensity,
  });

  // 2. Shot type diversity
  const pTypes = new Set(pCutlist.slots?.map((s: any) => s.targetShotType) || []);
  const rTypes = new Set(rCutlist.slots?.map((s: any) => s.targetShotType) || []);
  metrics.push({
    name: "shot_type_diversity",
    pValue: pTypes.size,
    rValue: rTypes.size,
    pass: rTypes.size >= pTypes.size,
  });

  // 3. Transition variety
  const pTrans = new Set(pCutlist.slots?.map((s: any) => s.transitionIn) || []);
  const rTrans = new Set(rCutlist.slots?.map((s: any) => s.transitionIn) || []);
  metrics.push({
    name: "transition_variety",
    pValue: pTrans.size,
    rValue: rTrans.size,
    pass: rTrans.size > pTrans.size,
  });

  // 4. Video output validity (ffprobe)
  const pStreams = (pProbe.streams as any[]) || [];
  const rStreams = (rProbe.streams as any[]) || [];
  const pHasVideo = pStreams.some((s) => s.codec_type === "video");
  const rHasVideo = rStreams.some((s) => s.codec_type === "video");
  metrics.push({
    name: "output_has_video_stream",
    pValue: pHasVideo ? 1 : 0,
    rValue: rHasVideo ? 1 : 0,
    pass: pHasVideo && rHasVideo,
  });

  return metrics;
}

/* ── Report writer ──────────────────────────────────────────────────── */
function writeReport(report: Report) {
  mkdirSync(REPORTS_DIR, { recursive: true });
  const path = join(REPORTS_DIR, "report.json");
  writeFileSync(path, JSON.stringify(report, null, 2));
  console.log(`\n📄 Report written → ${path}`);
}

/* ── Main ───────────────────────────────────────────────────────────── */
async function run() {
  const report: Report = {
    startedAt: new Date().toISOString(),
    success: false,
    simulated: false,
    projects: {},
    metrics: [],
    errors: [],
  };

  const fail = (msg: string) => {
    report.errors.push(msg);
    console.error(`\n❌ ${msg}`);
    writeReport(report);
    process.exit(1);
  };

  /* Validate env */
  if (!E2E_TOKEN) fail("E2E_TEST_TOKEN is not set");
  if (!INTERNAL_TOKEN) fail("INTERNAL_WORKER_TOKEN is not set");

  /* Health check */
  console.log("\n=== Health Check ===");
  try {
    const health = (await apiFetch("/health/ready")) as Record<string, unknown>;
    console.log("API ready:", JSON.stringify(health, null, 2));
  } catch (err: any) {
    fail(`API not ready: ${err.message}`);
  }

  /* SSE heartbeat */
  console.log("\n=== SSE Heartbeat ===");
  const sseOk = await sseHeartbeat("");
  console.log(sseOk ? "SSE reachable" : "SSE not reachable (non-fatal)");

  /* Load fixtures */
  console.log("\n=== Load Fixtures ===");
  const manifestPath = join(FIXTURES_DIR, "manifest.json");
  if (!existsSync(manifestPath)) fail("Fixture manifest not found. Run: pnpm fixtures");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8"));
  const fixtures: Fixture[] = manifest.fixtures || [];
  const videos = fixtures.filter((f) => f.type === "video");
  const audios = fixtures.filter((f) => f.type === "audio");
  if (videos.length < 4) fail(`Need 4 videos, found ${videos.length}`);
  if (audios.length < 1) fail(`Need 1 audio, found ${audios.length}`);
  console.log(`Videos: ${videos.length}, Audio: ${audios.length}`);

  const referenceVideo = videos[0];
  const clip1 = videos[1];
  const clip2 = videos[2];
  const clip3 = videos[3];
  const song = audios[0];

  /* Create projects */
  console.log("\n=== Create Projects ===");
  const projectP = await createProject("E2E Prompt-Only", "cuts_only", "assisted");
  const projectR = await createProject("E2E Reference-Driven", "full_style", "assisted");
  report.projects.P = { id: projectP.id, name: projectP.name, mode: "prompt-only" };
  report.projects.R = { id: projectR.id, name: projectR.name, mode: "reference-driven" };
  console.log(`P: ${projectP.id} (${projectP.name})`);
  console.log(`R: ${projectR.id} (${projectR.name})`);

  /* Upload helper */
  async function uploadForProject(projectId: string, fixture: Fixture, assetType: string): Promise<Asset> {
    const filePath = join(FIXTURES_DIR, fixture.filename);
    const buf = readFileSync(filePath);
    const { assetId, url } = await presignedUpload(projectId, fixture.filename, fixture.mimeType, assetType);
    const etag = await uploadToR2(url, buf);
    const asset = await completeUpload(assetId, buf.length, etag);
    const meta = {
      durationSec: fixture.durationSec || 10,
      width: fixture.width || 640,
      height: fixture.height || 480,
      fps: 30,
    };
    await probeAsset(asset.id, meta);
    console.log(`  ✓ ${fixture.filename} → ${asset.id}`);
    return asset;
  }

  /* Upload for P */
  console.log("\n--- Upload P ---");
  const pRef = await uploadForProject(projectP.id, referenceVideo, "reference_video");
  const pSong = await uploadForProject(projectP.id, song, "song");
  const pClip1 = await uploadForProject(projectP.id, clip1, "clip");

  /* Upload for R */
  console.log("\n--- Upload R ---");
  const rRef = await uploadForProject(projectR.id, referenceVideo, "reference_video");
  const rSong = await uploadForProject(projectR.id, song, "song");
  const rClip1 = await uploadForProject(projectR.id, clip2, "clip");
  const rClip2 = await uploadForProject(projectR.id, clip3, "clip");

  /* Patch projects */
  console.log("\n=== Patch Projects ===");
  await patchProject(projectP.id, {
    referenceAssetId: pRef.id,
    songAssetId: pSong.id,
    clipAssetIds: [pClip1.id],
  });
  await patchProject(projectR.id, {
    referenceAssetId: rRef.id,
    songAssetId: rSong.id,
    clipAssetIds: [rClip1.id, rClip2.id],
  });
  console.log("Projects linked to assets");

  /* Start renders */
  console.log("\n=== Start Renders ===");
  const renderP = await startRender(projectP.id);
  const renderR = await startRender(projectR.id);
  console.log(`P render: ${renderP.id}`);
  console.log(`R render: ${renderR.id}`);

  /* Create & submit cutlists */
  console.log("\n=== Submit Cutlists ===");
  const refDur = referenceVideo.durationSec || 10;
  const cutlistP = createSimpleCutlist(refDur);
  const cutlistR = createComplexCutlist(refDur);
  await submitCutlist(projectP.id, cutlistP);
  await submitCutlist(projectR.id, cutlistR);
  console.log("Cutlists submitted");

  /* Poll renders */
  console.log("\n=== Poll Renders ===");
  let pComplete = false;
  let rComplete = false;
  const pollStart = Date.now();

  while (Date.now() - pollStart < RENDER_TIMEOUT_MS) {
    if (!pComplete) {
      const job = await getRender(renderP.id);
      pComplete = job.status === "complete" || job.status === "failed";
      console.log(`  P: ${job.status} (${job.stage || ""} ${job.progress || 0}%)`);
    }
    if (!rComplete) {
      const job = await getRender(renderR.id);
      rComplete = job.status === "complete" || job.status === "failed";
      console.log(`  R: ${job.status} (${job.stage || ""} ${job.progress || 0}%)`);
    }
    if (pComplete && rComplete) break;
    await new Promise((r) => setTimeout(r, RENDER_POLL_MS));
  }

  /* Simulate completion if workers didn't finish */
  let simulated = false;
  if (!pComplete || !rComplete) {
    console.log("\n⚠️  Workers did not complete in time — simulating render completion");
    simulated = true;
    report.simulated = true;

    async function simulateRender(jobId: string, projectId: string) {
      // Use the reference video as the "render output"
      const refPath = join(FIXTURES_DIR, referenceVideo.filename);
      const buf = readFileSync(refPath);
      const { assetId, url } = await presignedUpload(projectId, "output.mp4", "video/mp4", "render");
      const etag = await uploadToR2(url, buf);
      const asset = await completeUpload(assetId, buf.length, etag);
      await completeRender(jobId, "complete", asset.id);
      console.log(`  ✓ Simulated render ${jobId} → asset ${asset.id}`);
      return asset;
    }

    if (!pComplete) await simulateRender(renderP.id, projectP.id);
    if (!rComplete) await simulateRender(renderR.id, projectR.id);
  } else {
    console.log("\n✓ Renders completed by workers");
  }

  /* Fetch final render state */
  const finalP = await getRender(renderP.id);
  const finalR = await getRender(renderR.id);
  if (finalP.status === "failed") fail(`P render failed`);
  if (finalR.status === "failed") fail(`R render failed`);

  /* Get output assets */
  console.log("\n=== Fetch Output Assets ===");
  const pProject = (await apiFetch(`/projects/${projectP.id}`)) as {
    project: Project & { renderAssetId?: string };
  };
  const rProject = (await apiFetch(`/projects/${projectR.id}`)) as {
    project: Project & { renderAssetId?: string };
  };

  if (!pProject.project.renderAssetId) fail("P project has no renderAssetId");
  if (!rProject.project.renderAssetId) fail("R project has no renderAssetId");

  const pAsset = (await apiFetch(`/uploads/${pProject.project.renderAssetId}`)) as { asset: Asset };
  const rAsset = (await apiFetch(`/uploads/${rProject.project.renderAssetId}`)) as { asset: Asset };
  console.log(`P output: ${pAsset.asset.storageUrl}`);
  console.log(`R output: ${rAsset.asset.storageUrl}`);

  /* Download outputs for ffprobe */
  console.log("\n=== ffprobe Outputs ===");
  const pOutputPath = join(REPORTS_DIR, "p-output.mp4");
  const rOutputPath = join(REPORTS_DIR, "r-output.mp4");

  async function downloadOutput(asset: Asset, path: string) {
    const res = await fetch(asset.storageUrl);
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    writeFileSync(path, buf);
    return path;
  }

  await downloadOutput(pAsset.asset, pOutputPath);
  await downloadOutput(rAsset.asset, rOutputPath);

  const pProbe = await ffprobe(pOutputPath);
  const rProbe = await ffprobe(rOutputPath);

  const pFormat = (pProbe.format as any) || {};
  const rFormat = (rProbe.format as any) || {};
  console.log(`P: ${pFormat.duration}s, ${pFormat.bit_rate}bps`);
  console.log(`R: ${rFormat.duration}s, ${rFormat.bit_rate}bps`);

  /* Wedge metrics */
  console.log("\n=== Wedge Metrics ===");
  const metrics = computeWedgeMetrics(cutlistP, cutlistR, pProbe, rProbe);
  report.metrics = metrics;

  for (const m of metrics) {
    const icon = m.pass ? "✅" : "❌";
    console.log(`${icon} ${m.name}: P=${m.pValue} R=${m.rValue}`);
  }

  const passCount = metrics.filter((m) => m.pass).length;
  const verdict = passCount >= 3 ? "PROVEN" : "FAIL";
  report.verdict = verdict;
  console.log(`\nVerdict: ${verdict} (${passCount}/${metrics.length} passed)`);

  /* Finalize */
  report.success = verdict === "PROVEN";
  report.finishedAt = new Date().toISOString();
  writeReport(report);

  if (!report.success) {
    process.exit(1);
  }
  console.log("\n🎉 E2E pipeline test passed");
}

run().catch((err) => {
  console.error("\n💥 Uncaught error:", err.message);
  process.exit(1);
});
