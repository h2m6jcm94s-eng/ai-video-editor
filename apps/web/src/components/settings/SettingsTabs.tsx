// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { CreditCard, Keyboard, KeyRound, Palette, Settings, User } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { label: "Account", href: "/settings/account", icon: User, disabled: true },
  { label: "Billing", href: "/settings/billing", icon: CreditCard, disabled: false },
  { label: "API Keys", href: "/settings/keys", icon: KeyRound, disabled: false },
  { label: "Appearance", href: "/settings/appearance", icon: Palette, disabled: true },
  { label: "Shortcuts", href: "/settings/shortcuts", icon: Keyboard, disabled: true },
  { label: "Advanced", href: "/settings/advanced", icon: Settings, disabled: true },
];

export function SettingsTabs() {
  const pathname = usePathname();
  return (
    <nav className="dash-subnav">
      <p className="dash-subnav-label">Settings</p>
      {TABS.map(({ label, href, icon: Icon, disabled }) =>
        disabled ? (
          <span key={href} className="disabled" title="Coming soon">
            <Icon />
            {label}
          </span>
        ) : (
          <Link key={href} href={href} className={cn(pathname.startsWith(href) && "active")}>
            <Icon />
            {label}
          </Link>
        ),
      )}
    </nav>
  );
}
