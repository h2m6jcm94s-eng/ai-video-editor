// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
  FormMessage,
} from "@/components/ui/form";
import { projectNameSchema } from "@ai-video-editor/shared-types";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { toast } from "sonner";
import type { CutList } from "@/types/api";

const templateFormSchema = z.object({
  name: projectNameSchema,
  description: z.string().max(2000).optional(),
  tags: z.array(z.string()).default([]),
  isPublic: z.boolean().default(false),
});

type TemplateForm = z.infer<typeof templateFormSchema>;

interface TemplateSaveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cutList: CutList;
}

export function TemplateSaveDialog({ open, onOpenChange, cutList }: TemplateSaveDialogProps) {
  const api = useApi();
  const form = useForm<TemplateForm>({
    resolver: zodResolver(templateFormSchema),
    defaultValues: { name: "", description: "", tags: [], isPublic: false },
    mode: "onChange",
  });

  const onSubmit = form.handleSubmit(async (values: TemplateForm) => {
    try {
      await api.templates.create({ ...values, cutList: cutList as unknown as Record<string, unknown> });
      toast.success("Template saved");
      form.reset();
      onOpenChange(false);
    } catch (err) {
      if (err instanceof APIError) {
        toast.error(err.userMessage);
      } else {
        toast.error("Failed to save template");
      }
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-zinc-950 border-zinc-800 text-zinc-100 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base">Save as Template</DialogTitle>
          <DialogDescription className="text-zinc-400 text-xs">
            Save the current cut list as a reusable template.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={onSubmit} className="space-y-4 pt-2">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Name</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="e.g. Fast cuts on downbeats"
                      className="bg-zinc-900 border-zinc-800 h-8 text-xs"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-[10px]" />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="What this template is best for..."
                      className="bg-zinc-900 border-zinc-800 text-xs min-h-[80px]"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-[10px]" />
                </FormItem>
              )}
            />
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={!form.formState.isValid || form.formState.isSubmitting}>
                {form.formState.isSubmitting && <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
                Save Template
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
