export const API_ERROR_CODES = [
  // Auth
  "UNAUTHORIZED",
  "FORBIDDEN",
  "SIGNUP_REQUIRED",
  // Validation
  "VALIDATION_ERROR",
  "INVALID_ENUM",
  "PAYLOAD_TOO_LARGE",
  // Resource
  "NOT_FOUND",
  "PROJECT_NOT_FOUND",
  "ASSET_NOT_FOUND",
  "RENDER_NOT_FOUND",
  "TEMPLATE_NOT_FOUND",
  // Conflict
  "CONFLICT",
  "RENDER_ALREADY_RUNNING",
  "CONCURRENT_EDIT",
  "PROJECT_LOCKED",
  // Provider
  "PROVIDER_KEY_MISSING",
  "PROVIDER_RATE_LIMITED",
  "PROVIDER_TIMEOUT",
  "PROVIDER_INVALID_RESPONSE",
  "PROVIDER_QUOTA_EXCEEDED",
  "ALL_PROVIDERS_FAILED",
  // AI-specific
  "AI_REFUSED",
  "AI_INVALID_JSON",
  "AI_DIFF_INVALID",
  "AI_DIFF_OUT_OF_BOUNDS",
  "CUTLIST_SCHEMA_DRIFT",
  "PROMPT_TOO_LONG",
  // Pipeline
  "BEAT_DETECT_FAILED",
  "SHOT_DETECT_FAILED",
  "RENDER_FFMPEG_FAILED",
  "UPLOAD_INCOMPLETE",
  "ETAG_MISMATCH",
  // Infra
  "DB_UNAVAILABLE",
  "REDIS_UNAVAILABLE",
  "TEMPORAL_UNAVAILABLE",
  "R2_UNAVAILABLE",
  "STORAGE_ERROR",
  "RATE_LIMITED",
  "INTERNAL_ERROR",
  "USER_RESOLUTION_ERROR",
  "GUARDRAILS_VIOLATION",
  "MISSING_ASSETS",
  "TEMPORAL_ERROR",
  "BUDGET_EXCEEDED",
  "NO_CUTLIST",
  "PENDING",
] as const;

export type ApiErrorCode = (typeof API_ERROR_CODES)[number];

export interface ApiError {
  code: ApiErrorCode;
  message: string;
  details?: unknown;
  requestId?: string;
}

export function isApiErrorCode(code: string | undefined): code is ApiErrorCode {
  return code !== undefined && (API_ERROR_CODES as readonly string[]).includes(code as ApiErrorCode);
}

export function createApiError(
  code: ApiErrorCode,
  message: string,
  details?: unknown,
  requestId?: string,
): ApiError {
  return { code, message, details, requestId };
}
