// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { usePathname } from "next/navigation";
import { NotificationBell } from "@/components/NotificationBell";

// Global app chrome (the fixed notification bell). Hidden on the public
// marketing/auth pages (landing, sign-in, sign-up), which have their own design,
// and on the shell pages (dashboard, pricing, settings), which render their own
// bell in the shell top bar.
const HIDE_CHROME = ["/", "/sign-in", "/sign-up", "/dashboard", "/pricing", "/settings"];

export function AppChrome() {
  const pathname = usePathname();
  if (HIDE_CHROME.some((p) => pathname === p || pathname.startsWith(p + "/"))) return null;

  return (
    <div className="fixed top-4 right-4 z-50">
      <div className="glass rounded-full p-1.5">
        <NotificationBell />
      </div>
    </div>
  );
}
