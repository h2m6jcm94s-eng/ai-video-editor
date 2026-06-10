// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import type { Operation } from "fast-json-patch";
import { Clock, Undo2, Wand2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface PromptHistoryEntry {
  id: string;
  prompt: string;
  summary: string;
  ops: Operation[];
  timestamp: Date;
  error?: boolean;
}

interface PromptHistoryProps {
  entries: PromptHistoryEntry[];
  onUndo?: () => void;
}

export function PromptHistory({ entries, onUndo }: PromptHistoryProps) {
  if (entries.length === 0) {
    return (
      <div className="text-xs text-zinc-500 text-center py-8">
        Try: &quot;cut on every beat&quot;, &quot;fade in&quot;, &quot;apply cinematic LUT&quot;
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1 p-3">
      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.id} className="space-y-1">
            <div className="flex items-center gap-2">
              <div className="bg-zinc-800 rounded-lg px-3 py-2 text-xs flex-1">{entry.prompt}</div>
              {entry.error ? null : (
                <span className="text-[10px] text-zinc-500 whitespace-nowrap">
                  <Clock className="w-3 h-3 inline mr-0.5" />
                  {entry.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <div className={`text-[11px] px-1 flex-1 ${entry.error ? "text-red-400" : "text-zinc-400"}`}>
                {entry.error ? (
                  entry.summary
                ) : (
                  <span className="flex items-center gap-1">
                    <Wand2 className="w-3 h-3" />
                    Applied {entry.summary}
                  </span>
                )}
              </div>
              {!entry.error && onUndo && (
                <button
                  onClick={onUndo}
                  className="p-1 hover:bg-zinc-800 rounded text-zinc-500 hover:text-zinc-300 transition"
                  aria-label="Undo"
                  title="Undo"
                >
                  <Undo2 className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
