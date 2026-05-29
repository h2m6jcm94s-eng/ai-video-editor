import { Client } from "@temporalio/client";

let temporalClient: Client | null = null;
let lastConnectAttempt = 0;

export async function getTemporalClient(): Promise<Client> {
  const now = Date.now();
  // Reconnect if client is null or if 5 minutes have passed since last attempt
  if (!temporalClient || now - lastConnectAttempt > 5 * 60 * 1000) {
    lastConnectAttempt = now;
    temporalClient = await Client.connect({
      address: process.env.TEMPORAL_HOST || "localhost:7233",
    });
  }
  return temporalClient;
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
