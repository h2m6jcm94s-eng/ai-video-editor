// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.

import { compare, type Operation } from "fast-json-patch";
import type { CutList } from "@/types/api";

export function diffCutLists(before: CutList, after: CutList): Operation[] {
  return compare(before, after);
}

export function summarizeOps(ops: Operation[]): string {
  return `${ops.length} change${ops.length === 1 ? "" : "s"}`;
}
