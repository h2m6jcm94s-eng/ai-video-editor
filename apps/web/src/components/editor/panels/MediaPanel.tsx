// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Film, ImageIcon, Music, Palette, Upload, Video } from "lucide-react";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUpload } from "@/hooks/useUpload";
import type { Asset } from "@/types/api";

interface MediaPanelProps {
  projectId: string;
  assets: Asset[];
  onAssetsChange: (assets: Asset[]) => void;
}

function AssetItem({ asset }: { asset: Asset }) {
  const icons = {
    reference_video: Video,
    song: Music,
    clip: Film,
    lut: Palette,
  };
  const Icon = icons[asset.type as keyof typeof icons] || ImageIcon;
  const isIngested = asset.durationSec != null && asset.durationSec > 0;

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
      data-testid={`asset-${asset.id}`}
      data-state={isIngested ? "ingested" : "uploading"}
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
  const [activeTab, setActiveTab] = useState<"all" | "reference_video" | "song" | "clip" | "lut">("all");
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
    { key: "reference_video", label: "Ref", icon: <Video className="w-3 h-3" /> },
    { key: "song", label: "Song", icon: <Music className="w-3 h-3" /> },
    { key: "clip", label: "Clips", icon: <Film className="w-3 h-3" /> },
    { key: "lut", label: "LUT", icon: <Palette className="w-3 h-3" /> },
  ];

  return (
    <div className="hidden md:flex md:w-[260px] border-r border-zinc-800 flex-col bg-zinc-950 shrink-0">
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
          {filtered.length === 0 && <p className="text-xs text-zinc-600 text-center py-8">No assets yet</p>}
        </div>
      </ScrollArea>

      <div className="p-3 border-t border-zinc-800 space-y-2">
        <input
          type="file"
          accept="video/*"
          className="hidden"
          id="upload-reference"
          data-testid="upload-reference"
          onChange={(e) => handleFileChange(e, "reference_video")}
        />
        <label htmlFor="upload-reference">
          <Button variant="outline" className="w-full gap-2 text-xs" size="sm" disabled={uploading} asChild>
            <span>
              <Upload className="w-3 h-3" />
              {uploading ? "Uploading..." : "Upload Reference"}
            </span>
          </Button>
        </label>

        <input
          type="file"
          accept="audio/*"
          className="hidden"
          id="upload-song"
          data-testid="upload-song"
          onChange={(e) => handleFileChange(e, "song")}
        />
        <label htmlFor="upload-song">
          <Button variant="outline" className="w-full gap-2 text-xs" size="sm" disabled={uploading} asChild>
            <span>
              <Upload className="w-3 h-3" />
              {uploading ? "Uploading..." : "Upload Song"}
            </span>
          </Button>
        </label>

        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          id="upload-clip"
          data-testid="upload-clip"
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

        <input
          type="file"
          accept=".cube"
          className="hidden"
          id="upload-lut"
          data-testid="upload-lut"
          onChange={(e) => handleFileChange(e, "lut")}
        />
        <label htmlFor="upload-lut">
          <Button variant="outline" className="w-full gap-2 text-xs" size="sm" disabled={uploading} asChild>
            <span>
              <Upload className="w-3 h-3" />
              {uploading ? "Uploading..." : "Upload LUT"}
            </span>
          </Button>
        </label>
      </div>
    </div>
  );
}
