// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Film, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useRenderStatus } from "@/hooks/useRenderStatus";
import type { Asset } from "@/types/api";
import { RenderOptionsDialog } from "./RenderOptionsDialog";

interface RenderButtonProps {
  projectId: string;
  assets: Asset[];
  onJobStart?: (jobId: string) => void;
}

export function RenderButton({ projectId, assets, onJobStart }: RenderButtonProps) {
  const [open, setOpen] = useState(false);
  const { activeRender, isRendering } = useRenderStatus(projectId);

  const { canRender, reason } = useMemo(() => {
    const hasSong = assets.some((a) => a.type === "song");
    const hasReference = assets.some((a) => a.type === "reference_video");
    const hasClip = assets.some((a) => a.type === "clip");
    if (!hasSong) return { canRender: false, reason: "Upload a song to render" };
    if (!hasReference) return { canRender: false, reason: "Upload a reference video to render" };
    if (!hasClip) return { canRender: false, reason: "Upload at least one clip to render" };
    return { canRender: true, reason: undefined };
  }, [assets]);

  const button = (
    <Button
      size="sm"
      className="gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-70"
      onClick={() => setOpen(true)}
      disabled={isRendering || !canRender}
      aria-busy={isRendering}
    >
      {isRendering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Film className="w-4 h-4" />}
      {isRendering ? `Rendering ${Math.round(activeRender?.progress ?? 0)}%` : "Render"}
    </Button>
  );

  return (
    <>
      <TooltipProvider delayDuration={150}>
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          {!canRender && (
            <TooltipContent side="bottom" className="text-xs max-w-xs">
              {reason}
            </TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>
      <RenderOptionsDialog open={open} onOpenChange={setOpen} projectId={projectId} onJobStart={onJobStart} />
    </>
  );
}
