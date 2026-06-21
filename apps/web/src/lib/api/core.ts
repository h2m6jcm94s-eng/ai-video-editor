import type { Asset, CutList, GenerationJob, Project, RenderJob, Subtitle } from "@/types/api";
import { APIError } from "./error";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

function sleep(ms: number) {
  return new Promise((res) => setTimeout(res, ms));
}

export type TokenGetter = (opts?: { skipCache?: boolean }) => Promise<string | null>;

async function fetchWithRetry(
  path: string,
  init: RequestInit,
  getToken: TokenGetter,
  attempts = 3,
): Promise<Response> {
  const url = `${API_BASE}${path}`;

  for (let i = 0; i < attempts; i++) {
    try {
      // Refresh the Clerk token once on a 401 by skipping the cache.
      const token = await getToken({ skipCache: i > 0 && i === 1 });
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(init.headers as Record<string, string>),
      };
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const res = await fetch(url, {
        ...init,
        credentials: "include",
        headers,
        signal: init.signal ?? AbortSignal.timeout(15_000),
      });

      if (res.status === 401 && i < attempts - 1) {
        await sleep(2 ** i * 100);
        continue;
      }

      if (res.status >= 500 && i < attempts - 1) {
        await sleep(2 ** i * 200);
        continue;
      }

      if (!res.ok) {
        throw await APIError.fromResponse(res);
      }

      return res;
    } catch (err) {
      if (err instanceof APIError) throw err; // 4xx → don't retry
      if (i === attempts - 1) throw err;
      await sleep(2 ** i * 200);
    }
  }

  throw new Error("Unreachable");
}

export function createAPI(getToken: TokenGetter) {
  async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchWithRetry(path, init ?? {}, getToken);
    return res.json();
  }

  return {
    projects: {
      list: (): Promise<{ projects: Project[] }> => fetchJSON("/projects"),
      get: (id: string): Promise<{ project: Project & { assets: Asset[] } }> => fetchJSON(`/projects/${id}`),
      create: (data: { name: string; styleTier?: string; mode?: string }): Promise<{ project: Project }> =>
        fetchJSON("/projects", { method: "POST", body: JSON.stringify(data) }),
      update: (id: string, data: Partial<Project>): Promise<{ project: Project }> =>
        fetchJSON(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
      delete: (id: string): Promise<{ success: boolean }> =>
        fetchJSON(`/projects/${id}`, { method: "DELETE" }),
      updateCutlist: (id: string, cutList: CutList): Promise<{ project: Project }> =>
        fetchJSON(`/projects/${id}/cutlist`, { method: "PATCH", body: JSON.stringify({ cutList }) }),
      prompt: (
        id: string,
        prompt: string,
        init?: RequestInit,
      ): Promise<{ project: Project; diff: unknown[]; explanation: string }> =>
        fetchJSON(`/projects/${id}/prompt`, {
          method: "POST",
          body: JSON.stringify({ prompt }),
          ...init,
        }),
      generate: (
        id: string,
        body: { prompt?: string; options?: Record<string, unknown> } = {},
      ): Promise<{ job: GenerationJob }> =>
        fetchJSON(`/projects/${id}/generate`, { method: "POST", body: JSON.stringify(body) }),
      getGeneration: (id: string): Promise<{ job: GenerationJob }> => fetchJSON(`/projects/${id}/generation`),
      transcribe: (id: string, assetId: string): Promise<{ subtitles: Subtitle[] }> =>
        fetchJSON(`/projects/${id}/transcribe`, { method: "POST", body: JSON.stringify({ assetId }) }),
      getStyle: (id: string): Promise<{ styleAnalysis: Record<string, unknown> | null }> =>
        fetchJSON(`/projects/${id}/style`),
    },
    uploads: {
      presign: (data: {
        projectId: string;
        filename: string;
        mimeType: string;
        type: string;
      }): Promise<{ assetId: string; url: string; fields: Record<string, string>; asset: Asset }> =>
        fetchJSON("/uploads/presigned", { method: "POST", body: JSON.stringify(data) }),
      complete: (assetId: string, data: { sizeBytes: number; etag: string }): Promise<{ asset: Asset }> =>
        fetchJSON(`/uploads/${assetId}/complete`, { method: "POST", body: JSON.stringify(data) }),
      get: (assetId: string): Promise<{ asset: Asset }> => fetchJSON(`/uploads/${assetId}`),
      multipartInit: (data: {
        projectId: string;
        filename: string;
        mimeType: string;
        type: string;
      }): Promise<{ uploadId: string; key: string; assetId: string; asset: Asset }> =>
        fetchJSON("/uploads/multipart/init", { method: "POST", body: JSON.stringify(data) }),
      multipartSignPart: (data: {
        uploadId: string;
        key: string;
        partNumber: number;
      }): Promise<{ url: string }> =>
        fetchJSON("/uploads/multipart/sign-part", { method: "POST", body: JSON.stringify(data) }),
      multipartComplete: (data: {
        uploadId: string;
        key: string;
        parts: Array<{ PartNumber: number; ETag: string }>;
        sizeBytes: number;
      }): Promise<{ asset: Asset }> =>
        fetchJSON("/uploads/multipart/complete", { method: "POST", body: JSON.stringify(data) }),
      multipartAbort: (data: { uploadId: string; key: string }): Promise<{ ok: boolean }> =>
        fetchJSON("/uploads/multipart/abort", { method: "DELETE", body: JSON.stringify(data) }),
    },
    renders: {
      start: (projectId: string, options?: Record<string, unknown>): Promise<{ job: RenderJob }> =>
        fetchJSON("/renders", { method: "POST", body: JSON.stringify({ projectId, options }) }),
      get: (jobId: string): Promise<{ job: RenderJob }> => fetchJSON(`/renders/${jobId}`),
      listByProject: (projectId: string): Promise<{ jobs: RenderJob[] }> =>
        fetchJSON(`/renders/project/${projectId}`),
    },
    segments: {
      start: (data: {
        projectId: string;
        assetId: string;
        prompt: string;
        mode?: "image" | "video";
        frameIndex?: number;
      }): Promise<{ workflowId: string; status: string }> =>
        fetchJSON("/segments", { method: "POST", body: JSON.stringify(data) }),
      get: (workflowId: string): Promise<{ workflowId: string; result: Record<string, unknown> }> =>
        fetchJSON(`/segments/${workflowId}`),
    },
    templates: {
      list: (): Promise<{
        templates: Array<{
          id: string;
          name: string;
          description: string | null;
          tags: string[];
          isPublic: boolean;
          usageCount: number;
          createdAt: string;
        }>;
      }> => fetchJSON("/templates"),
      create: (data: {
        name: string;
        description?: string;
        cutList: unknown;
        tags?: string[];
        isPublic?: boolean;
      }): Promise<{ template: { id: string } }> =>
        fetchJSON("/templates", { method: "POST", body: JSON.stringify(data) }),
      get: (id: string): Promise<{ template: { id: string; name: string; cutList: unknown } }> =>
        fetchJSON(`/templates/${id}`),
      apply: (id: string): Promise<{ cutList: unknown }> =>
        fetchJSON(`/templates/${id}/apply`, { method: "POST" }),
      delete: (id: string): Promise<{ success: boolean }> =>
        fetchJSON(`/templates/${id}`, { method: "DELETE" }),
    },
    presence: {
      report: (
        projectId: string,
        data: { x: number; y: number; name: string },
        init?: RequestInit,
      ): Promise<{ success: boolean }> =>
        fetchJSON(`/presence/${projectId}/presence`, {
          method: "POST",
          body: JSON.stringify(data),
          ...init,
        }),
      get: (
        projectId: string,
      ): Promise<{ users: Array<{ userId: string; name: string; color: string; x: number; y: number }> }> =>
        fetchJSON(`/presence/${projectId}/presence`),
    },
    progress: {
      subscribe: (jobId: string): EventSource => {
        return new EventSource(`${API_BASE}/progress/${jobId}/events`);
      },
    },
    settings: {
      providerKeys: {
        list: (): Promise<{ keys: Array<{ provider: string; masked: string; createdAt: string }> }> =>
          fetchJSON("/settings/provider-keys"),
        save: (data: { provider: string; key: string }): Promise<{ success: boolean }> =>
          fetchJSON("/settings/provider-keys", { method: "POST", body: JSON.stringify(data) }),
        remove: (provider: string): Promise<{ success: boolean }> =>
          fetchJSON(`/settings/provider-keys/${provider}`, { method: "DELETE" }),
        test: (provider: string): Promise<{ success: boolean }> =>
          fetchJSON("/settings/provider-keys/test", { method: "POST", body: JSON.stringify({ provider }) }),
      },
    },
    notifications: {
      list: (): Promise<{
        items: Array<{
          id: string;
          code: string;
          message: string;
          occurrenceCount: number;
          createdAt: string;
        }>;
        nextCursor?: string;
        hasMore: boolean;
      }> => fetchJSON("/notifications"),
      ack: (id: string): Promise<{ ok: boolean }> =>
        fetchJSON(`/notifications/${id}/ack`, { method: "POST" }),
      ackAll: (): Promise<{ ok: boolean }> => fetchJSON("/notifications/ack-all", { method: "POST" }),
    },
    admin: {
      overview: (): Promise<{
        users: { total: number; active24h: number };
        errors: { total: number; last24h: number };
        renders: { total: number; queued: number; running: number };
      }> => fetchJSON("/admin/overview"),
      users: {
        list: (): Promise<{
          items: Array<{ id: string; email: string; name: string | null; createdAt: string }>;
          nextCursor?: string;
          hasMore: boolean;
        }> => fetchJSON("/admin/users"),
        get: (
          userId: string,
        ): Promise<{
          user: { id: string; email: string; name: string | null };
          stats: { errors: number; projects: number; renders: number };
        }> => fetchJSON(`/admin/users/${userId}`),
      },
      errors: (): Promise<{
        items: Array<{ id: string; userId: string; code: string; message: string; createdAt: string }>;
        nextCursor?: string;
        hasMore: boolean;
      }> => fetchJSON("/admin/errors"),
      renders: (): Promise<{
        items: Array<{ id: string; status: string; stage: string; progress: number; createdAt: string }>;
        statusCounts: Array<{ status: string; count: number }>;
      }> => fetchJSON("/admin/renders"),
      audit: (): Promise<{
        items: Array<{
          id: string;
          actorId: string;
          action: string;
          targetType: string | null;
          createdAt: string;
        }>;
        nextCursor?: string;
        hasMore: boolean;
      }> => fetchJSON("/admin/audit"),
    },
  };
}

export type API = ReturnType<typeof createAPI>;
