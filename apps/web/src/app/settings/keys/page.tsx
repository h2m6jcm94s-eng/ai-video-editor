// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { apiServer } from "@/lib/api/server";
import { ProviderKeyManager } from "@/components/settings/ProviderKeyManager";

export default async function KeysPage() {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in");

  let keys: Awaited<ReturnType<typeof apiServer.settings.providerKeys.list>>["keys"] = [];
  try {
    const res = await apiServer.settings.providerKeys.list();
    keys = res.keys;
  } catch {
    // Silent fail — empty state handles it
  }

  return <ProviderKeyManager initialKeys={keys} />;
}
