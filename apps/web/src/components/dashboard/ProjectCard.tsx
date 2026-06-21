// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { AlertCircle, Clock, Loader2, Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/lib/api/client";
import type { Asset, Project } from "@/types/api";

function StatusBadge({ status }: { status: Project["status"] }) {
  const variants: Record<
    string,
    { variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ReactNode }
  > = {
    uploading: { variant: "secondary", icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    processing: { variant: "outline", icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    complete: { variant: "default", icon: <Play className="w-3 h-3" /> },
    failed: { variant: "destructive", icon: <AlertCircle className="w-3 h-3" /> },
  };
  const config = variants[status] || variants.processing;
  return (
    <Badge variant={config.variant} className="gap-1 capitalize">
      {config.icon}
      {status}
    </Badge>
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
      <div className="w-full h-full flex items-center justify-center text-zinc-600">
        <Play className="w-8 h-8" />
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
      className="w-full h-full object-cover group-hover:scale-105 transition duration-500"
      aria-label={alt}
      onLoadedData={(e) => {
        const video = e.currentTarget;
        video.pause();
      }}
    />
  );
}

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/editor/${project.id}`}>
      <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition cursor-pointer overflow-hidden group">
        <div className="aspect-video bg-zinc-950 relative overflow-hidden">
          <Thumbnail renderAssetId={project.renderAssetId} alt={project.name} />
          <div className="absolute top-2 right-2">
            <StatusBadge status={project.status} />
          </div>
        </div>
        <CardContent className="p-4">
          <h3 className="font-medium truncate">{project.name}</h3>
          <div className="flex items-center gap-2 mt-2 text-xs text-zinc-500">
            <Clock className="w-3 h-3" />
            <span>{new Date(project.updatedAt).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
