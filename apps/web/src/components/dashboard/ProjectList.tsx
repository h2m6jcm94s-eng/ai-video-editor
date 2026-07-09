// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { motion } from "framer-motion";
import { Film } from "lucide-react";
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
        className="dash-empty"
      >
        <span className="dash-empty-icon">
          <Film />
        </span>
        <h3>No projects yet</h3>
        <p>Upload a reference video, your clips, and a song. The AI will build the first cut in seconds.</p>
        <CreateProjectDialog className="dash-btn dash-btn--primary" />
      </motion.div>
    );
  }

  return (
    <section>
      <div className="dash-section-head">
        <div>
          <span className="dash-eyebrow">
            <span className="dot" />
            Your library
          </span>
          <h2 style={{ marginTop: 12 }}>
            Your <em>projects</em>
          </h2>
        </div>
        <span className="num">{projects.length} total</span>
      </div>
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.06 } },
        }}
        className="dash-projects"
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
