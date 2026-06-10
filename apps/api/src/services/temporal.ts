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
    const connection = await Connection.connect({ address: env.TEMPORAL_HOST });
    temporalClient = new Client({ connection });
  }
  return temporalClient!;
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
  const client = await getTemporalClient();
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
}

export async function startProbeWorkflow(assetId: string, storageKey: string) {
  const client = await getTemporalClient();
  const handle = await client.workflow.start("ProbeAssetWorkflow", {
    taskQueue: "ingest",
    args: [{ asset_id: assetId, storage_key: storageKey }],
    workflowId: `probe-${assetId}`,
  });
  return handle.workflowId;
}

export async function sendCutlistApprovedSignal(workflowId: string, cutList: CutList) {
  const client = await getTemporalClient();
  const handle = client.workflow.getHandle(workflowId);
  await handle.signal("cutlist_approved", cutList);
}
