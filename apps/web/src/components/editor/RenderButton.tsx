// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState } from "react";
import { Film } from "lucide-react";
import { Button } from "@/components/ui/button";
import { RenderOptionsDialog } from "./RenderOptionsDialog";

export function RenderButton({
  projectId,
  onJobStart,
}: {
  projectId: string;
  onJobStart?: (jobId: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        size="sm"
        className="gap-2 bg-indigo-600 hover:bg-indigo-700"
        onClick={() => setOpen(true)}
      >
        <Film className="w-4 h-4" />
        Render
      </Button>
      <RenderOptionsDialog
        open={open}
        onOpenChange={setOpen}
        projectId={projectId}
        onJobStart={onJobStart}
      />
    </>
  );
}
