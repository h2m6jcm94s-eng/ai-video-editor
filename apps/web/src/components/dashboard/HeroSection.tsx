// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { motion } from "framer-motion";

export function HeroSection({ projectCount }: { projectCount: number }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="dash-hero"
    >
      <span className="dash-eyebrow">
        <span className="dot" />
        Reference-driven editing
      </span>
      <h1>
        Create videos <em>that feel like magic.</em>
      </h1>
      <p>
        Upload a reference, drop your clips, pick a song, and let AI match the style, cuts, and energy —
        automatically.
      </p>
      {projectCount > 0 && (
        <p className="note">
          You have <b>{projectCount}</b> project{projectCount === 1 ? "" : "s"} ready to edit.
        </p>
      )}
    </motion.section>
  );
}
