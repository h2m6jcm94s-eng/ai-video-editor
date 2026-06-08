import { APIError } from "./error";
import type { Project, Asset, RenderJob, CutList, Subtitle } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000/api";

function sleep(ms: number) {
  return new Promise((res) => setTimeout(res, ms));
}

export type TokenGetter = () => Promise<string | null>;

async function fetchWithRetry(
  path: string,
  init: RequestInit,
  getToken: TokenGetter,
  attempts = 3
): Promise<Response> {
  const url = `${API_BASE}${path}`;

  for (let i = 0; i < attempts; i++) {
    try {
      const token = await getToken();
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
        signal: AbortSignal.timeout(15_000),
      });

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
      get: (id: string): Promise<{ project: Project & { assets: Asset[] } }> =>
        fetchJSON(`/projects/${id}`),
      create: (data: { name: string; styleTier?: string; mode?: string }): Promise<{ project: Project }> =>
        fetchJSON("/projects", { method: "POST", body: JSON.stringify(data) }),
      update: (id: string, data: Partial<Project>): Promise<{ project: Project }> =>
        fetchJSON(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
      delete: (id: string): Promise<{ success: boolean }> =>
        fetchJSON(`/projects/${id}`, { method: "DELETE" }),
      updateCutlist: (id: string, cutList: CutList): Promise<{ project: Project }> =>
        fetchJSON(`/projects/${id}/cutlist`, { method: "PATCH", body: JSON.stringify({ cutList }) }),
      prompt: (id: string, prompt: string): Promise<{ project: Project; diff: unknown[]; explanation: string }> =>
        fetchJSON(`/projects/${id}/prompt`, { method: "POST", body: JSON.stringify({ prompt }) }),
      transcribe: (id: string, assetId: string): Promise<{ subtitles: Subtitle[] }> =>
        fetchJSON(`/projects/${id}/transcribe`, { method: "POST", body: JSON.stringify({ assetId }) }),
    },
    uploads: {
      presign: (data: {
        projectId: string;
        filename: string;
        mimeType: string;
        type: string;
      }): Promise<{ assetId: string; url: string; fields: Record<string, string>; key: string; asset: Asset }> =>
        fetchJSON("/uploads/presigned", { method: "POST", body: JSON.stringify(data) }),
      complete: (assetId: string, data: { sizeBytes: number; etag: string }): Promise<{ asset: Asset }> =>
        fetchJSON(`/uploads/${assetId}/complete`, { method: "POST", body: JSON.stringify(data) }),
    },
    renders: {
      start: (projectId: string, options?: Record<string, unknown>): Promise<{ job: RenderJob }> =>
        fetchJSON("/renders", { method: "POST", body: JSON.stringify({ projectId, options }) }),
      get: (jobId: string): Promise<{ job: RenderJob }> => fetchJSON(`/renders/${jobId}`),
      listByProject: (projectId: string): Promise<{ jobs: RenderJob[] }> =>
        fetchJSON(`/renders/project/${projectId}`),
    },
    templates: {
      list: (): Promise<{ templates: Array<{ id: string; name: string; description: string | null; tags: string[]; isPublic: boolean; usageCount: number; createdAt: string }> }> =>
        fetchJSON("/templates"),
      create: (data: { name: string; description?: string; cutList: unknown; tags?: string[]; isPublic?: boolean }): Promise<{ template: { id: string } }> =>
        fetchJSON("/templates", { method: "POST", body: JSON.stringify(data) }),
      get: (id: string): Promise<{ template: { id: string; name: string; cutList: unknown } }> =>
        fetchJSON(`/templates/${id}`),
      apply: (id: string): Promise<{ cutList: unknown }> =>
        fetchJSON(`/templates/${id}/apply`, { method: "POST" }),
      delete: (id: string): Promise<{ success: boolean }> =>
        fetchJSON(`/templates/${id}`, { method: "DELETE" }),
    },
    presence: {
      report: (projectId: string, data: { x: number; y: number; name: string }): Promise<{ success: boolean }> =>
        fetchJSON(`/presence/${projectId}/presence`, { method: "POST", body: JSON.stringify(data) }),
      get: (projectId: string): Promise<{ users: Array<{ userId: string; name: string; color: string; x: number; y: number }> }> =>
        fetchJSON(`/presence/${projectId}/presence`),
    },
    progress: {
      subscribe: (jobId: string): EventSource => {
        return new EventSource(`${API_BASE}/progress/${jobId}/events`);
      },
    },
  };
}

export type API = ReturnType<typeof createAPI>;
