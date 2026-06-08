// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState } from "react";
import { Send, X, Wand2, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Form, FormControl, FormField, FormItem, FormMessage } from "@/components/ui/form";
import type { CutList } from "@/types/api";
import { toast } from "sonner";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { promptEditSchema } from "@ai-video-editor/shared-types";
import { z } from "zod";

interface PromptPanelProps {
  projectId: string;
  cutList: CutList | null;
  onUpdateCutlist: (cutList: CutList) => void;
  onUndo?: () => void;
  onClose: () => void;
}

type PromptForm = z.infer<typeof promptEditSchema>;

export function PromptPanel({ projectId, cutList, onUpdateCutlist, onUndo, onClose }: PromptPanelProps) {
  const [history, setHistory] = useState<{ prompt: string; response: string; error?: boolean }[]>([]);
  const [loading, setLoading] = useState(false);
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
    setLoading(true);

    try {
      const result = await api.projects.prompt(projectId, values.prompt.trim());
      if (result.project.cutList) {
        onUpdateCutlist(result.project.cutList as CutList);
      }
      setHistory((h) => [
        ...h,
        { prompt: values.prompt, response: result.explanation || "Changes applied successfully." },
      ]);
      toast.success("AI edit applied");
      form.reset({ prompt: "" });
    } catch (err) {
      const message = err instanceof APIError ? err.userMessage : err instanceof Error ? err.message : "AI edit failed";
      setHistory((h) => [...h, { prompt: values.prompt, response: message, error: true }]);
      toast.error(message);
    } finally {
      setLoading(false);
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
          {onUndo && (
            <button onClick={onUndo} className="p-1 hover:bg-zinc-800 rounded" aria-label="Undo last edit" title="Undo">
              <Undo2 className="w-3 h-3" />
            </button>
          )}
          <button onClick={onClose} className="p-1 hover:bg-zinc-800 rounded" aria-label="Close">
            <X className="w-3 h-3" />
          </button>
        </div>
      </div>

      <ScrollArea className="flex-1 p-3">
        {history.length === 0 && (
          <div className="text-xs text-zinc-500 text-center py-8">
            Try: &quot;cut on every beat&quot;, &quot;fade in&quot;, &quot;apply cinematic LUT&quot;
          </div>
        )}
        <div className="space-y-3">
          {history.map((h, i) => (
            <div key={i} className="space-y-1">
              <div className="bg-zinc-800 rounded-lg px-3 py-2 text-xs">{h.prompt}</div>
              <div className={`text-[11px] px-1 ${h.error ? "text-red-400" : "text-zinc-400"}`}>{h.response}</div>
            </div>
          ))}
        </div>
      </ScrollArea>

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
                    disabled={loading}
                    {...field}
                  />
                </FormControl>
                <FormMessage className="text-[10px]" />
              </FormItem>
            )}
          />
          <Button size="sm" className="h-8 px-3" type="submit" disabled={!form.formState.isValid || loading}>
            <Send className="w-3 h-3" />
          </Button>
        </form>
      </Form>
    </div>
  );
}
