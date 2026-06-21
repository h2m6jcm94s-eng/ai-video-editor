// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Check, Loader2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useApi } from "@/lib/api/client";

const plans = [
  {
    name: "Free",
    price: "$0",
    period: "/month",
    description: "Try the editor with limited AI generations.",
    features: ["3 projects", "5 AI generations / month", "720p exports", "Basic effects"],
    cta: "Get started",
    href: "/dashboard",
    popular: false,
  },
  {
    name: "Pro",
    price: "$29",
    period: "/month",
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
    period: "/month",
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
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <Link href="/dashboard" className="flex items-center gap-2 text-zinc-100">
            <Sparkles className="w-5 h-5 text-indigo-400" />
            <span className="font-semibold tracking-tight">AI Video Editor</span>
          </Link>
          <Link href="/dashboard" className="text-sm text-zinc-400 hover:text-zinc-100 transition-colors">
            Dashboard
          </Link>
        </div>
      </header>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24 text-center">
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight">
          Simple pricing for <span className="text-gradient">every creator</span>
        </h1>
        <p className="mt-4 text-lg text-glass-subtle max-w-2xl mx-auto">
          Start free, upgrade when you need more exports, AI generations, and team features.
        </p>

        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`glass-card p-6 relative flex flex-col ${plan.popular ? "border-indigo-500/50" : ""}`}
            >
              {plan.popular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-indigo-500 text-white text-xs font-medium">
                  Most popular
                </span>
              )}
              <h3 className="text-lg font-semibold text-white">{plan.name}</h3>
              <div className="mt-2 flex items-baseline gap-1">
                <span className="text-4xl font-bold text-white">{plan.price}</span>
                <span className="text-zinc-500 text-sm">{plan.period}</span>
              </div>
              <p className="mt-2 text-sm text-glass-subtle">{plan.description}</p>

              <ul className="mt-6 space-y-3 flex-1">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-zinc-300">
                    <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    {feature}
                  </li>
                ))}
              </ul>

              {plan.href ? (
                <Button asChild variant="outline" className="mt-6 w-full">
                  <Link href={plan.href}>{plan.cta}</Link>
                </Button>
              ) : (
                <Button
                  onClick={() => handleCheckout(plan.name)}
                  disabled={checkoutLoading === plan.name}
                  className="mt-6 w-full"
                >
                  {checkoutLoading === plan.name ? <Loader2 className="w-4 h-4 animate-spin" /> : plan.cta}
                </Button>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
