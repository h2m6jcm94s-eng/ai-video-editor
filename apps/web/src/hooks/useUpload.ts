// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
"use client";

import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/lib/api/client";
import { APIError } from "@/lib/api/error";
import type { Asset, AssetType } from "@/types/api";

interface UploadState {
  uploading: boolean;
  progress: number;
  error: string | null;
}

const ALLOWED_TYPES = [
  "video/mp4",
  "video/quicktime",
  "video/webm",
  "audio/mpeg",
  "audio/wav",
  "audio/aac",
  "audio/ogg",
];

const MULTIPART_THRESHOLD = 100 * 1024 * 1024; // 100MB
const PART_SIZE = 10 * 1024 * 1024; // 10MB parts

export function useUpload(projectId: string) {
  const api = useApi();
  const [state, setState] = useState<UploadState>({
    uploading: false,
    progress: 0,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);
  const multipartRef = useRef<{ uploadId: string; key: string } | null>(null);

  const uploadFile = useCallback(
    async (file: File, type: AssetType): Promise<Asset | null> => {
      if (!ALLOWED_TYPES.includes(file.type)) {
        const msg = `Unsupported file type: ${file.type}. Allowed: MP4, MOV, WEBM, MP3, WAV, AAC, OGG.`;
        setState({ uploading: false, progress: 0, error: msg });
        toast.error(msg);
        return null;
      }

      setState({ uploading: true, progress: 0, error: null });
      abortRef.current = new AbortController();

      try {
        let asset: Asset;

        if (file.size > MULTIPART_THRESHOLD) {
          asset = await uploadMultipart(file, projectId, type, api, setState, abortRef.current.signal);
        } else {
          asset = await uploadSimple(file, projectId, type, api, setState, abortRef.current.signal);
        }

        setState({ uploading: false, progress: 100, error: null });
        return asset;
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setState({ uploading: false, progress: 0, error: "Upload cancelled" });
          return null;
        }
        const message =
          err instanceof APIError ? err.userMessage : err instanceof Error ? err.message : "Upload failed";
        setState({ uploading: false, progress: 0, error: message });
        toast.error(message);
        return null;
      }
    },
    [projectId, api],
  );

  const cancelUpload = useCallback(async () => {
    abortRef.current?.abort();
    const mp = multipartRef.current;
    if (mp) {
      try {
        await api.uploads.multipartAbort(mp);
        toast.info("Upload cancelled — multipart aborted");
      } catch {
        toast.info("Upload cancelled");
      }
    }
    setState({ uploading: false, progress: 0, error: "Upload cancelled" });
  }, [api]);

  return { ...state, uploadFile, cancelUpload };
}

async function uploadSimple(
  file: File,
  projectId: string,
  type: AssetType,
  api: ReturnType<typeof useApi>,
  setState: (s: UploadState) => void,
  signal: AbortSignal,
): Promise<Asset> {
  const presign = await api.uploads.presign({
    projectId,
    filename: file.name,
    mimeType: file.type,
    type,
  });

  const { etag } = await uploadWithProgress(presign.url, file, presign.fields, signal, (pct) =>
    setState({ uploading: true, progress: pct, error: null }),
  );

  const complete = await api.uploads.complete(presign.assetId, {
    sizeBytes: file.size,
    etag,
  });

  return complete.asset;
}

async function uploadMultipart(
  file: File,
  projectId: string,
  type: AssetType,
  api: ReturnType<typeof useApi>,
  setState: (s: UploadState) => void,
  signal: AbortSignal,
): Promise<Asset> {
  const init = await api.uploads.multipartInit({
    projectId,
    filename: file.name,
    mimeType: file.type,
    type,
  });

  const totalParts = Math.ceil(file.size / PART_SIZE);
  const parts: Array<{ PartNumber: number; ETag: string }> = [];

  for (let i = 1; i <= totalParts; i++) {
    if (signal.aborted) throw new DOMException("Upload aborted", "AbortError");

    const start = (i - 1) * PART_SIZE;
    const end = Math.min(i * PART_SIZE, file.size);
    const chunk = file.slice(start, end);

    const { url } = await api.uploads.multipartSignPart({
      uploadId: init.uploadId,
      key: init.key,
      partNumber: i,
    });

    const etag = await uploadPartWithProgress(url, chunk, signal, (pct) => {
      const overall = Math.round(((i - 1 + pct / 100) / totalParts) * 100);
      setState({ uploading: true, progress: overall, error: null });
    });

    parts.push({ PartNumber: i, ETag: etag });
  }

  const complete = await api.uploads.multipartComplete({
    uploadId: init.uploadId,
    key: init.key,
    parts,
    sizeBytes: file.size,
  });

  return complete.asset;
}

function uploadWithProgress(
  url: string,
  file: File,
  fields: Record<string, string>,
  signal: AbortSignal,
  onProgress: (pct: number) => void,
): Promise<{ etag: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader("etag") || xhr.getResponseHeader("ETag") || "";
        resolve({ etag });
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Upload failed: network error")));
    xhr.addEventListener("abort", () => reject(new DOMException("Upload aborted", "AbortError")));

    signal.addEventListener("abort", () => xhr.abort());

    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.send(file);
  });
}

function uploadPartWithProgress(
  url: string,
  chunk: Blob,
  signal: AbortSignal,
  onProgress: (pct: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const etag = xhr.getResponseHeader("etag") || xhr.getResponseHeader("ETag") || "";
        resolve(etag);
      } else {
        reject(new Error(`Part upload failed: ${xhr.status} ${xhr.statusText}`));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Part upload failed: network error")));
    xhr.addEventListener("abort", () => reject(new DOMException("Upload aborted", "AbortError")));

    signal.addEventListener("abort", () => xhr.abort());

    xhr.open("PUT", url);
    xhr.send(chunk);
  });
}
