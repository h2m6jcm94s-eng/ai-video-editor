// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { Film } from "lucide-react";
import { ProjectCard } from "./ProjectCard";
import type { Project } from "@/types/api";

export function ProjectList({ projects }: { projects: Project[] }) {
  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-zinc-500">
        <Film className="w-12 h-12 mb-4 opacity-50" />
        <h3 className="text-lg font-medium text-zinc-300">No projects yet</h3>
        <p className="text-sm mt-1">Create your first project to get started.</p>
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
