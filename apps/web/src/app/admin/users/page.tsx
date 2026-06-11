// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import Link from "next/link";
import { apiServer } from "@/lib/api/server";

export default async function AdminUsersPage() {
  let users: Array<{ id: string; email: string; name: string | null; createdAt: string }> = [];
  try {
    const res = await apiServer.admin.users.list();
    users = res.items;
  } catch {
    // leave empty
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Users</h2>
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="px-4 py-3 text-left font-medium">Email</th>
              <th className="px-4 py-3 text-left font-medium">Name</th>
              <th className="px-4 py-3 text-left font-medium">Joined</th>
              <th className="px-4 py-3 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {users.map((user) => (
              <tr key={user.id} className="hover:bg-zinc-900/50">
                <td className="px-4 py-3">{user.email}</td>
                <td className="px-4 py-3">{user.name || "—"}</td>
                <td className="px-4 py-3">{new Date(user.createdAt).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  <Link
                    href={`/admin/users/${user.id}`}
                    className="text-blue-400 hover:text-blue-300 text-xs"
                  >
                    View
                  </Link>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500">
                  No users found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
