// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Loader2, Scan } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useSegmentJob } from "@/hooks/useSegmentJob";
import type { Asset } from "@/types/api";

interface SegmentPanelProps {
  projectId: string;
  assets: Asset[];
}

export function SegmentPanel({ projectId, assets }: SegmentPanelProps) {
  const videoAssets = assets.filter((a) => a.type === "clip" || a.type === "reference_video");
  const [assetId, setAssetId] = useState<string>(videoAssets[0]?.id ?? "");
  const [prompt, setPrompt] = useState("person");
  const [mode, setMode] = useState<"image" | "video">("image");
  const { workflowId, result, loading, error, start, reset } = useSegmentJob(projectId);

  const masks = (result?.masks as string[] | undefined) ?? [];
  const skipped = result?.skipped === true;
  const skippedReason = (result?.skipped_reason as string) || "";

  return (
    <div className="w-[260px] border-l border-zinc-800 flex flex-col bg-zinc-950 shrink-0">
      <div className="h-10 border-b border-zinc-800 flex items-center px-3">
        <Scan className="w-4 h-4 mr-2 text-zinc-400" />
        <span className="text-xs font-medium text-zinc-300">Segment</span>
      </div>
      <ScrollArea className="flex-1 p-3 space-y-3">
        <div className="space-y-2">
          <label className="text-[10px] uppercase text-zinc-500 font-medium">Asset</label>
          <Select value={assetId} onValueChange={setAssetId}>
            <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-zinc-950 border-zinc-800">
              {videoAssets.map((a) => (
                <SelectItem key={a.id} value={a.id} className="text-xs">
                  {a.filename}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <label className="text-[10px] uppercase text-zinc-500 font-medium">Prompt</label>
          <Input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. person"
            className="bg-zinc-900 border-zinc-800 h-8 text-xs"
          />
        </div>

        <div className="space-y-2">
          <label className="text-[10px] uppercase text-zinc-500 font-medium">Mode</label>
          <Select value={mode} onValueChange={(v) => setMode(v as "image" | "video")}>
            <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-zinc-950 border-zinc-800">
              <SelectItem value="image" className="text-xs">
                Single frame
              </SelectItem>
              <SelectItem value="video" className="text-xs">
                Track in video
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex gap-2">
          <Button
            size="sm"
            className="flex-1 gap-2 bg-indigo-600 hover:bg-indigo-700 text-xs"
            disabled={!assetId || loading || !prompt.trim()}
            onClick={() => start(assetId, prompt.trim(), mode)}
          >
            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Scan className="w-3 h-3" />}
            {loading ? "Running..." : "Segment"}
          </Button>
          {result && (
            <Button size="sm" variant="outline" className="text-xs" onClick={reset}>
              Reset
            </Button>
          )}
        </div>

        {error && <p className="text-xs text-red-400">{error}</p>}
        {skipped && <p className="text-xs text-amber-400">Skipped: {skippedReason}</p>}

        {masks.length > 0 && (
          <div className="space-y-2 pt-2">
            <label className="text-[10px] uppercase text-zinc-500 font-medium">Masks</label>
            <div className="space-y-2">
              {masks.map((mask, i) =>
                mask ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    key={i}
                    src={`data:image/png;base64,${mask}`}
                    alt={`Mask ${i + 1}`}
                    className="w-full rounded border border-zinc-800"
                  />
                ) : null,
              )}
            </div>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
