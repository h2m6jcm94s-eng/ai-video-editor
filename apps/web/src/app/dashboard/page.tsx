// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { AlertTriangle } from "lucide-react";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/dashboard/AppShell";
import { HeroSection } from "@/components/dashboard/HeroSection";
import { ProjectList } from "@/components/dashboard/ProjectList";
import { StatsSection } from "@/components/dashboard/StatsSection";
import { SubscriptionCard } from "@/components/dashboard/SubscriptionCard";
import { apiServer } from "@/lib/api/server";
import { getServerAuth } from "@/lib/auth";

export default async function DashboardPage() {
  const { userId } = await getServerAuth();
  if (!userId) redirect("/sign-in");

  let projects: Awaited<ReturnType<typeof apiServer.projects.list>>["projects"] = [];
  let loadError = false;
  try {
    const res = await apiServer.projects.list();
    projects = res.projects;
  } catch (err) {
    loadError = true;
    console.error("Failed to load projects:", err);
  }

  return (
    <AppShell section="Overview">
      {loadError && (
        <div className="dash-error" role="alert">
          <AlertTriangle />
          <div>
            <p className="t">Failed to load projects</p>
            <p className="d">Please refresh the page or try again later.</p>
          </div>
        </div>
      )}
      <HeroSection projectCount={projects.length} />
      <SubscriptionCard />
      <StatsSection projects={projects} />
      <ProjectList projects={projects} />
    </AppShell>
  );
}
