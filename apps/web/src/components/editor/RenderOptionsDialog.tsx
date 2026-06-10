// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Film, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { renderOptionsSchema } from "@ai-video-editor/shared-types";
import type { z } from "zod";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { mapApiValidationErrors } from "@/lib/api/formErrors";
import { toast } from "sonner";

const EXPORT_PRESETS = [
  { value: "youtube_16_9", label: "YouTube 16:9" },
  { value: "reels_9_16", label: "Instagram Reels 9:16" },
  { value: "tiktok_9_16", label: "TikTok 9:16" },
  { value: "square_1_1", label: "Square 1:1" },
];

type RenderForm = z.infer<typeof renderOptionsSchema>;

interface RenderOptionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  onJobStart?: (jobId: string) => void;
}

export function RenderOptionsDialog({ open, onOpenChange, projectId, onJobStart }: RenderOptionsDialogProps) {
  const api = useApi();

  const form = useForm<RenderForm>({
    resolver: zodResolver(renderOptionsSchema),
    defaultValues: { exportPreset: "reels_9_16" },
    mode: "onChange",
  });

  const onSubmit = async (values: RenderForm) => {
    try {
      const res = await api.renders.start(projectId, { exportPreset: values.exportPreset });
      toast.success("Render started", { description: `Job ID: ${res.job.id}` });
      onJobStart?.(res.job.id);
      onOpenChange(false);
    } catch (err) {
      if (err instanceof APIError && mapApiValidationErrors(err, form.setError)) {
        return;
      }
      toast.error(err instanceof APIError ? err.userMessage : "Render failed");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="text-base">Render Video</DialogTitle>
          <DialogDescription className="text-zinc-400 text-xs">
            Choose an export preset and start rendering.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 pt-2">
            <FormField
              control={form.control}
              name="exportPreset"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Export Preset</FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger className="bg-zinc-900 border-zinc-800 h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent className="bg-zinc-950 border-zinc-800">
                      {EXPORT_PRESETS.map((p) => (
                        <SelectItem key={p.value} value={p.value} className="text-xs">
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={!form.formState.isValid || form.formState.isSubmitting} className="gap-2 bg-indigo-600 hover:bg-indigo-700">
                {form.formState.isSubmitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Film className="h-3.5 w-3.5" />}
                Start Render
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
