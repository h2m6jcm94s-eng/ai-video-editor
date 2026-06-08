// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
export const dynamic = "force-dynamic";

import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard");
}
