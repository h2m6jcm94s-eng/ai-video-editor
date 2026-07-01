// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { usePathname } from "next/navigation";
import { NotificationBell } from "@/components/NotificationBell";
import { DashboardSidebar } from "./DashboardSidebar";
import "@/components/landing/landing.css";
import "./dashboard.css";

function sectionFor(pathname: string): string {
  if (pathname.startsWith("/pricing")) return "Pricing";
  if (pathname.startsWith("/settings")) return "Settings";
  if (pathname.startsWith("/dashboard")) return "Overview";
  return "Studio";
}

export function AppShell({ children, section }: { children: React.ReactNode; section?: string }) {
  const pathname = usePathname();
  const label = section ?? sectionFor(pathname);

  return (
    <div className="stencil dash-root" data-theme="dark">
      <div className="dash-layout">
        <DashboardSidebar />
        <div className="dash-content">
          <div className="dash-topbar">
            <span className="dash-crumb">
              Stencil <span className="sep">/</span> <b>{label}</b>
            </span>
            <div className="dash-topbar-right">
              <NotificationBell className="dash-bell" badgeClassName="badge" />
            </div>
          </div>
          <main className="dash-main">{children}</main>
        </div>
      </div>
    </div>
  );
}
