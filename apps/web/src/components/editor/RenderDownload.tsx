// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/client";
import type { RenderJob } from "@/types/api";

interface RenderDownloadProps {
  render: RenderJob;
}

export function RenderDownload({ render }: RenderDownloadProps) {
  const api = useApi();
  const [fetching, setFetching] = useState(false);

  if (render.status !== "complete" || !render.outputAssetId) {
    return null;
  }

  const handleClick = async () => {
    const assetId = render.outputAssetId;
    if (!assetId) return;
    setFetching(true);
    try {
      const { asset } = await api.uploads.get(assetId);
      if (!asset.storageUrl) {
        throw new Error("Download URL not available");
      }
      const a = document.createElement("a");
      a.href = asset.storageUrl;
      a.download = asset.filename || "render.mp4";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Download failed", err);
    } finally {
      setFetching(false);
    }
  };

  return (
    <Button
      size="sm"
      variant="outline"
      className="gap-2 text-xs border-zinc-700 hover:bg-zinc-800"
      onClick={handleClick}
      disabled={fetching}
      data-testid="download-render"
    >
      {fetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      Download
    </Button>
  );
}
