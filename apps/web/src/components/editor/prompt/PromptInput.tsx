// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface PromptInputProps {
  onSubmit: (prompt: string) => void;
  loading?: boolean;
}

export function PromptInput({ onSubmit, loading }: PromptInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = () => {
    if (!value.trim()) return;
    onSubmit(value);
    setValue("");
  };

  return (
    <div className="flex gap-2">
      <Input
        placeholder="Ask AI to edit..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        className="bg-zinc-950 border-zinc-800 h-8 text-xs"
        disabled={loading}
      />
      <Button size="sm" className="h-8 px-3" onClick={handleSubmit} disabled={loading}>
        <Send className="w-3 h-3" />
      </Button>
    </div>
  );
}
