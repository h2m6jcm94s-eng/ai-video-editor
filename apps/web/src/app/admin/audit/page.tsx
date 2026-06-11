// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { apiServer } from "@/lib/api/server";

export default async function AdminAuditPage() {
  let logs: Array<{
    id: string;
    actorId: string;
    action: string;
    targetType: string | null;
    createdAt: string;
  }> = [];
  try {
    const res = await apiServer.admin.audit();
    logs = res.items;
  } catch {
    // leave empty
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Audit Log</h2>
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Action</th>
              <th className="px-4 py-3 text-left font-medium">Actor</th>
              <th className="px-4 py-3 text-left font-medium">Target</th>
              <th className="px-4 py-3 text-left font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {logs.map((log) => (
              <tr key={log.id} className="hover:bg-zinc-900/50">
                <td className="px-4 py-3 font-mono text-xs">{log.action}</td>
                <td className="px-4 py-3 text-xs text-zinc-400">{log.actorId.slice(0, 8)}…</td>
                <td className="px-4 py-3 text-xs text-zinc-400">{log.targetType || "—"}</td>
                <td className="px-4 py-3 text-xs text-zinc-400">
                  {new Date(log.createdAt).toLocaleString()}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500">
                  No audit entries
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
