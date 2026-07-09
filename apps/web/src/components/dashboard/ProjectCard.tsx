// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { AlertCircle, Clock, Loader2, Play, Wand2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/api/client";
import type { Asset, Project } from "@/types/api";

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; label: string }> = {
  uploading: { icon: <Loader2 className="dash-spin" />, label: "Uploading" },
  processing: { icon: <Wand2 />, label: "Processing" },
  rendering: { icon: <Loader2 className="dash-spin" />, label: "Rendering" },
  complete: { icon: <Play />, label: "Ready" },
  failed: { icon: <AlertCircle />, label: "Failed" },
};

function StatusBadge({ status }: { status: Project["status"] }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.processing;
  return (
    <span className="dash-badge" data-status={status}>
      {config.icon}
      {config.label}
    </span>
  );
}

function Thumbnail({ renderAssetId, alt }: { renderAssetId: string | null; alt: string }) {
  const api = useApi();
  const [asset, setAsset] = useState<Asset | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!renderAssetId) return;
    let cancelled = false;
    setLoading(true);
    api.uploads
      .get(renderAssetId)
      .then(({ asset }) => {
        if (!cancelled) setAsset(asset);
      })
      .catch(() => {
        // ignore; keep placeholder
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [renderAssetId, api]);

  if (!renderAssetId || loading || !asset?.storageUrl) {
    return (
      <div className="dash-project-placeholder">
        <Play />
      </div>
    );
  }

  return (
    // eslint-disable-next-line jsx-a11y/media-has-caption
    <video
      src={asset.storageUrl}
      preload="metadata"
      muted
      playsInline
      aria-label={alt}
      onLoadedData={(e) => {
        e.currentTarget.pause();
      }}
    />
  );
}

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/editor/${project.id}`} className="dash-project">
      <div className="dash-project-thumb">
        <StatusBadge status={project.status} />
        <Thumbnail renderAssetId={project.renderAssetId} alt={project.name} />
        <span className="bracket tl" />
        <span className="bracket br" />
      </div>
      <div className="dash-project-body">
        <h3 className="dash-project-title">{project.name}</h3>
        <div className="dash-project-meta">
          <Clock />
          <span>Updated {new Date(project.updatedAt).toLocaleDateString()}</span>
        </div>
      </div>
    </Link>
  );
}
