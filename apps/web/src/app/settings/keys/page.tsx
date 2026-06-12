// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";
import { ProviderKeyManager } from "@/components/settings/ProviderKeyManager";
import { apiServer } from "@/lib/api/server";
import { getServerAuth } from "@/lib/auth";

export default async function KeysPage() {
  const { userId } = await getServerAuth();
  if (!userId) redirect("/sign-in");

  let keys: Awaited<ReturnType<typeof apiServer.settings.providerKeys.list>>["keys"] = [];
  try {
    const res = await apiServer.settings.providerKeys.list();
    keys = res.keys;
  } catch (err) {
    console.error("Failed to load provider keys:", err);
  }

  return <ProviderKeyManager initialKeys={keys} />;
}
