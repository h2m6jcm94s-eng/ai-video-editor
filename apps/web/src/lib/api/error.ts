import type { ApiErrorCode } from "@ai-video-editor/shared-types";

export class APIError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: ApiErrorCode,
    message: string,
    public readonly details?: unknown,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = "APIError";
  }

  static async fromResponse(res: Response): Promise<APIError> {
    let parsed: { error?: string; code?: ApiErrorCode; details?: unknown; requestId?: string } = {};
    try {
      parsed = await res.json();
    } catch {
      // ignore parse failures
    }
    return new APIError(
      res.status,
      parsed.code ?? "INTERNAL_ERROR",
      parsed.error ?? `HTTP ${res.status}`,
      parsed.details,
      parsed.requestId,
    );
  }

  get userMessage(): string {
    switch (this.code) {
      case "UNAUTHORIZED":
        return "Please sign in again.";
      case "FORBIDDEN":
        return "You don't have access to this resource.";
      case "NOT_FOUND":
      case "PROJECT_NOT_FOUND":
      case "ASSET_NOT_FOUND":
      case "RENDER_NOT_FOUND":
      case "TEMPLATE_NOT_FOUND":
        return "We couldn't find what you were looking for.";
      case "VALIDATION_ERROR":
        return this.formatZodErrors() ?? "Please check your input.";
      case "CONFLICT":
      case "RENDER_ALREADY_RUNNING":
      case "GENERATION_ALREADY_RUNNING":
      case "CONCURRENT_EDIT":
      case "PROJECT_LOCKED":
        return "This conflicts with current state. Refresh and try again.";
      case "RATE_LIMITED":
        return "Slow down for a moment.";
      case "PROVIDER_KEY_MISSING":
        return `Connect your ${(this.details as Record<string, string>)?.provider ?? "AI"} key in Settings to use this feature.`;
      case "PROVIDER_RATE_LIMITED":
      case "PROVIDER_TIMEOUT":
      case "PROVIDER_INVALID_RESPONSE":
      case "PROVIDER_QUOTA_EXCEEDED":
        return "The AI service is having issues. Try again in a moment.";
      case "AI_REFUSED":
      case "AI_INVALID_JSON":
      case "AI_DIFF_INVALID":
      case "AI_DIFF_OUT_OF_BOUNDS":
        return "The AI couldn't process that request. Try rephrasing.";
      case "UPLOAD_INCOMPLETE":
      case "ETAG_MISMATCH":
        return "Upload failed. Please try again.";
      case "SIGNUP_REQUIRED":
        return "Please complete sign-up to continue.";
      case "INVALID_ENUM":
        return "Invalid option selected. Please choose a valid value.";
      case "PAYLOAD_TOO_LARGE":
        return "Your request is too large. Try reducing the size.";
      case "CUTLIST_SCHEMA_DRIFT":
        return "Your project data is out of date. Refresh the page.";
      case "PROMPT_TOO_LONG":
        return "Your prompt is too long. Shorten it and try again.";
      case "BEAT_DETECT_FAILED":
        return "Couldn't analyze the song's beat. Try a different audio file.";
      case "SHOT_DETECT_FAILED":
        return "Couldn't analyze the video. Try a different file.";
      case "RENDER_FFMPEG_FAILED":
        return "Rendering failed. Try again or adjust your project.";
      case "DB_UNAVAILABLE":
      case "REDIS_UNAVAILABLE":
      case "TEMPORAL_UNAVAILABLE":
      case "R2_UNAVAILABLE":
      case "STORAGE_ERROR":
      case "METRICS_ERROR":
        return "Service temporarily unavailable. Try again in a moment.";
      case "ALL_PROVIDERS_FAILED":
        return "Every AI provider in your chain failed. Check your keys in Settings or try again.";
      case "NO_CUTLIST":
        return "This project has no timeline yet. Generate or import one first.";
      case "PENDING":
        return "This is still processing. Check back in a moment.";
      default:
        return "Something went wrong.";
    }
  }

  private formatZodErrors(): string | undefined {
    if (!this.details || !Array.isArray(this.details)) return undefined;
    const issues = this.details as Array<{ path: (string | number)[]; message: string }>;
    return issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
  }
}
