// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { CheckCircle2, Film, Loader2, PlayCircle } from "lucide-react";
import { useCountUp } from "@/hooks/useCountUp";
import type { Project } from "@/types/api";

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  color: string;
}) {
  const animated = useCountUp(value);
  return (
    <div className="glass-card p-5 glow-hover group relative overflow-hidden">
      <div className={`absolute -top-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-20 ${color}`} />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-glass-subtle">{label}</p>
          <p data-testid={`stat-${label}`} className="mt-2 text-3xl font-bold tracking-tight text-white">
            {animated}
          </p>
        </div>
        <div
          className={`flex items-center justify-center w-10 h-10 rounded-xl bg-glass-surface border border-glass ${color.replace("bg-", "text-")}`}
        >
          <Icon className="w-5 h-5" />
        </div>
      </div>
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
    </div>
  );
}

export function StatsSection({ projects }: { projects: Project[] }) {
  const total = projects.length;
  const complete = projects.filter((p) => p.status === "complete").length;
  const inProgress = projects.filter((p) =>
    ["uploading", "processing", "rendering"].includes(p.status),
  ).length;
  const rendered = projects.filter((p) => p.renderAssetId).length;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard icon={Film} label="Total Projects" value={total} color="bg-indigo-500" />
      <StatCard icon={Loader2} label="In Progress" value={inProgress} color="bg-amber-500" />
      <StatCard icon={CheckCircle2} label="Completed" value={complete} color="bg-emerald-500" />
      <StatCard icon={PlayCircle} label="Rendered" value={rendered} color="bg-pink-500" />
    </div>
  );
}
