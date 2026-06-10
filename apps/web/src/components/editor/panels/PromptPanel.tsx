// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { promptEditSchema } from "@ai-video-editor/shared-types";
import { zodResolver } from "@hookform/resolvers/zod";
import { Send, Wand2, X } from "lucide-react";
import { memo, useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import type { z } from "zod";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormField, FormItem, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { mapApiValidationErrors } from "@/lib/api/formErrors";
import { diffCutLists, summarizeOps } from "@/lib/cutlistDiff";
import type { CutList } from "@/types/api";
import { PromptHistory, type PromptHistoryEntry } from "./PromptHistory";

interface PromptPanelProps {
  projectId: string;
  cutList: CutList | null;
  onPromptApply: (cutList: CutList) => void;
  onUndo: () => void;
  onClose: () => void;
}

type PromptForm = z.infer<typeof promptEditSchema>;

function PromptPanelInner({ projectId, cutList, onPromptApply, onUndo, onClose }: PromptPanelProps) {
  const [entries, setEntries] = useState<PromptHistoryEntry[]>([]);
  const api = useApi();

  const form = useForm<PromptForm>({
    resolver: zodResolver(promptEditSchema),
    defaultValues: { prompt: "" },
    mode: "onChange",
  });

  const onSubmit = async (values: PromptForm) => {
    if (!cutList) {
      toast.error("No cut list to edit");
      return;
    }

    try {
      const result = await api.projects.prompt(projectId, values.prompt.trim());
      if (result.project.cutList) {
        const newCutList = result.project.cutList as CutList;
        const ops = diffCutLists(cutList, newCutList);
        onPromptApply(newCutList);
        const entry: PromptHistoryEntry = {
          id: crypto.randomUUID(),
          prompt: values.prompt,
          summary: summarizeOps(ops),
          ops,
          timestamp: new Date(),
        };
        setEntries((prev) => [...prev, entry]);
        toast.success(`Applied ${entry.summary}`, {
          action: { label: "Undo", onClick: onUndo },
          duration: 8000,
        });
      }
      form.reset({ prompt: "" });
    } catch (err) {
      if (err instanceof APIError && mapApiValidationErrors(err, form.setError)) {
        return;
      }
      const message =
        err instanceof APIError ? err.userMessage : err instanceof Error ? err.message : "AI edit failed";
      const entry: PromptHistoryEntry = {
        id: crypto.randomUUID(),
        prompt: values.prompt,
        summary: message,
        ops: [],
        timestamp: new Date(),
        error: true,
      };
      setEntries((prev) => [...prev, entry]);
      toast.error(message);
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col h-[400px]">
      <div className="h-10 border-b border-zinc-800 flex items-center justify-between px-3">
        <div className="flex items-center gap-2 text-xs font-medium">
          <Wand2 className="w-3 h-3" />
          AI Prompt
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onClose} className="p-1 hover:bg-zinc-800 rounded" aria-label="Close">
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>

      <PromptHistory entries={entries} onUndo={onUndo} />

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="p-3 border-t border-zinc-800 flex gap-2">
          <FormField
            control={form.control}
            name="prompt"
            render={({ field }) => (
              <FormItem className="flex-1">
                <FormControl>
                  <Input
                    placeholder="Ask AI to edit..."
                    className="bg-zinc-950 border-zinc-800 h-8 text-xs"
                    disabled={form.formState.isSubmitting}
                    {...field}
                  />
                </FormControl>
                <FormMessage className="text-[10px]" />
              </FormItem>
            )}
          />
          <Button
            size="sm"
            className="h-8 px-3"
            type="submit"
            disabled={!form.formState.isValid || form.formState.isSubmitting}
          >
            <Send className="w-3 h-3" />
          </Button>
        </form>
      </Form>
    </div>
  );
}

export const PromptPanel = memo(PromptPanelInner);
