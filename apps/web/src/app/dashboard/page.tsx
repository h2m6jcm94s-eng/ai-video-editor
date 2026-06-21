// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { HeroSection } from "@/components/dashboard/HeroSection";
import { ProjectList } from "@/components/dashboard/ProjectList";
import { StatsSection } from "@/components/dashboard/StatsSection";
import { apiServer } from "@/lib/api/server";
import { getServerAuth } from "@/lib/auth";

export default async function DashboardPage() {
  const { userId } = await getServerAuth();
  if (!userId) redirect("/sign-in");

  let projects: Awaited<ReturnType<typeof apiServer.projects.list>>["projects"] = [];
  try {
    const res = await apiServer.projects.list();
    projects = res.projects;
  } catch (err) {
    console.error("Failed to load projects:", err);
  }

  return (
    <main className="min-h-screen text-foreground">
      <DashboardHeader />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">
        <HeroSection projectCount={projects.length} />
        <StatsSection projects={projects} />
        <div className="mt-10">
          <ProjectList projects={projects} />
        </div>
      </div>
    </main>
  );
}
