// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { apiServer } from "@/lib/api/server";

export default async function AdminErrorsPage() {
  let events: Array<{ id: string; userId: string; code: string; message: string; createdAt: string }> = [];
  try {
    const res = await apiServer.admin.errors();
    events = res.items;
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("[admin/errors] Failed to load:", e);
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Error Log</h2>
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Code</th>
              <th className="px-4 py-3 text-left font-medium">Message</th>
              <th className="px-4 py-3 text-left font-medium">User</th>
              <th className="px-4 py-3 text-left font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {events.map((evt) => (
              <tr key={evt.id} className="hover:bg-zinc-900/50">
                <td className="px-4 py-3 font-mono text-xs">{evt.code}</td>
                <td className="px-4 py-3">{evt.message}</td>
                <td className="px-4 py-3 text-xs text-zinc-400">{evt.userId.slice(0, 8)}…</td>
                <td className="px-4 py-3 text-xs text-zinc-400">
                  {new Date(evt.createdAt).toLocaleString()}
                </td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500">
                  No errors
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
