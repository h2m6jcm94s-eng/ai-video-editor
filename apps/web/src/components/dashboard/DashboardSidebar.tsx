// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useUser } from "@clerk/nextjs";
import { CreditCard, LayoutGrid, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { CreateProjectDialog } from "./CreateProjectDialog";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutGrid },
  { href: "/pricing", label: "Pricing", icon: CreditCard },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const { user } = useUser();

  const displayName = user?.firstName || user?.primaryEmailAddress?.emailAddress || "Account";
  const initial = (user?.firstName?.[0] || user?.primaryEmailAddress?.emailAddress?.[0] || "S").toUpperCase();

  return (
    <aside className="dash-sidebar">
      <Link href="/" className="dash-brand">
        <span className="logo-mark">
          <em>S</em>tencil
        </span>
        <span className="logo-word">Studio</span>
      </Link>

      <CreateProjectDialog className="dash-btn dash-btn--primary dash-btn--block" />

      <nav className="dash-nav">
        <p className="dash-nav-label">Menu</p>
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
          return (
            <Link key={href} href={href} className={cn("dash-nav-item", active && "active")}>
              <Icon />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="dash-sidebar-foot">
        <div className="dash-userchip">
          <span className="avatar">{initial}</span>
          <span className="who">{displayName}</span>
        </div>
      </div>
    </aside>
  );
}
