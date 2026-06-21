// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import type { CutList } from "@ai-video-editor/shared-types";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { Client, Connection, WorkflowIdReusePolicy } from "@temporalio/client";
import { env } from "../env";

let temporalClient: Client | null = null;
let lastConnectAttempt = 0;

export async function getTemporalClient(): Promise<Client> {
  const now = Date.now();
  if (!temporalClient || now - lastConnectAttempt > 5 * 60 * 1000) {
    lastConnectAttempt = now;
    // Close any previously cached connection to avoid leaking gRPC sockets.
    const previousConnection = temporalClient?.connection;
    temporalClient = null;
    try {
      const connection = await Connection.connect({ address: env.TEMPORAL_HOST });
      temporalClient = new Client({ connection });
    } catch (e) {
      // If connect failed, clear the cached attempt time so the next caller retries immediately.
      lastConnectAttempt = 0;
      throw e;
    } finally {
      try {
        await previousConnection?.close();
      } catch {
        // ignore close errors
      }
    }
  }
  return temporalClient!;
}

async function withTemporalReconnect<T>(call: (client: Client) => Promise<T>): Promise<T> {
  try {
    return await call(await getTemporalClient());
  } catch (e) {
    // If the cached connection is dead, reset it and try once more.
    const message = e instanceof Error ? e.message : String(e);
    const isConnectionError =
      message.includes("Connection") ||
      message.includes("closed") ||
      message.includes("ECONNREFUSED") ||
      message.includes("UNAVAILABLE");
    if (!isConnectionError) throw e;
    temporalClient = null;
    lastConnectAttempt = 0;
    return await call(await getTemporalClient());
  }
}

export interface StartRenderOptions {
  projectId: string;
  referenceAssetId?: string | null;
  songAssetId: string;
  clipAssetIds: string[];
  styleTier: string;
  mode: string;
  userId: string;
  renderId?: string;
  completionToken?: string;
  assetKeyMap?: Record<string, string>;
  styleAnalysis?: Record<string, unknown> | null;
  maskAssetIds?: string[];
  maskSourceMap?: Record<string, string>;
}

export interface StartAnalyzeStyleOptions {
  assetId: string;
  storageKey: string;
  shotBoundaries?: Record<string, unknown>[];
  lutStrength?: number;
  textSampleFps?: number;
}

export async function startRenderWorkflow(options: StartRenderOptions) {
  return withTemporalReconnect(async (client) => {
    const handle = await client.workflow.start("VideoRenderWorkflow", {
      taskQueue: "video-render-queue",
      args: [
        {
          project_id: options.projectId,
          reference_asset_id: options.referenceAssetId,
          song_asset_id: options.songAssetId,
          clip_asset_ids: options.clipAssetIds,
          style_tier: options.styleTier,
          mode: options.mode,
          user_id: options.userId,
          asset_key_map: options.assetKeyMap || {},
          style_analysis: options.styleAnalysis || null,
          mask_asset_ids: options.maskAssetIds || [],
          mask_source_map: options.maskSourceMap || {},
          completion_token: options.completionToken,
        },
      ],
      workflowId: `render-${options.projectId}-${options.renderId || "new"}`,
    });

    return handle.workflowId;
  });
}

export async function startAnalyzeStyleWorkflow(options: StartAnalyzeStyleOptions) {
  return withTemporalReconnect(async (client) => {
    const handle = await client.workflow.start("AnalyzeStyleWorkflow", {
      taskQueue: "style",
      args: [
        {
          asset_id: options.assetId,
          storage_key: options.storageKey,
          shot_boundaries: options.shotBoundaries || [],
          lut_strength: options.lutStrength ?? 0.5,
          text_sample_fps: options.textSampleFps ?? 5.0,
        },
      ],
      workflowId: `style-${options.assetId}`,
    });
    return handle.workflowId;
  });
}

export async function startProbeWorkflow(assetId: string, storageKey: string) {
  return withTemporalReconnect(async (client) => {
    const handle = await client.workflow.start("ProbeAssetWorkflow", {
      taskQueue: "ingest",
      args: [{ asset_id: assetId, storage_key: storageKey }],
      workflowId: `probe-${assetId}`,
    });
    return handle.workflowId;
  });
}

export async function getStyleAnalysisFromWorkflow(assetId: string) {
  return withTemporalReconnect(async (client) => {
    const handle = client.workflow.getHandle(`style-${assetId}`);
    try {
      // Query the running/completed workflow for its current output.
      return await handle.query("get_analysis");
    } catch (e) {
      // Workflow may not exist yet or may have already completed and been cleaned up.
      return null;
    }
  });
}

export async function sendCutlistApprovedSignal(workflowId: string, cutList: CutList) {
  return withTemporalReconnect(async (client) => {
    const handle = client.workflow.getHandle(workflowId);
    await handle.signal("cutlist_approved", cutList);
  });
}

export interface StartSegmentSubjectOptions {
  assetId: string;
  projectId: string;
  storageKey: string;
  prompt: string;
  mode?: "image" | "video";
  frameIndex?: number;
}

export async function startSegmentSubjectWorkflow(options: StartSegmentSubjectOptions) {
  return withTemporalReconnect(async (client) => {
    const handle = await client.workflow.start("SegmentSubjectWorkflow", {
      taskQueue: "segment",
      args: [
        {
          asset_id: options.assetId,
          project_id: options.projectId,
          storage_key: options.storageKey,
          prompt: options.prompt,
          mode: options.mode || "image",
          frame_index: options.frameIndex ?? 0,
        },
      ],
      workflowId: `segment-${options.assetId}-${options.projectId}`,
      workflowIdReusePolicy: WorkflowIdReusePolicy.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
    });
    return handle.workflowId;
  });
}
