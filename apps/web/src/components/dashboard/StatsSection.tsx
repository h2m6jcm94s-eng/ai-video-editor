// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { CheckCircle2, Film, Loader2, PlayCircle } from "lucide-react";
import { useCountUp } from "@/hooks/useCountUp";
import type { Project } from "@/types/api";

function StatCard({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: number }) {
  const animated = useCountUp(value);
  return (
    <div className="dash-stat">
      <div className="dash-stat-top">
        <p className="dash-stat-k">{label}</p>
        <span className="dash-stat-icon">
          <Icon />
        </span>
      </div>
      <p data-testid={`stat-${label}`} className="dash-stat-v">
        {animated}
      </p>
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
    <div className="dash-stats">
      <StatCard icon={Film} label="Total Projects" value={total} />
      <StatCard icon={Loader2} label="In Progress" value={inProgress} />
      <StatCard icon={CheckCircle2} label="Completed" value={complete} />
      <StatCard icon={PlayCircle} label="Rendered" value={rendered} />
    </div>
  );
}
