// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { createProjectSchema, STYLE_TIER, EDIT_MODE } from "@ai-video-editor/shared-types";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import { mapApiValidationErrors } from "@/lib/api/formErrors";
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

export function CreateProjectDialog() {
  const router = useRouter();
  const api = useApi();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    setError,
    formState: { errors, isSubmitting, isValid },
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

  const onSubmit = async (data: FormData) => {
    try {
      const res = await api.projects.create(data);
      reset();
      router.push(`/editor/${res.project.id}`);
    } catch (err: unknown) {
      if (err instanceof APIError && mapApiValidationErrors(err, setError)) {
        return;
      }
      const message = err instanceof APIError ? err.userMessage : "Failed to create project";
      toast.error(message);
    }
  };

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-2">
          <Plus className="w-4 h-4" />
          New Project
        </Button>
      </DialogTrigger>
      <DialogContent className="bg-zinc-900 border-zinc-800 text-zinc-100 sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create New Project</DialogTitle>
          <DialogDescription className="text-zinc-400">
            Start a new AI-powered video editing session.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">Project Name</Label>
            <Input
              id="project-name"
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

          <div className="flex justify-end gap-3">
            <DialogTrigger asChild>
              <Button type="button" variant="outline" disabled={isSubmitting}>
                Cancel
              </Button>
            </DialogTrigger>
            <Button type="submit" disabled={!isValid || isSubmitting}>
              {isSubmitting ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
