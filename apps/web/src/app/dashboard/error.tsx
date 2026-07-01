// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#0a0908] p-6 text-center text-[#f5f1e8]">
      <AlertTriangle className="mb-5 h-10 w-10 text-[#ff7a5c]" />
      <h2 className="mb-3 font-serif text-2xl">Dashboard failed to load</h2>
      <p className="mb-7 max-w-md text-[#b9b0a1]">
        {error.message || "Something went wrong while loading your projects."}
      </p>
      <button
        onClick={reset}
        className="rounded-full bg-[#ff4d1f] px-6 py-3 text-xs font-medium uppercase tracking-[0.18em] text-white transition-colors hover:bg-[#ff5c30]"
      >
        Try again
      </button>
    </div>
  );
}
