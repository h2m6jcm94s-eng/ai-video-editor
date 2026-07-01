// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { AppShell } from "@/components/dashboard/AppShell";
import { SettingsTabs } from "@/components/settings/SettingsTabs";
import { getServerAuth } from "@/lib/auth";

export default async function SettingsLayout({ children }: { children: React.ReactNode }) {
  const { userId } = await getServerAuth();
  if (!userId) redirect("/sign-in");

  return (
    <AppShell section="Settings">
      <section className="dash-hero" style={{ paddingBottom: 0 }}>
        <span className="dash-eyebrow">
          <span className="dot" />
          Workspace
        </span>
        <h1 style={{ fontSize: "clamp(40px, 5vw, 68px)" }}>
          Settings<em>.</em>
        </h1>
      </section>

      <div className="dash-settings">
        <SettingsTabs />
        <div style={{ minWidth: 0 }}>{children}</div>
      </div>
    </AppShell>
  );
}
