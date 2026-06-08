// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

export default function NewProjectPage() {
  const router = useRouter();
  const { isLoaded, isSignedIn } = useAuth();
  const [name, setName] = useState("");
  const [styleTier, setStyleTier] = useState<"full_style" | "style_transfer" | "no_style">("full_style");
  const [mode, setMode] = useState<"auto" | "assisted">("auto");
  const [loading, setLoading] = useState(false);

  if (!isLoaded) return null;
  if (!isSignedIn) {
    router.push("/sign-in");
    return null;
  }

  const handleCreate = async () => {
    if (!name.trim()) {
      toast.error("Project name is required");
      return;
    }
    setLoading(true);
    try {
      const res = await api.projects.create({ name, styleTier, mode });
      router.push(`/editor/${res.project.id}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to create project";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <div>
          <h1 className="text-xl font-semibold">Create New Project</h1>
          <p className="text-sm text-zinc-400 mt-1">Set up your video editing session</p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Project Name</Label>
            <Input
              id="name"
              placeholder="My Awesome Edit"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-zinc-950 border-zinc-800"
            />
          </div>

          <div className="space-y-2">
            <Label>Style Tier</Label>
            <Select value={styleTier} onValueChange={(v) => setStyleTier(v as typeof styleTier)}>
              <SelectTrigger className="bg-zinc-950 border-zinc-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full_style">Full Style (LUT + transitions + text)</SelectItem>
                <SelectItem value="style_transfer">Style Transfer Only</SelectItem>
                <SelectItem value="no_style">No Style (cut timing only)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Edit Mode</Label>
            <Select value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
              <SelectTrigger className="bg-zinc-950 border-zinc-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto (AI generates full edit)</SelectItem>
                <SelectItem value="assisted">Assisted (you approve the cutlist)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex gap-3">
          <Button variant="outline" className="flex-1" onClick={() => router.push("/dashboard")}>
            Cancel
          </Button>
          <Button className="flex-1" onClick={handleCreate} disabled={loading}>
            {loading ? "Creating..." : "Create Project"}
          </Button>
        </div>
      </div>
    </div>
  );
}
