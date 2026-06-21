// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { motion } from "framer-motion";
import { AlertCircle, Clock, Loader2, Play, Wand2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/lib/api/client";
import type { Asset, Project } from "@/types/api";

function StatusBadge({ status }: { status: Project["status"] }) {
  const variants: Record<string, { classes: string; icon: React.ReactNode; label: string }> = {
    uploading: {
      classes: "bg-amber-500/10 text-amber-300 border-amber-500/20",
      icon: <Loader2 className="w-3 h-3 animate-spin" />,
      label: "Uploading",
    },
    processing: {
      classes: "bg-indigo-500/10 text-indigo-300 border-indigo-500/20",
      icon: <Wand2 className="w-3 h-3 animate-pulse" />,
      label: "Processing",
    },
    rendering: {
      classes: "bg-purple-500/10 text-purple-300 border-purple-500/20",
      icon: <Loader2 className="w-3 h-3 animate-spin" />,
      label: "Rendering",
    },
    complete: {
      classes: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
      icon: <Play className="w-3 h-3" />,
      label: "Ready",
    },
    failed: {
      classes: "bg-red-500/10 text-red-300 border-red-500/20",
      icon: <AlertCircle className="w-3 h-3" />,
      label: "Failed",
    },
  };
  const config = variants[status] || variants.processing;
  return (
    <Badge variant="outline" className={`gap-1.5 capitalize backdrop-blur-md ${config.classes}`}>
      {config.icon}
      {config.label}
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
      <div className="w-full h-full flex items-center justify-center bg-black/20">
        <div className="w-14 h-14 rounded-2xl bg-white/[0.05] border border-white/[0.08] flex items-center justify-center">
          <Play className="w-6 h-6 text-glass-subtle" />
        </div>
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
      className="w-full h-full object-cover group-hover:scale-110 transition duration-700 ease-out"
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
      <motion.div
        whileHover={{ y: -6, scale: 1.01 }}
        transition={{ type: "spring", stiffness: 300, damping: 22 }}
      >
        <Card className="glass-card overflow-hidden group cursor-pointer glow-hover border-white/[0.08] hover:border-white/[0.16]">
          <div className="aspect-video relative overflow-hidden">
            <Thumbnail renderAssetId={project.renderAssetId} alt={project.name} />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-60 group-hover:opacity-80 transition-opacity" />
            <div className="absolute top-3 right-3">
              <StatusBadge status={project.status} />
            </div>
            <div className="absolute bottom-3 left-3 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <div className="flex items-center gap-2 text-xs font-medium text-white">
                <Play className="w-3.5 h-3.5" />
                Open editor
              </div>
            </div>
          </div>
          <CardContent className="p-5">
            <h3 className="font-semibold text-glass truncate group-hover:text-gradient transition-all">
              {project.name}
            </h3>
            <div className="flex items-center gap-2 mt-2 text-xs text-glass-faint">
              <Clock className="w-3.5 h-3.5" />
              <span>Updated {new Date(project.updatedAt).toLocaleDateString()}</span>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </Link>
  );
}
