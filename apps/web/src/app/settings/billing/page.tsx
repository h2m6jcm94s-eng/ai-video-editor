// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Check, CreditCard, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
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
      <div style={{ display: "flex", justifyContent: "center", padding: "48px 0" }}>
        <Loader2 className="dash-spin" style={{ width: 20, height: 20, color: "var(--fg-muted)" }} />
      </div>
    );
  }

  const active = subscription?.status === "active";

  return (
    <div className="dash-panel">
      <div className="dash-panel-head">
        <h2>
          Billing<em>.</em>
        </h2>
        <p>Manage your plan and payment history.</p>
      </div>

      <div className="dash-card dash-sub">
        <div className="dash-sub-left">
          <span className="dash-sub-icon">
            <CreditCard />
          </span>
          <div>
            <p className="dash-sub-k">Current plan</p>
            <p className="dash-sub-plan">{subscription?.plan || "Free"}</p>
            <p className="dash-sub-desc">
              {active
                ? `Renews on ${new Date(subscription?.currentPeriodEnd || 0).toLocaleDateString()}`
                : "No active subscription"}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleManage}
          disabled={redirecting}
          className="dash-btn dash-btn--primary"
        >
          {redirecting ? <Loader2 className="dash-spin" /> : "Manage billing"}
        </button>
      </div>

      {subscription && subscription.features.length > 0 && (
        <div className="dash-card" style={{ padding: "20px 22px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
            {subscription.features.map((feature) => (
              <span key={feature} className="dash-feature">
                <Check />
                {feature}
              </span>
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="dash-sub-k" style={{ marginBottom: 12 }}>
          Invoice history
        </p>
        {invoices.length === 0 ? (
          <p className="dash-plan-desc">No invoices yet.</p>
        ) : (
          <div className="dash-list">
            {invoices.map((invoice) => (
              <div key={invoice.id} className="dash-list-row">
                <span className="k">
                  {new Date(invoice.createdAt).toLocaleDateString()}
                  <span className="status">{invoice.status}</span>
                </span>
                <span className="v">
                  ${(invoice.amount / 100).toFixed(2)} {invoice.currency.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
