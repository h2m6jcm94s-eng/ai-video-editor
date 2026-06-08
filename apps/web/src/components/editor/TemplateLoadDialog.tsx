// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect, useState } from "react";
import { FolderOpen, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { toast } from "sonner";
import type { CutList } from "@/types/api";

interface TemplateLoadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApply: (cutList: CutList) => void;
}

export function TemplateLoadDialog({ open, onOpenChange, onApply }: TemplateLoadDialogProps) {
  const api = useApi();
  const [templates, setTemplates] = useState<Array<{ id: string; name: string; description: string | null; usageCount: number }>>([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api.templates
      .list()
      .then((res) => setTemplates(res.templates))
      .catch((err) => toast.error(err instanceof APIError ? err.userMessage : "Failed to load templates"))
      .finally(() => setLoading(false));
  }, [open, api]);

  const handleApply = async (id: string, name: string) => {
    setApplying(id);
    try {
      const res = await api.templates.apply(id);
      if (res.cutList) {
        onApply(res.cutList as CutList);
        toast.success(`Loaded template: ${name}`);
        onOpenChange(false);
      }
    } catch (err) {
      toast.error(err instanceof APIError ? err.userMessage : "Failed to apply template");
    } finally {
      setApplying(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">Load Template</DialogTitle>
          <DialogDescription className="text-zinc-400 text-xs">
            Apply a saved template to the current project.
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="h-[280px] mt-2">
          {loading && (
            <div className="flex items-center justify-center py-12 text-zinc-500 text-xs">
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Loading...
            </div>
          )}
          {!loading && templates.length === 0 && (
            <div className="text-center py-12 text-zinc-500 text-xs">No templates yet. Save one first.</div>
          )}
          <div className="space-y-2 pr-2">
            {templates.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between p-3 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-900 transition"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{t.name}</p>
                  {t.description && <p className="text-[10px] text-zinc-500 truncate">{t.description}</p>}
                  <p className="text-[10px] text-zinc-600 mt-0.5">{t.usageCount} uses</p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={applying === t.id}
                  onClick={() => handleApply(t.id, t.name)}
                >
                  {applying === t.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Apply"}
                </Button>
              </div>
            ))}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
