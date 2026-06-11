// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { apiServer } from "@/lib/api/server";

export default async function AdminOverviewPage() {
  let overview;
  try {
    overview = await apiServer.admin.overview();
  } catch {
    overview = {
      users: { total: 0, active24h: 0 },
      errors: { total: 0, last24h: 0 },
      renders: { total: 0, queued: 0, running: 0 },
    };
  }

  const cards = [
    { label: "Total Users", value: overview.users.total, sub: `${overview.users.active24h} active 24h` },
    { label: "Total Errors", value: overview.errors.total, sub: `${overview.errors.last24h} last 24h` },
    { label: "Renders Queued", value: overview.renders.queued, sub: `${overview.renders.running} running` },
    { label: "Total Renders", value: overview.renders.total, sub: "all time" },
  ];

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Overview</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div key={card.label} className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <p className="text-sm text-zinc-400">{card.label}</p>
            <p className="text-2xl font-bold mt-1">{card.value}</p>
            <p className="text-xs text-zinc-500 mt-1">{card.sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
