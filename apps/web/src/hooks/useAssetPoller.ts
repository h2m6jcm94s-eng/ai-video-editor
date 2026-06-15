// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect, useRef } from "react";
import { useApi } from "@/lib/api/client";
import type { Asset } from "@/types/api";

const POLL_INTERVAL_MS = 2000;

function isPending(asset: Asset): boolean {
  // Treat durationSec == null or 0 as still being ingested.
  return asset.durationSec == null || asset.durationSec === 0;
}

/**
 * Polls the project endpoint until every uploaded asset has a duration.
 * Updates the parent asset list via onAssetsChange so the UI transitions
 * from data-state="uploading" to data-state="ingested" without a manual reload.
 */
export function useAssetPoller(
  projectId: string,
  assets: Asset[],
  onAssetsChange: (assets: Asset[]) => void,
): void {
  const api = useApi();
  const onChangeRef = useRef(onAssetsChange);
  onChangeRef.current = onAssetsChange;

  const hasPending = assets.some(isPending);

  useEffect(() => {
    if (!hasPending) return;

    let mounted = true;

    const tick = async () => {
      if (!mounted) return;
      try {
        const res = await api.projects.get(projectId);
        if (!mounted) return;
        onChangeRef.current(res.project.assets);
      } catch (err) {
        // Swallow poll errors — uploads/probe failures are surfaced via toasts.
        // eslint-disable-next-line no-console
        console.warn("[useAssetPoller] tick failed:", err);
      }
    };

    tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);

    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [projectId, hasPending, api]);
}
