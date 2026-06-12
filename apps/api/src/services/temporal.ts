// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import type { CutList } from "@ai-video-editor/shared-types";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { Client, Connection } from "@temporalio/client";
import { env } from "../env";

let temporalClient: Client | null = null;
let lastConnectAttempt = 0;

export async function getTemporalClient(): Promise<Client> {
  const now = Date.now();
  if (!temporalClient || now - lastConnectAttempt > 5 * 60 * 1000) {
    lastConnectAttempt = now;
    try {
      const connection = await Connection.connect({ address: env.TEMPORAL_HOST });
      temporalClient = new Client({ connection });
    } catch (e) {
      // If connect failed, clear the cached attempt time so the next caller retries immediately.
      lastConnectAttempt = 0;
      throw e;
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
  referenceAssetId: string;
  songAssetId: string;
  clipAssetIds: string[];
  styleTier: string;
  mode: string;
  userId: string;
  renderId?: string;
  assetKeyMap?: Record<string, string>;
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
        },
      ],
      workflowId: `render-${options.projectId}-${options.renderId || Date.now()}`,
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

export async function sendCutlistApprovedSignal(workflowId: string, cutList: CutList) {
  return withTemporalReconnect(async (client) => {
    const handle = client.workflow.getHandle(workflowId);
    await handle.signal("cutlist_approved", cutList);
  });
}
