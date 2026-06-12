// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { notFound, redirect } from "next/navigation";
import { EditorLayout } from "@/components/editor/EditorLayout";
import { EditorErrorBoundary } from "@/components/editor/ErrorBoundary";
import { apiServer } from "@/lib/api/server";
import { getServerAuth } from "@/lib/auth";

interface EditorPageProps {
  params: Promise<{ projectId: string }>;
}

export default async function EditorPage({ params }: EditorPageProps) {
  const { userId } = await getServerAuth();
  if (!userId) redirect("/sign-in");

  const { projectId } = await params;

  let project: Awaited<ReturnType<typeof apiServer.projects.get>>["project"] | null = null;
  let assets: Awaited<ReturnType<typeof apiServer.projects.get>>["project"]["assets"] = [];
  try {
    const res = await apiServer.projects.get(projectId);
    project = res.project;
    assets = res.project.assets;
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("[editor/" + projectId + "] Failed to load project:", e);
    notFound();
  }

  if (!project) notFound();

  return (
    <EditorErrorBoundary>
      <EditorLayout project={project} assets={assets} />
    </EditorErrorBoundary>
  );
}
