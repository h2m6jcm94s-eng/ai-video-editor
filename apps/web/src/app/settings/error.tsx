// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect } from "react";

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
    <div className="dash-empty">
      <span className="dash-empty-icon" style={{ color: "#ff7a5c" }}>
        <AlertTriangle />
      </span>
      <h3>Settings failed to load</h3>
      <p>{error.message || "Something went wrong while loading settings."}</p>
      <button onClick={reset} className="dash-btn dash-btn--primary" type="button">
        Try again
      </button>
    </div>
  );
}
