// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { auth } from "@clerk/nextjs/server";
import { Settings } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";
import { CreateProjectDialog } from "@/components/dashboard/CreateProjectDialog";
import { ProjectList } from "@/components/dashboard/ProjectList";
import { Button } from "@/components/ui/button";
import { apiServer } from "@/lib/api/server";

export default async function DashboardPage() {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  let projects: Awaited<ReturnType<typeof apiServer.projects.list>>["projects"] = [];
  try {
    const res = await apiServer.projects.list();
    projects = res.projects;
  } catch (err) {
    console.error("Failed to load projects:", err);
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <h1 className="text-lg font-semibold tracking-tight">AI Video Editor</h1>
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/settings">
                <Settings className="h-4 w-4 mr-1.5" />
                Settings
              </Link>
            </Button>
            <CreateProjectDialog />
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <ProjectList projects={projects} />
      </div>
    </main>
  );
}
