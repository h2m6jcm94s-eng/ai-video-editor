"use client";

import { PROVIDER_KEY_OPTIONS, providerKeySchema } from "@ai-video-editor/shared-types";
import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, KeyRound, Loader2, Plus, TestTube, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { type SubmitHandler, useForm } from "react-hook-form";
import { toast } from "sonner";
import type { z } from "zod";
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

const FIELD_CLASS =
  "bg-[#0a0908] border-[#2a2520] text-[#f5f1e8] focus-visible:border-[#ff4d1f]/60 focus-visible:ring-[#ff4d1f]/20";

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
    <div className="dash-panel">
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div className="dash-panel-head">
          <h2>
            API <em>keys</em>
          </h2>
          <p>Connect your own provider keys for AI editing. Keys are encrypted at rest.</p>
        </div>
        <button type="button" onClick={() => setShowForm((s) => !s)} className="dash-btn dash-btn--sm">
          <Plus />
          {showForm ? "Cancel" : "Add Key"}
        </button>
      </div>

      {showForm && (
        <div className="dash-card" style={{ padding: "22px 24px" }}>
          <p className="dash-sub-k" style={{ marginBottom: 4 }}>
            Add provider key
          </p>
          <p className="dash-plan-desc" style={{ marginBottom: 18 }}>
            Your key is encrypted before storage. We never share it.
          </p>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="dash-sub-k">Provider</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger className={FIELD_CLASS}>
                          <SelectValue placeholder="Select a provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent className="bg-[#15110d] border-[#2a2520] text-[#f5f1e8]">
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
                    <FormLabel className="dash-sub-k">API Key</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="sk-ant-api03-..."
                        className={`${FIELD_CLASS} font-mono text-sm`}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="dash-btn dash-btn--sm"
                  onClick={() => {
                    setShowForm(false);
                    form.reset();
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="dash-btn dash-btn--primary dash-btn--sm"
                  disabled={!form.formState.isValid || form.formState.isSubmitting}
                >
                  {form.formState.isSubmitting && <Loader2 className="dash-spin" />}
                  Save Key
                </button>
              </div>
            </form>
          </Form>
        </div>
      )}

      {keys.length === 0 && !showForm && (
        <div className="dash-empty">
          <span className="dash-empty-icon">
            <KeyRound />
          </span>
          <h3>No API keys connected</h3>
          <p>Add your Anthropic or OpenAI key to unlock AI-powered editing features.</p>
          <button type="button" onClick={() => setShowForm(true)} className="dash-btn">
            <Plus />
            Add Key
          </button>
        </div>
      )}

      {keys.length > 0 && (
        <div className="dash-list">
          {keys.map((key) => {
            const provider = PROVIDERS.find((p) => p.value === key.provider);
            return (
              <div key={key.provider} className="dash-list-row">
                <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
                  <KeyRound style={{ width: 18, height: 18, color: "var(--fg-muted)", flexShrink: 0 }} />
                  <div style={{ minWidth: 0 }}>
                    <p style={{ color: "var(--fg)", fontSize: 15 }}>{provider?.label || key.provider}</p>
                    <p
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: "0.72rem",
                        color: "var(--fg-muted)",
                        marginTop: 2,
                      }}
                    >
                      {key.masked}
                    </p>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  <button
                    type="button"
                    className="dash-btn dash-btn--sm"
                    onClick={() => handleTest(key.provider)}
                    disabled={testing[key.provider]}
                  >
                    {testing[key.provider] ? (
                      <Loader2 className="dash-spin" />
                    ) : (
                      <>
                        <TestTube />
                        Test
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    className="dash-btn dash-btn--sm"
                    style={{ color: "#ff7a5c" }}
                    onClick={() => handleDelete(key.provider)}
                    disabled={deleting[key.provider]}
                    aria-label="Remove key"
                  >
                    {deleting[key.provider] ? <Loader2 className="dash-spin" /> : <Trash2 />}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
