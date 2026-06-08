"use client";

import { useMemo } from "react";
import { useAuth } from "@clerk/nextjs";
import { createAPI } from "./core";

export function useApi() {
  const { getToken } = useAuth();
  return useMemo(() => createAPI(getToken), [getToken]);
}
