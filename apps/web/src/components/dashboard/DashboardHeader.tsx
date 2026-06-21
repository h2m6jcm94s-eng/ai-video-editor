// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { CreditCard, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { CreateProjectDialog } from "@/components/dashboard/CreateProjectDialog";
import { Button } from "@/components/ui/button";

export function DashboardHeader() {
  return (
    <header className="sticky top-0 z-50 glass-strong border-b border-white/[0.08]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-glow">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <span className="text-lg font-semibold tracking-tight text-gradient">AI Video Editor</span>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <Button
            variant="ghost"
            size="sm"
            asChild
            className="text-glass-muted hover:text-glass hover:bg-glass-hover hidden sm:inline-flex"
          >
            <Link href="/pricing">
              <CreditCard className="h-4 w-4 mr-1.5" />
              Pricing
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            asChild
            className="text-glass-muted hover:text-glass hover:bg-glass-hover"
          >
            <Link href="/settings">
              <Settings className="h-4 w-4 mr-1.5" />
              <span className="hidden sm:inline">Settings</span>
            </Link>
          </Button>
          <CreateProjectDialog />
        </div>
      </div>
    </header>
  );
}
