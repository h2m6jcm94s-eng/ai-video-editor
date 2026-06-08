// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import { APIError, type Project, type Asset, type RenderJob, type CutList } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

async function fetchAPI(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Unknown error", code: "UNKNOWN" }));
    throw new APIError(
      err.error || `HTTP ${res.status}`,
      res.status,
      err.code || "UNKNOWN",
      err.details
    );
  }

  return res.json();
}

export const api = {
  projects: {
    list: (): Promise<{ projects: Project[] }> => fetchAPI("/projects"),
    get: (id: string): Promise<{ project: Project & { assets: Asset[] } }> =>
      fetchAPI(`/projects/${id}`),
    create: (data: { name: string; styleTier?: string; mode?: string }): Promise<{ project: Project }> =>
      fetchAPI("/projects", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Project>): Promise<{ project: Project }> =>
      fetchAPI(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
    delete: (id: string): Promise<{ success: boolean }> =>
      fetchAPI(`/projects/${id}`, { method: "DELETE" }),
    updateCutlist: (id: string, cutList: CutList): Promise<{ project: Project }> =>
      fetchAPI(`/projects/${id}/cutlist`, { method: "PATCH", body: JSON.stringify({ cutList }) }),
    prompt: (id: string, prompt: string): Promise<{ project: Project; diff: unknown[]; explanation: string }> =>
      fetchAPI(`/projects/${id}/prompt`, { method: "POST", body: JSON.stringify({ prompt }) }),
    transcribe: (id: string, assetId: string): Promise<{ subtitles: Array<{ id: string; text: string; start_s: number; end_s: number }> }> =>
      fetchAPI(`/projects/${id}/transcribe`, { method: "POST", body: JSON.stringify({ assetId }) }),
  },
  uploads: {
    presign: (data: {
      projectId: string;
      filename: string;
      mimeType: string;
      type: string;
    }): Promise<{ assetId: string; url: string; fields: Record<string, string>; key: string; asset: Asset }> =>
      fetchAPI("/uploads/presigned", { method: "POST", body: JSON.stringify(data) }),
    complete: (assetId: string, data: { sizeBytes: number; etag: string }): Promise<{ asset: Asset }> =>
      fetchAPI(`/uploads/${assetId}/complete`, { method: "POST", body: JSON.stringify(data) }),
  },
  renders: {
    start: (projectId: string, options?: Record<string, unknown>): Promise<{ job: RenderJob }> =>
      fetchAPI("/renders", { method: "POST", body: JSON.stringify({ projectId, options }) }),
    get: (jobId: string): Promise<{ job: RenderJob }> =>
      fetchAPI(`/renders/${jobId}`),
    listByProject: (projectId: string): Promise<{ jobs: RenderJob[] }> =>
      fetchAPI(`/renders/project/${projectId}`),
  },
  templates: {
    list: (): Promise<{ templates: Array<{ id: string; name: string; description: string | null; tags: string[]; isPublic: boolean; usageCount: number; createdAt: string }> }> =>
      fetchAPI("/templates"),
    create: (data: { name: string; description?: string; cutList: unknown; tags?: string[]; isPublic?: boolean }): Promise<{ template: { id: string } }> =>
      fetchAPI("/templates", { method: "POST", body: JSON.stringify(data) }),
    get: (id: string): Promise<{ template: { id: string; name: string; cutList: unknown } }> =>
      fetchAPI(`/templates/${id}`),
    apply: (id: string): Promise<{ cutList: unknown }> =>
      fetchAPI(`/templates/${id}/apply`, { method: "POST" }),
    delete: (id: string): Promise<{ success: boolean }> =>
      fetchAPI(`/templates/${id}`, { method: "DELETE" }),
  },
  presence: {
    report: (projectId: string, data: { x: number; y: number; name: string }): Promise<{ success: boolean }> =>
      fetchAPI(`/presence/${projectId}/presence`, { method: "POST", body: JSON.stringify(data) }),
    get: (projectId: string): Promise<{ users: Array<{ userId: string; name: string; color: string; x: number; y: number }> }> =>
      fetchAPI(`/presence/${projectId}/presence`),
  },
  progress: {
    subscribe: (jobId: string): EventSource => {
      return new EventSource(`${API_BASE}/progress/${jobId}/events`);
    },
  },
};
