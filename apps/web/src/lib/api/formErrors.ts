"use client";

import { APIError } from "./error";
import type { FieldValues, UseFormSetError } from "react-hook-form";

/**
 * Maps a backend VALIDATION_ERROR to react-hook-form field errors.
 * Returns true if errors were mapped, false otherwise.
 */
export function mapApiValidationErrors<T extends FieldValues>(
  err: APIError,
  setError: UseFormSetError<T>
): boolean {
  if (err.code !== "VALIDATION_ERROR" || !Array.isArray(err.details)) {
    return false;
  }
  for (const issue of err.details as Array<{ path: (string | number)[]; message: string }>) {
    const field = String(issue.path[0]);
    setError(field as Parameters<typeof setError>[0], { message: issue.message });
  }
  return true;
}
