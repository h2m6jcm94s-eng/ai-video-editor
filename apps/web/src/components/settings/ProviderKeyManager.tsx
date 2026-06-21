"use client";

import { PROVIDER_KEY_OPTIONS, providerKeySchema } from "@ai-video-editor/shared-types";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, KeyRound, Loader2, Plus, TestTube, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { type SubmitHandler, useForm } from "react-hook-form";
import { toast } from "sonner";
import type { z } from "zod";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import { mapApiValidationErrors } from "@/lib/api/formErrors";

const PROVIDER_LABELS: Record<(typeof PROVIDER_KEY_OPTIONS)[number], string> = {
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI (GPT-4o)",
  kimi: "Kimi",
  openrouter: "OpenRouter",
  groq: "Groq",
  gemini: "Google (Gemini)",
  qwen: "Alibaba (Qwen)",
};

const PROVIDERS = PROVIDER_KEY_OPTIONS.map((value) => ({ value, label: PROVIDER_LABELS[value] }));

type FormValues = z.infer<typeof providerKeySchema>;

type KeyInfo = {
  provider: string;
  masked: string;
  createdAt: string;
};

export function ProviderKeyManager({ initialKeys }: { initialKeys: KeyInfo[] }) {
  const api = useApi();
  const [keys, setKeys] = useState<KeyInfo[]>(initialKeys);
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [deleting, setDeleting] = useState<Record<string, boolean>>({});
  const [showForm, setShowForm] = useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(providerKeySchema),
    defaultValues: { provider: PROVIDERS[0].value, key: "" },
    mode: "onChange",
  });

  const onSubmit: SubmitHandler<FormValues> = useCallback(
    async (values) => {
      try {
        await api.settings.providerKeys.save(values);
        toast.success(`${PROVIDERS.find((p) => p.value === values.provider)?.label} key saved`);
        // Refresh list
        const res = await api.settings.providerKeys.list();
        setKeys(res.keys);
        setShowForm(false);
        form.reset();
      } catch (err) {
        if (err instanceof APIError && mapApiValidationErrors(err, form.setError)) {
          return;
        }
        if (err instanceof APIError) {
          toast.error(err.userMessage);
        } else if (err instanceof Error) {
          toast.error(err.message);
        } else {
          toast.error("Failed to save key");
        }
      }
    },
    [api, form],
  );

  const handleDelete = useCallback(
    async (provider: string) => {
      setDeleting((prev) => ({ ...prev, [provider]: true }));
      try {
        await api.settings.providerKeys.remove(provider);
        toast.success("Key removed");
        setKeys((prev) => prev.filter((k) => k.provider !== provider));
      } catch (err) {
        if (err instanceof APIError) {
          toast.error(err.userMessage);
        } else {
          toast.error("Failed to remove key");
        }
      } finally {
        setDeleting((prev) => ({ ...prev, [provider]: false }));
      }
    },
    [api],
  );

  const handleTest = useCallback(
    async (provider: string) => {
      setTesting((prev) => ({ ...prev, [provider]: true }));
      try {
        await api.settings.providerKeys.test(provider);
        toast.success("Key is valid", { icon: <CheckCircle2 className="h-4 w-4 text-green-500" /> });
      } catch (err) {
        if (err instanceof APIError) {
          toast.error(err.userMessage || "Key test failed");
        } else {
          toast.error("Key test failed");
        }
      } finally {
        setTesting((prev) => ({ ...prev, [provider]: false }));
      }
    },
    [api],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">API Keys</h2>
          <p className="text-sm text-zinc-400 mt-1">
            Connect your own provider keys for AI editing. Keys are encrypted at rest.
          </p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)} size="sm">
          <Plus className="h-4 w-4 mr-1.5" />
          {showForm ? "Cancel" : "Add Key"}
        </Button>
      </div>

      {showForm && (
        <Card className="border-zinc-800 bg-zinc-950/50">
          <CardHeader>
            <CardTitle className="text-base">Add Provider Key</CardTitle>
            <CardDescription className="text-zinc-400">
              Your key is encrypted before storage. We never share it.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="provider"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Provider</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger className="bg-zinc-950 border-zinc-800">
                            <SelectValue placeholder="Select a provider" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent className="bg-zinc-950 border-zinc-800">
                          {PROVIDERS.map((p) => (
                            <SelectItem key={p.value} value={p.value}>
                              {p.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="key"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>API Key</FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          placeholder="sk-ant-api03-..."
                          className="bg-zinc-950 border-zinc-800 font-mono text-sm"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex justify-end gap-3 pt-2">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setShowForm(false);
                      form.reset();
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={!form.formState.isValid || form.formState.isSubmitting}>
                    {form.formState.isSubmitting && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
                    Save Key
                  </Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
      )}

      {keys.length === 0 && !showForm && (
        <Card className="border-zinc-800 bg-zinc-950/50 border-dashed">
          <CardContent className="py-12 flex flex-col items-center text-center">
            <KeyRound className="h-10 w-10 text-zinc-600 mb-4" />
            <p className="text-zinc-300 font-medium">No API keys connected</p>
            <p className="text-sm text-zinc-500 mt-1 max-w-sm">
              Add your Anthropic or OpenAI key to unlock AI-powered editing features.
            </p>
            <Button onClick={() => setShowForm(true)} variant="outline" size="sm" className="mt-4">
              <Plus className="h-4 w-4 mr-1.5" />
              Add Key
            </Button>
          </CardContent>
        </Card>
      )}

      {keys.length > 0 && (
        <div className="space-y-3">
          {keys.map((key) => {
            const provider = PROVIDERS.find((p) => p.value === key.provider);
            return (
              <Card key={key.provider} className="border-zinc-800 bg-zinc-950/50">
                <CardContent className="py-4 px-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <KeyRound className="h-5 w-5 text-zinc-500" />
                      <div>
                        <p className="font-medium text-sm">{provider?.label || key.provider}</p>
                        <p className="text-xs text-zinc-500 font-mono mt-0.5">{key.masked}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleTest(key.provider)}
                        disabled={testing[key.provider]}
                      >
                        {testing[key.provider] ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <>
                            <TestTube className="h-4 w-4 mr-1.5" />
                            Test
                          </>
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-400 hover:text-red-300 hover:bg-red-950/30"
                        onClick={() => handleDelete(key.provider)}
                        disabled={deleting[key.provider]}
                      >
                        {deleting[key.provider] ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
