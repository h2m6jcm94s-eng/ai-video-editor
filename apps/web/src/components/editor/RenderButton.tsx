// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState } from "react";
import { Film } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

export function RenderButton({
  projectId,
  onJobStart,
}: {
  projectId: string;
  onJobStart?: (jobId: string) => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleRender = async () => {
    setLoading(true);
    try {
      const res = await api.renders.start(projectId);
      toast.success("Render started", { description: `Job ID: ${res.job.id}` });
      onJobStart?.(res.job.id);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Render failed";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      size="sm"
      className="gap-2 bg-indigo-600 hover:bg-indigo-700"
      onClick={handleRender}
      disabled={loading}
    >
      <Film className="w-4 h-4" />
      {loading ? "Rendering..." : "Render"}
    </Button>
  );
}
