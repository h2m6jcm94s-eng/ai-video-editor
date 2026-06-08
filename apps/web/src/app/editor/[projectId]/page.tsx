// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { auth } from "@clerk/nextjs/server";
import { redirect, notFound } from "next/navigation";
import { api } from "@/lib/api";
import { EditorLayout } from "@/components/editor/EditorLayout";
import { EditorErrorBoundary } from "@/components/editor/ErrorBoundary";

interface EditorPageProps {
  params: Promise<{ projectId: string }>;
}

export default async function EditorPage({ params }: EditorPageProps) {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  const { projectId } = await params;

  let project: Awaited<ReturnType<typeof api.projects.get>>["project"] | null = null;
  let assets: Awaited<ReturnType<typeof api.projects.get>>["project"]["assets"] = [];
  try {
    const res = await api.projects.get(projectId);
    project = res.project;
    assets = res.project.assets;
  } catch {
    notFound();
  }

  if (!project) notFound();

  return (
    <EditorErrorBoundary>
      <EditorLayout project={project} assets={assets} />
    </EditorErrorBoundary>
  );
}
