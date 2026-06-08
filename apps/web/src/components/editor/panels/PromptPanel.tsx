// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState } from "react";
import { Send, X, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import type { CutList } from "@/types/api";
import { toast } from "sonner";

const PROMPT_PATTERNS = [
  { pattern: /cut on (every )?beat/i, action: "align_cuts_to_beats", label: "Align cuts to beats" },
  { pattern: /fade (in|out)/i, action: "add_fade", label: "Add fade" },
  { pattern: /remove clip (\d+)/i, action: "remove_slot", label: "Remove clip" },
  { pattern: /add text "(.+)" at (\d+:\d+)/i, action: "add_text_overlay", label: "Add text overlay" },
  { pattern: /apply .* lut/i, action: "apply_lut", label: "Apply LUT" },
];

interface PromptPanelProps {
  projectId: string;
  cutList: CutList | null;
  onUpdateCutlist: (cutList: CutList) => void;
  onClose: () => void;
}

export function PromptPanel({ projectId, cutList, onUpdateCutlist, onClose }: PromptPanelProps) {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<{ prompt: string; response: string }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!prompt.trim() || !cutList) return;
    setLoading(true);

    // Client-side pattern matching for optimistic updates
    const matched = PROMPT_PATTERNS.find((p) => p.pattern.test(prompt));
    if (matched) {
      // Optimistic update based on action
      const updated = { ...cutList };
      if (matched.action === "add_fade") {
        updated.slots = updated.slots.map((s, i) =>
          i === 0 ? { ...s, transition_in: "fade" } : s
        );
      }
      onUpdateCutlist(updated);
      setHistory((h) => [...h, { prompt, response: `Applied: ${matched.label}` }]);
      setPrompt("");
      setLoading(false);
      return;
    }

    // Send to backend
    try {
      const res = await fetch(`/api/projects/${projectId}/prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, context: { cutList } }),
      });
      const data = await res.json();
      if (data.diff) {
        // Apply diff (simplified: replace cutList for now)
        onUpdateCutlist(data.diff);
      }
      setHistory((h) => [...h, { prompt, response: data.explanation || "Done" }]);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "AI request failed";
      toast.error(message);
    } finally {
      setLoading(false);
      setPrompt("");
    }
  };

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl flex flex-col h-[400px]">
      <div className="h-10 border-b border-zinc-800 flex items-center justify-between px-3">
        <div className="flex items-center gap-2 text-xs font-medium">
          <Wand2 className="w-3 h-3" />
          AI Prompt
        </div>
        <button onClick={onClose} className="p-1 hover:bg-zinc-800 rounded" aria-label="Close">
          <X className="w-3 h-3" />
        </button>
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
              <div className="text-[11px] text-zinc-400 px-1">{h.response}</div>
            </div>
          ))}
        </div>
      </ScrollArea>

      <div className="p-3 border-t border-zinc-800 flex gap-2">
        <Input
          placeholder="Ask AI to edit..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          className="bg-zinc-950 border-zinc-800 h-8 text-xs"
        />
        <Button size="sm" className="h-8 px-3" onClick={handleSubmit} disabled={loading}>
          <Send className="w-3 h-3" />
        </Button>
      </div>
    </div>
  );
}
