// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
"use client";

import { useEffect } from "react";
import { logger } from "@/lib/logger";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    logger.error("Route error", { message: error.message, stack: error.stack, digest: error.digest });
  }, [error]);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center p-4">
      <h2 className="text-xl font-semibold mb-3">Something went wrong</h2>
      <p className="text-gray-600 mb-4 text-center max-w-md">
        {error.message || "An unexpected error occurred while loading this page."}
      </p>
      <button onClick={reset} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
        Try again
      </button>
    </div>
  );
}
