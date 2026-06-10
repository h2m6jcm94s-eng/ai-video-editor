// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Film, Loader2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useRenderStatus } from "@/hooks/useRenderStatus";
import { RenderOptionsDialog } from "./RenderOptionsDialog";

export function RenderButton({
  projectId,
  onJobStart,
}: {
  projectId: string;
  onJobStart?: (jobId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const { activeRender, isRendering } = useRenderStatus(projectId);

  return (
    <>
      <Button
        size="sm"
        className="gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-70"
        onClick={() => setOpen(true)}
        disabled={isRendering}
        aria-busy={isRendering}
      >
        {isRendering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Film className="w-4 h-4" />}
        {isRendering ? `Rendering ${Math.round(activeRender?.progress ?? 0)}%` : "Render"}
      </Button>
      <RenderOptionsDialog open={open} onOpenChange={setOpen} projectId={projectId} onJobStart={onJobStart} />
    </>
  );
}
