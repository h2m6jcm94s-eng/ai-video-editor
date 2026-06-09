// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

export default function SettingsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Settings error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center p-4">
      <AlertTriangle className="w-10 h-10 text-amber-500 mb-4" />
      <h2 className="text-xl font-semibold mb-2">Settings failed to load</h2>
      <p className="text-zinc-400 mb-6 text-center max-w-md">
        {error.message || "Something went wrong while loading settings."}
      </p>
      <button
        onClick={reset}
        className="px-4 py-2 bg-zinc-800 text-zinc-100 rounded-lg hover:bg-zinc-700 transition"
      >
        Try again
      </button>
    </div>
  );
}
