// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import { APIError, type Project, type Asset, type RenderJob } from "@/types/api";

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
    updateCutlist: (id: string, cutList: unknown): Promise<{ project: Project }> =>
      fetchAPI(`/projects/${id}/cutlist`, { method: "PATCH", body: JSON.stringify({ cutList }) }),
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
  progress: {
    subscribe: (jobId: string): EventSource => {
      return new EventSource(`${API_BASE}/progress/${jobId}/events`);
    },
  },
};
