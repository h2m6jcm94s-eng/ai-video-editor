// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { auth, clerkClient } from "@clerk/nextjs/server";
import { AlertTriangle, ClipboardList, Film, LayoutDashboard, Users } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  const client = await clerkClient();
  const clerkUser = await client.users.getUser(userId);
  const role = clerkUser?.publicMetadata?.role as string | undefined;
  if (role !== "admin") redirect("/dashboard");

  const navItems = [
    { href: "/admin", label: "Overview", icon: LayoutDashboard },
    { href: "/admin/users", label: "Users", icon: Users },
    { href: "/admin/errors", label: "Errors", icon: AlertTriangle },
    { href: "/admin/renders", label: "Renders", icon: Film },
    { href: "/admin/audit", label: "Audit", icon: ClipboardList },
  ];

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="flex h-screen">
        {/* Sidebar */}
        <aside className="w-56 border-r border-zinc-800 bg-zinc-950">
          <div className="p-4 border-b border-zinc-800">
            <h1 className="text-sm font-semibold tracking-tight text-zinc-400 uppercase">Admin</h1>
          </div>
          <nav className="p-2 space-y-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-2 px-3 py-2 rounded-md text-sm hover:bg-zinc-900 transition-colors"
              >
                <item.icon className="h-4 w-4 text-zinc-400" />
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <div className="flex-1 overflow-auto">
          <div className="p-6">{children}</div>
        </div>
      </div>
    </main>
  );
}
