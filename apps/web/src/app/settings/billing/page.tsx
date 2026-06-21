// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Check, CreditCard, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/client";
import type { Invoice, Subscription } from "@/types/api";

export default function BillingPage() {
  const api = useApi();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    let mounted = true;
    Promise.all([api.billing.plan(), api.billing.invoices()])
      .then(([planRes, invoicesRes]) => {
        if (!mounted) return;
        setSubscription(planRes.subscription);
        setInvoices(invoicesRes.invoices);
      })
      .catch(() => {
        if (!mounted) return;
      })
      .finally(() => setLoading(false));
    return () => {
      mounted = false;
    };
  }, [api]);

  const handleManage = async () => {
    setRedirecting(true);
    try {
      const { url } = await api.billing.portal();
      window.location.href = url;
    } catch {
      setRedirecting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-xl font-semibold text-white">Billing</h2>
        <p className="text-sm text-zinc-500 mt-1">Manage your plan and payment history.</p>
      </div>

      <div className="glass-card p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <CreditCard className="w-6 h-6 text-white" />
            </div>
            <div>
              <p className="text-sm text-zinc-400">Current plan</p>
              <p className="text-2xl font-bold text-white capitalize">{subscription?.plan || "Free"}</p>
              <p className="text-xs text-zinc-500">
                {subscription?.status === "active"
                  ? `Renews on ${new Date(subscription?.currentPeriodEnd || Date.now()).toLocaleDateString()}`
                  : "No active subscription"}
              </p>
            </div>
          </div>
          <Button onClick={handleManage} disabled={redirecting} className="shrink-0">
            {redirecting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Manage billing"}
          </Button>
        </div>

        {subscription && (
          <div className="mt-6 pt-6 border-t border-zinc-800 grid grid-cols-1 sm:grid-cols-2 gap-3">
            {subscription.features.map((feature) => (
              <div key={feature} className="flex items-center gap-2 text-sm text-zinc-300">
                <Check className="w-4 h-4 text-emerald-400" />
                {feature}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="glass-card p-6">
        <h3 className="text-sm font-medium text-white mb-4">Invoice history</h3>
        {invoices.length === 0 ? (
          <p className="text-sm text-zinc-500">No invoices yet.</p>
        ) : (
          <div className="divide-y divide-zinc-800">
            {invoices.map((invoice) => (
              <div key={invoice.id} className="py-3 flex items-center justify-between text-sm">
                <div>
                  <p className="text-zinc-300">{new Date(invoice.createdAt).toLocaleDateString()}</p>
                  <p className="text-xs text-zinc-500 uppercase">{invoice.status}</p>
                </div>
                <p className="font-medium text-white">
                  ${(invoice.amount / 100).toFixed(2)} {invoice.currency.toUpperCase()}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
