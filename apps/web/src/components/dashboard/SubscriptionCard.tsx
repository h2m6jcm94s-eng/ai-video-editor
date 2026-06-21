// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Check, CreditCard, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/client";
import type { Subscription } from "@/types/api";

export function SubscriptionCard() {
  const api = useApi();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.billing
      .plan()
      .then((res) => setSubscription(res.subscription))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [api]);

  if (loading) {
    return (
      <div className="glass-card p-5 flex items-center justify-center h-32">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="glass-card p-5 relative overflow-hidden">
      <div className="absolute -top-6 -right-6 w-24 h-24 rounded-full bg-indigo-500/20 blur-2xl" />
      <div className="relative flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            {subscription ? (
              <CreditCard className="w-6 h-6 text-white" />
            ) : (
              <Sparkles className="w-6 h-6 text-white" />
            )}
          </div>
          <div>
            <p className="text-sm text-zinc-400">Subscription</p>
            <p className="text-xl font-bold text-white capitalize">{subscription?.plan || "Free"}</p>
            <p className="text-xs text-zinc-500">
              {subscription?.status === "active"
                ? `Renews ${new Date(subscription.currentPeriodEnd).toLocaleDateString()}`
                : "Upgrade to unlock more features"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {subscription?.features.slice(0, 2).map((feature) => (
            <span key={feature} className="hidden sm:flex items-center gap-1 text-xs text-zinc-300">
              <Check className="w-3 h-3 text-emerald-400" />
              {feature}
            </span>
          ))}
          <Button asChild size="sm" className="shrink-0">
            <Link href="/pricing">{subscription?.status === "active" ? "Manage" : "Upgrade"}</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
