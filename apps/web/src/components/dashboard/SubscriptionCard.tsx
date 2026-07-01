// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Check, CreditCard, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
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
      <div className="dash-card dash-sub" style={{ justifyContent: "center", minHeight: 108 }}>
        <Loader2 className="dash-spin" style={{ width: 20, height: 20, color: "var(--fg-muted)" }} />
      </div>
    );
  }

  const active = subscription?.status === "active";

  return (
    <div className="dash-card dash-sub">
      <div className="dash-sub-left">
        <span className="dash-sub-icon">{subscription ? <CreditCard /> : <Sparkles />}</span>
        <div>
          <p className="dash-sub-k">Subscription</p>
          <p className="dash-sub-plan">{subscription?.plan || "Free"}</p>
          <p className="dash-sub-desc">
            {active
              ? `Renews ${new Date(subscription.currentPeriodEnd).toLocaleDateString()}`
              : "Upgrade to unlock more features"}
          </p>
        </div>
      </div>
      <div className="dash-sub-right">
        {subscription?.features.slice(0, 2).map((feature) => (
          <span key={feature} className="dash-feature">
            <Check />
            {feature}
          </span>
        ))}
        <Link href="/pricing" className="dash-btn dash-btn--sm">
          {active ? "Manage" : "Upgrade"}
        </Link>
      </div>
    </div>
  );
}
