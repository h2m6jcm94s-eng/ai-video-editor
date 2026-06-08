// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { Skeleton } from "@/components/ui/skeleton";

export default function EditorLoading() {
  return (
    <div className="min-h-screen bg-zinc-950 grid grid-cols-[260px_1fr_280px] grid-rows-[56px_1fr_200px]">
      <Skeleton className="col-span-3 h-14 border-b border-zinc-800" />
      <Skeleton className="border-r border-zinc-800" />
      <Skeleton />
      <Skeleton className="border-l border-zinc-800" />
      <Skeleton className="col-span-3 border-t border-zinc-800" />
    </div>
  );
}
