// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Check, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/dashboard/AppShell";
import { useApi } from "@/lib/api/client";

const plans = [
  {
    name: "Free",
    price: "$0",
    period: "/mo",
    description: "Try the editor with limited AI generations.",
    features: ["3 projects", "5 AI generations / month", "720p exports", "Basic effects"],
    cta: "Get started",
    href: "/dashboard",
    popular: false,
  },
  {
    name: "Pro",
    price: "$29",
    period: "/mo",
    description: "Unlimited creative power for solo creators.",
    features: [
      "Unlimited projects",
      "Unlimited AI generations",
      "4K exports",
      "All effects",
      "Priority rendering",
    ],
    cta: "Upgrade to Pro",
    href: null,
    popular: true,
  },
  {
    name: "Team",
    price: "$99",
    period: "/mo",
    description: "Shared workspace and admin controls.",
    features: ["Everything in Pro", "Up to 5 seats", "Shared asset library", "Admin analytics", "SSO (soon)"],
    cta: "Contact sales",
    href: "mailto:sales@example.com",
    popular: false,
  },
];

export default function PricingPage() {
  const api = useApi();
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  const handleCheckout = async (planName: string) => {
    setCheckoutLoading(planName);
    try {
      const { url } = await api.billing.checkout();
      window.location.href = url;
    } catch {
      setCheckoutLoading(null);
    }
  };

  return (
    <AppShell section="Pricing">
      <section className="dash-hero" style={{ paddingBottom: 0 }}>
        <span className="dash-eyebrow">
          <span className="dot" />
          Plans &amp; billing
        </span>
        <h1>
          Pricing for <em>every creator.</em>
        </h1>
        <p>Start free, upgrade when you need more exports, AI generations, and team features.</p>
      </section>

      <div className="dash-pricing">
        {plans.map((plan) => (
          <div key={plan.name} className={`dash-plan-card${plan.popular ? " popular" : ""}`}>
            {plan.popular && <span className="dash-plan-tag">Most popular</span>}
            <span className="dash-plan-name">{plan.name}</span>
            <span className="dash-plan-price">
              {plan.price}
              <span className="per">{plan.period}</span>
            </span>
            <p className="dash-plan-desc">{plan.description}</p>
            <ul className="dash-plan-features">
              {plan.features.map((feature) => (
                <li key={feature}>
                  <Check />
                  {feature}
                </li>
              ))}
            </ul>
            {plan.href ? (
              <Link
                href={plan.href}
                className={`dash-btn dash-btn--block${plan.popular ? " dash-btn--primary" : ""}`}
              >
                {plan.cta}
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => handleCheckout(plan.name)}
                disabled={checkoutLoading === plan.name}
                className={`dash-btn dash-btn--block${plan.popular ? " dash-btn--primary" : ""}`}
              >
                {checkoutLoading === plan.name ? <Loader2 className="dash-spin" /> : plan.cta}
              </button>
            )}
          </div>
        ))}
      </div>
    </AppShell>
  );
}
