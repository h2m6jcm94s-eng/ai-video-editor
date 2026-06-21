// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { motion } from "framer-motion";
import { Film, Plus } from "lucide-react";
import type { Project } from "@/types/api";
import { CreateProjectDialog } from "./CreateProjectDialog";
import { ProjectCard } from "./ProjectCard";

export function ProjectList({ projects }: { projects: Project[] }) {
  if (projects.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5 }}
        className="glass-card flex flex-col items-center justify-center py-24 text-center"
      >
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-indigo-500/20 blur-2xl" />
          <div className="relative w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-white/[0.12] flex items-center justify-center mb-5">
            <Film className="w-9 h-9 text-indigo-300" />
          </div>
        </div>
        <h3 className="text-xl font-semibold text-white">No projects yet</h3>
        <p className="text-sm mt-2 max-w-sm text-glass-subtle">
          Upload a reference video, your clips, and a song. The AI will build the first cut in seconds.
        </p>
        <div className="mt-6">
          <CreateProjectDialog />
        </div>
      </motion.div>
    );
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-xl font-semibold text-white">Your Projects</h2>
        <CreateProjectDialog />
      </div>
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.06 } },
        }}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
      >
        {projects.map((project) => (
          <motion.div
            key={project.id}
            variants={{
              hidden: { opacity: 0, y: 20 },
              visible: { opacity: 1, y: 0 },
            }}
          >
            <ProjectCard project={project} />
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
