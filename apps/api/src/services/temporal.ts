// Copyright (c) 2025 Devayan Dewri. All rights reserved.
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

export async function startRenderWorkflow(
  projectId: string,
  referenceAssetId: string,
  songAssetId: string,
  clipAssetIds: string[],
  styleTier: string,
  mode: string,
  userId: string,
  renderId?: string
) {
  const client = await getTemporalClient();
  const handle = await client.workflow.start("VideoRenderWorkflow", {
    taskQueue: "video-render-queue",
    args: [
      {
        project_id: projectId,
        reference_asset_id: referenceAssetId,
        song_asset_id: songAssetId,
        clip_asset_ids: clipAssetIds,
        style_tier: styleTier,
        mode,
        user_id: userId,
      },
    ],
    workflowId: `render-${projectId}-${renderId || Date.now()}`
  });

  return handle.workflowId;
}

export async function sendCutlistApprovedSignal(
  workflowId: string,
  cutList: any
) {
  const client = await getTemporalClient();
  const handle = client.workflow.getHandle(workflowId);
  await handle.signal("cutlist_approved", cutList);
}
