// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";

export default function EditorError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Editor error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-4 bg-zinc-950 text-zinc-100">
      <AlertTriangle className="w-12 h-12 text-amber-500 mb-4" />
      <h2 className="text-2xl font-semibold mb-2">Editor crashed</h2>
      <p className="text-zinc-400 mb-2 text-center max-w-md">
        {error.message || "Something went wrong in the video editor."}
      </p>
      <p className="text-zinc-500 text-sm mb-6 text-center max-w-md">
        Your work is auto-saved. You can safely return to the dashboard.
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={reset}
          className="px-4 py-2 bg-zinc-800 text-zinc-100 rounded-lg hover:bg-zinc-700 transition"
        >
          Try again
        </button>
        <Link
          href="/dashboard"
          className="px-4 py-2 bg-zinc-800 text-zinc-100 rounded-lg hover:bg-zinc-700 transition"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
