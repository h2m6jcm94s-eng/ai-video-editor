// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import Link from "next/link";
import { apiServer } from "@/lib/api/server";

interface Props {
  params: Promise<{ userId: string }>;
}

export default async function AdminUserDetailPage({ params }: Props) {
  const { userId } = await params;

  let data;
  try {
    data = await apiServer.admin.users.get(userId);
  } catch {
    return (
      <div>
        <h2 className="text-xl font-semibold mb-4">User not found</h2>
        <Link href="/admin/users" className="text-blue-400 hover:text-blue-300 text-sm">
          ← Back to users
        </Link>
      </div>
    );
  }

  return (
    <div>
      <Link href="/admin/users" className="text-blue-400 hover:text-blue-300 text-sm">
        ← Back to users
      </Link>

      <h2 className="text-xl font-semibold mt-4 mb-2">{data.user.name || data.user.email}</h2>
      <p className="text-sm text-zinc-400 mb-6">{data.user.email}</p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-sm text-zinc-400">Errors</p>
          <p className="text-2xl font-bold">{data.stats.errors}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-sm text-zinc-400">Projects</p>
          <p className="text-2xl font-bold">{data.stats.projects}</p>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
          <p className="text-sm text-zinc-400">Renders</p>
          <p className="text-2xl font-bold">{data.stats.renders}</p>
        </div>
      </div>
    </div>
  );
}
