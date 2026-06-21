// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { motion } from "framer-motion";

export function HeroSection({ projectCount }: { projectCount: number }) {
  return (
    <section className="relative py-10 sm:py-14">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="max-w-3xl"
      >
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight">
          <span className="text-gradient">Create videos</span>
          <span className="text-white"> that feel like magic.</span>
        </h1>
        <p className="mt-4 text-lg text-glass-subtle leading-relaxed max-w-2xl">
          Upload a reference, drop your clips, pick a song, and let AI match the style, cuts, and energy —
          automatically.
        </p>
        {projectCount > 0 && (
          <p className="mt-3 text-sm text-glass-faint">
            You have {projectCount} project{projectCount === 1 ? "" : "s"} ready to edit.
          </p>
        )}
      </motion.div>
    </section>
  );
}
