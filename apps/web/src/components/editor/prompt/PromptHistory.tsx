// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { ScrollArea } from "@/components/ui/scroll-area";

interface PromptHistoryProps {
  items: { prompt: string; response: string }[];
}

export function PromptHistory({ items }: PromptHistoryProps) {
  return (
    <ScrollArea className="flex-1">
      <div className="space-y-3 p-3">
        {items.length === 0 && (
          <div className="text-xs text-zinc-500 text-center py-8">
            Try: &quot;cut on every beat&quot;, &quot;fade in&quot;, &quot;apply cinematic LUT&quot;
          </div>
        )}
        {items.map((item, i) => (
          <div key={i} className="space-y-1">
            <div className="bg-zinc-800 rounded-lg px-3 py-2 text-xs">{item.prompt}</div>
            <div className="text-[11px] text-zinc-400 px-1">{item.response}</div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
