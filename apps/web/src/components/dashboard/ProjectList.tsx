// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Film } from "lucide-react";
import { ProjectCard } from "./ProjectCard";
import type { Project } from "@/types/api";

export function ProjectList({ projects }: { projects: Project[] }) {
  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-zinc-500 border border-dashed border-zinc-800 rounded-2xl bg-zinc-950/50">
        <div className="w-16 h-16 rounded-full bg-zinc-900 flex items-center justify-center mb-4">
          <Film className="w-8 h-8 text-zinc-600" />
        </div>
        <h3 className="text-lg font-medium text-zinc-300">No projects yet</h3>
        <p className="text-sm mt-1 mb-5 max-w-xs text-center">
          Upload a reference video, your clips, and a song. The AI will build the first cut.
        </p>
        <p className="text-xs text-zinc-600">Click &quot;New Project&quot; in the top right to start.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
