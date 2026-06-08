// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { Asset } from "@/types/api";

interface UploadState {
  uploading: boolean;
  progress: number;
  error: string | null;
}

export function useUpload(projectId: string) {
  const [state, setState] = useState<UploadState>({
    uploading: false,
    progress: 0,
    error: null,
  });

  const uploadFile = useCallback(
    async (file: File, type: "reference" | "song" | "clip"): Promise<Asset | null> => {
      setState({ uploading: true, progress: 0, error: null });
      try {
        const presign = await api.uploads.presign({
          projectId,
          filename: file.name,
          mimeType: file.type,
          type,
        });

        const formData = new FormData();
        Object.entries(presign.fields).forEach(([k, v]) => formData.append(k, v));
        formData.append("file", file);

        await fetch(presign.url, {
          method: "POST",
          body: formData,
        });

        const complete = await api.uploads.complete(presign.assetId, {
          sizeBytes: file.size,
          etag: "", // R2/Minio may not require this
        });

        setState({ uploading: false, progress: 100, error: null });
        return complete.asset;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setState({ uploading: false, progress: 0, error: message });
        return null;
      }
    },
    [projectId]
  );

  return { ...state, uploadFile };
}
