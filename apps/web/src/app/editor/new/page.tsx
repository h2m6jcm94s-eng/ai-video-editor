// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { createProjectSchema, STYLE_TIER, EDIT_MODE } from "@ai-video-editor/shared-types";
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
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { toast } from "sonner";

type FormData = z.infer<typeof createProjectSchema>;

const STYLE_LABELS: Record<(typeof STYLE_TIER)[number], string> = {
  cuts_only: "Cuts Only (beat sync, no effects)",
  color_grade: "+ Color Grade (LUT matching)",
  with_text: "+ Text Overlays (kinetic typography)",
  with_effects: "+ Effects (transitions, zooms, SFX)",
  full_remix: "Full Remix (everything + manual layers)",
};

const MODE_LABELS: Record<(typeof EDIT_MODE)[number], string> = {
  auto: "Auto (AI generates full edit)",
  assisted: "Assisted (you approve the cutlist)",
};

export default function NewProjectPage() {
  const router = useRouter();
  const { isLoaded, isSignedIn } = useAuth();
  const api = useApi();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(createProjectSchema),
    defaultValues: {
      name: "",
      styleTier: "with_effects",
      mode: "auto",
    },
    mode: "onChange",
  });

  const styleTier = watch("styleTier");
  const mode = watch("mode");

  if (!isLoaded) return null;
  if (!isSignedIn) {
    router.push("/sign-in");
    return null;
  }

  const onSubmit = async (data: FormData) => {
    try {
      const res = await api.projects.create(data);
      router.push(`/editor/${res.project.id}`);
    } catch (err: unknown) {
      const message = err instanceof APIError ? err.userMessage : "Failed to create project";
      toast.error(message);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6 bg-zinc-900 border border-zinc-800 rounded-xl p-6">
        <div>
          <h1 className="text-xl font-semibold">Create New Project</h1>
          <p className="text-sm text-zinc-400 mt-1">Set up your video editing session</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Project Name</Label>
            <Input
              id="name"
              placeholder="My Awesome Edit"
              className="bg-zinc-950 border-zinc-800"
              {...register("name")}
            />
            {errors.name && (
              <p className="text-xs text-red-400">{errors.name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Style Tier</Label>
            <Select
              value={styleTier}
              onValueChange={(v) => setValue("styleTier", v as FormData["styleTier"])}
            >
              <SelectTrigger className="bg-zinc-950 border-zinc-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STYLE_TIER.map((tier) => (
                  <SelectItem key={tier} value={tier}>
                    {STYLE_LABELS[tier]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.styleTier && (
              <p className="text-xs text-red-400">{errors.styleTier.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Edit Mode</Label>
            <Select
              value={mode}
              onValueChange={(v) => setValue("mode", v as FormData["mode"])}
            >
              <SelectTrigger className="bg-zinc-950 border-zinc-800">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EDIT_MODE.map((m) => (
                  <SelectItem key={m} value={m}>
                    {MODE_LABELS[m]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.mode && (
              <p className="text-xs text-red-400">{errors.mode.message}</p>
            )}
          </div>

          <div className="flex gap-3">
            <Button type="button" variant="outline" className="flex-1" onClick={() => router.push("/dashboard")}>
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={isSubmitting}>
              {isSubmitting ? "Creating..." : "Create Project"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
