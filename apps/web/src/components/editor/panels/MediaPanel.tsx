// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useState } from "react";
import { Upload, Film, Music, Video, ImageIcon } from "lucide-react";
import { useUpload } from "@/hooks/useUpload";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Asset } from "@/types/api";

interface MediaPanelProps {
  projectId: string;
  assets: Asset[];
  onAssetsChange: (assets: Asset[]) => void;
}

function AssetItem({ asset }: { asset: Asset }) {
  const icons = {
    reference: Video,
    song: Music,
    clip: Film,
  };
  const Icon = icons[asset.type as keyof typeof icons] || ImageIcon;

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("assetId", asset.id);
        e.dataTransfer.setData("assetType", asset.type);
      }}
      className="flex items-center gap-2 p-2 rounded-lg hover:bg-zinc-800 cursor-grab active:cursor-grabbing transition"
      role="button"
      aria-label={`Drag ${asset.filename}`}
    >
      <div className="w-8 h-8 rounded bg-zinc-800 flex items-center justify-center shrink-0">
        <Icon className="w-4 h-4 text-zinc-400" />
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium truncate">{asset.filename}</p>
        <p className="text-[10px] text-zinc-500">
          {asset.durationSec ? `${asset.durationSec.toFixed(1)}s` : ""}
          {asset.width ? ` · ${asset.width}×${asset.height}` : ""}
        </p>
      </div>
    </div>
  );
}

export function MediaPanel({ projectId, assets, onAssetsChange }: MediaPanelProps) {
  const [activeTab, setActiveTab] = useState<"all" | "reference" | "song" | "clip">("all");
  const { uploadFile, uploading } = useUpload(projectId);
  const fileInputRef = useCallback((node: HTMLInputElement | null) => {
    // no-op, used for ref assignment in JSX
  }, []);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>, type: Asset["type"]) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const asset = await uploadFile(file, type);
    if (asset) onAssetsChange([...assets, asset]);
  };

  const filtered = assets.filter((a) => (activeTab === "all" ? true : a.type === activeTab));

  const tabs: { key: typeof activeTab; label: string; icon: React.ReactNode }[] = [
    { key: "all", label: "All", icon: <ImageIcon className="w-3 h-3" /> },
    { key: "reference", label: "Ref", icon: <Video className="w-3 h-3" /> },
    { key: "song", label: "Song", icon: <Music className="w-3 h-3" /> },
    { key: "clip", label: "Clips", icon: <Film className="w-3 h-3" /> },
  ];

  return (
    <div className="w-[260px] border-r border-zinc-800 flex flex-col bg-zinc-950 shrink-0">
      <div className="h-10 border-b border-zinc-800 flex items-center px-3 gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition ${
              activeTab === t.key ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      <ScrollArea className="flex-1 px-2 py-2">
        <div className="space-y-1">
          {filtered.map((asset) => (
            <AssetItem key={asset.id} asset={asset} />
          ))}
          {filtered.length === 0 && (
            <p className="text-xs text-zinc-600 text-center py-8">No assets yet</p>
          )}
        </div>
      </ScrollArea>

      <div className="p-3 border-t border-zinc-800 space-y-2">
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          id="upload-clip"
          onChange={(e) => handleFileChange(e, "clip")}
        />
        <label htmlFor="upload-clip">
          <Button variant="outline" className="w-full gap-2 text-xs" size="sm" disabled={uploading} asChild>
            <span>
              <Upload className="w-3 h-3" />
              {uploading ? "Uploading..." : "Upload Clip"}
            </span>
          </Button>
        </label>
      </div>
    </div>
  );
}
