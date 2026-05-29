"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileVideo, FileAudio, Check, Loader2, AlertCircle } from "lucide-react";

interface UploadZoneProps {
  projectId: string;
  type: string;
  label: string;
  accept: string;
  multiple?: boolean;
}

export function UploadZone({ projectId, type, label, accept, multiple }: UploadZoneProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setFiles((prev) => (multiple ? [...prev, ...acceptedFiles] : acceptedFiles));
      setUploading(true);
      setError(null);

      for (let i = 0; i < acceptedFiles.length; i++) {
        const file = acceptedFiles[i];
        try {
          // Get presigned URL
          const presignRes = await fetch("/api/uploads/presigned", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              projectId,
              filename: file.name,
              mimeType: file.type,
              type,
            }),
          });
          if (!presignRes.ok) {
            throw new Error(`Presign failed: ${presignRes.statusText}`);
          }
          const { url, assetId } = await presignRes.json();

          // Upload to R2
          const uploadRes = await fetch(url, {
            method: "PUT",
            body: file,
            headers: { "Content-Type": file.type },
          });
          if (!uploadRes.ok) {
            throw new Error(`R2 upload failed: ${uploadRes.statusText}`);
          }

          const etag = uploadRes.headers.get("ETag") ?? "";

          // Mark complete
          const completeRes = await fetch(`/api/uploads/${assetId}/complete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sizeBytes: file.size, etag }),
          });
          if (!completeRes.ok) {
            throw new Error(`Complete failed: ${completeRes.statusText}`);
          }

          setProgress(Math.round(((i + 1) / acceptedFiles.length) * 100));
        } catch (err: any) {
          setError(err.message || "Upload failed");
          setUploading(false);
          return;
        }
      }

      setUploading(false);
    },
    [projectId, type, multiple]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { [accept]: [] },
    multiple,
  });

  const Icon = type === "song" ? FileAudio : FileVideo;

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-4 cursor-pointer transition ${
          isDragActive
            ? "border-indigo-500 bg-indigo-50"
            : "border-slate-300 hover:border-slate-400"
        }`}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center justify-center space-y-2 text-slate-500">
          {uploading ? (
            <>
              <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
              <span className="text-sm">Uploading... {progress}%</span>
            </>
          ) : files.length > 0 ? (
            <>
              <Check className="w-8 h-8 text-green-500" />
              <span className="text-sm text-slate-700">
                {files.length} file{files.length > 1 ? "s" : ""} ready
              </span>
            </>
          ) : (
            <>
              <Upload className="w-8 h-8" />
              <span className="text-sm">
                Drop {multiple ? "files" : "a file"} here, or click to select
              </span>
            </>
          )}
        </div>
      </div>
      {error && (
        <div className="flex items-center space-x-2 text-sm text-red-600">
          <AlertCircle className="w-4 h-4" />
          <span>{error}</span>
        </div>
      )}
      {files.length > 0 && (
        <div className="space-y-1">
          {files.map((f, i) => (
            <div key={i} className="flex items-center space-x-2 text-sm text-slate-600">
              <Icon className="w-4 h-4" />
              <span className="truncate">{f.name}</span>
              <span className="text-slate-400">
                ({(f.size / 1024 / 1024).toFixed(1)} MB)
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
