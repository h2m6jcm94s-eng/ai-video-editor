"use client";

import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import type { CutList } from "@/types/api";

export type SaveState =
  | { status: "idle" }
  | { status: "saving" }
  | { status: "saved"; at: Date }
  | { status: "error"; err: APIError | Error };

interface UseAutosaveOptions {
  projectId: string;
  cutList: CutList | null;
  onRollback: (cl: CutList) => void;
  debounceMs?: number;
}

export function useAutosave({ projectId, cutList, onRollback, debounceMs = 1500 }: UseAutosaveOptions) {
  const api = useApi();
  const [state, setState] = useState<SaveState>({ status: "idle" });
  const lastSavedRef = useRef<CutList | null>(cutList);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<CutList | null>(null);

  useEffect(() => {
    if (!cutList) return;
    if (cutList === lastSavedRef.current) return;
    if (JSON.stringify(cutList) === JSON.stringify(lastSavedRef.current)) return;

    pendingRef.current = cutList;

    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setState({ status: "idle" });

    timeoutRef.current = setTimeout(async () => {
      const toSave = pendingRef.current;
      if (!toSave) return;

      setState({ status: "saving" });
      try {
        await api.projects.updateCutlist(projectId, toSave);
        lastSavedRef.current = toSave;
        setState({ status: "saved", at: new Date() });
      } catch (err) {
        const error = err instanceof APIError ? err : err instanceof Error ? err : new Error("Save failed");
        setState({ status: "error", err: error });
        if (lastSavedRef.current) {
          onRollback(lastSavedRef.current);
        }
      }
    }, debounceMs);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [projectId, cutList, api, onRollback, debounceMs]);

  const retry = () => {
    const toSave = pendingRef.current ?? cutList;
    if (!toSave) return;

    setState({ status: "saving" });
    api.projects
      .updateCutlist(projectId, toSave)
      .then(() => {
        lastSavedRef.current = toSave;
        setState({ status: "saved", at: new Date() });
      })
      .catch((err) => {
        const error = err instanceof APIError ? err : err instanceof Error ? err : new Error("Save failed");
        setState({ status: "error", err: error });
        if (lastSavedRef.current) {
          onRollback(lastSavedRef.current);
        }
      });
  };

  return { state, retry };
}
