// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export default function DashboardLoading() {
  return (
    <div className="min-h-screen bg-[#0a0908]">
      <div className="grid grid-cols-1 md:grid-cols-[264px_minmax(0,1fr)] min-h-screen">
        <div className="hidden md:block border-r border-[#2a2520]" />
        <div className="p-8 md:p-12 space-y-10 animate-pulse">
          <div className="h-14 w-2/3 max-w-xl rounded bg-[#15110d]" />
          <div className="h-24 w-full rounded-md border border-[#2a2520] bg-[#15110d]/60" />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-28 rounded-md border border-[#2a2520] bg-[#15110d]/60" />
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-56 rounded-md border border-[#2a2520] bg-[#15110d]/60" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
