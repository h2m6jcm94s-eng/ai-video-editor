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
  "RATE_LIMITED",
  "INTERNAL_ERROR",
] as const;

export type ApiErrorCode = (typeof API_ERROR_CODES)[number];

export interface ApiError {
  code: ApiErrorCode;
  message: string;
  details?: unknown;
  requestId?: string;
}

export function createApiError(
  code: ApiErrorCode,
  message: string,
  details?: unknown,
  requestId?: string
): ApiError {
  return { code, message, details, requestId };
}
