// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { KeyRound, User, Palette, Keyboard, Settings, ArrowLeft } from "lucide-react";

const tabs = [
  { label: "Account", href: "/settings/account", icon: User, disabled: true },
  { label: "API Keys", href: "/settings/keys", icon: KeyRound },
  { label: "Appearance", href: "/settings/appearance", icon: Palette, disabled: true },
  { label: "Shortcuts", href: "/settings/shortcuts", icon: Keyboard, disabled: true },
  { label: "Advanced", href: "/settings/advanced", icon: Settings, disabled: true },
];

export default async function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors text-sm"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Link>
            <div className="h-4 w-px bg-zinc-800" />
            <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Sidebar */}
          <aside className="w-full lg:w-56 shrink-0">
            <nav className="space-y-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return tab.disabled ? (
                  <span
                    key={tab.href}
                    className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-zinc-600 cursor-not-allowed"
                    title="Coming soon"
                  >
                    <Icon className="h-4 w-4" />
                    {tab.label}
                  </span>
                ) : (
                  <Link
                    key={tab.href}
                    href={tab.href}
                    className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 transition-colors"
                  >
                    <Icon className="h-4 w-4" />
                    {tab.label}
                  </Link>
                );
              })}
            </nav>
          </aside>

          {/* Content */}
          <div className="flex-1 min-w-0">{children}</div>
        </div>
      </div>
    </main>
  );
}
