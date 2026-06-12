"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo, useRef } from "react";
import { createAPI } from "./core";

export function useApi() {
  const { getToken } = useAuth();
  // Keep getToken fresh without rebuilding the API object on every render.
  // Clerk's getToken reference changes each render; a stable api object prevents
  // effect / callback dependency churn in downstream hooks.
  const getTokenRef = useRef(getToken);
  getTokenRef.current = getToken;

  return useMemo(() => createAPI(() => getTokenRef.current()), []);
}
