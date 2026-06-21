// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import {
  type _Object,
  AbortMultipartUploadCommand,
  type CompletedPart,
  CompleteMultipartUploadCommand,
  CreateMultipartUploadCommand,
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  HeadObjectCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
  UploadPartCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import fs from "fs";
import path from "path";
import { logger } from "../lib/logger";

const endpoint = process.env.R2_ENDPOINT || "";
const isLocal =
  endpoint.includes("localhost") ||
  endpoint.includes("127.0.0.1") ||
  endpoint.includes("minio") ||
  endpoint.includes(":9000");

export const s3 = new S3Client({
  region: "auto",
  endpoint: endpoint || undefined,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID || "",
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY || "",
  },
  forcePathStyle: isLocal,
  requestHandler: {
    requestTimeout: 30_000,
    connectionTimeout: 5_000,
  },
});

export const BUCKET = process.env.R2_BUCKET_NAME || "ai-video-editor";

export async function createPresignedUploadUrl(key: string, contentType: string, expiresIn = 900) {
  const command = new PutObjectCommand({
    Bucket: BUCKET,
    Key: key,
    ContentType: contentType,
  });

  const url = await getSignedUrl(s3, command, { expiresIn });
  return { url, fields: {} };
}

export async function createPresignedDownloadUrl(key: string, expiresIn = 3600) {
  const command = new GetObjectCommand({
    Bucket: BUCKET,
    Key: key,
  });

  return getSignedUrl(s3, command, { expiresIn });
}

export async function downloadAsset(storageKey: string, localPath: string): Promise<string> {
  const command = new GetObjectCommand({
    Bucket: BUCKET,
    Key: storageKey,
  });

  const response = await s3.send(command);
  if (!response.Body) {
    throw new Error(`Empty response body for ${storageKey}`);
  }

  const dir = path.dirname(localPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const stream = response.Body as NodeJS.ReadableStream;
  const writeStream = fs.createWriteStream(localPath);

  return new Promise((resolve, reject) => {
    stream.pipe(writeStream);
    writeStream.on("finish", () => resolve(localPath));
    writeStream.on("error", reject);
  });
}

export async function deleteAsset(storageKey: string): Promise<void> {
  const command = new DeleteObjectCommand({
    Bucket: BUCKET,
    Key: storageKey,
  });
  await s3.send(command);
}

export async function listProjectAssets(projectId: string): Promise<string[]> {
  const prefix = `projects/${projectId}/`;
  let continuationToken: string | undefined;
  const keys: string[] = [];
  do {
    const command = new ListObjectsV2Command({
      Bucket: BUCKET,
      Prefix: prefix,
      ContinuationToken: continuationToken,
    });
    const response = await s3.send(command);
    keys.push(...(response.Contents?.map((obj: _Object) => obj.Key || "") ?? []));
    continuationToken = response.NextContinuationToken;
  } while (continuationToken);
  return keys;
}

export async function deleteProjectAssets(projectId: string): Promise<void> {
  const keys = await listProjectAssets(projectId);
  const results = await Promise.allSettled(keys.map((k) => deleteAsset(k)));
  const failures = results.filter((r) => r.status === "rejected") as PromiseRejectedResult[];
  if (failures.length) {
    logger.error({ failures: failures.map((f) => f.reason) }, "Some assets failed to delete");
    throw new Error(`Failed to delete ${failures.length} asset(s) from storage for project ${projectId}`);
  }
}

export async function probeS3Connection(): Promise<void> {
  const command = new HeadBucketCommand({ Bucket: BUCKET });
  await s3.send(command);
}

// ── Multipart Upload Helpers ────────────────────────────────────────────────

export async function createMultipartUpload(key: string, contentType: string) {
  const r = await s3.send(
    new CreateMultipartUploadCommand({
      Bucket: BUCKET,
      Key: key,
      ContentType: contentType,
    }),
  );
  if (!r.UploadId) throw new Error("R2 did not return UploadId");
  return r.UploadId;
}

export async function presignUploadPart(key: string, uploadId: string, partNumber: number, expiresIn = 900) {
  const cmd = new UploadPartCommand({
    Bucket: BUCKET,
    Key: key,
    UploadId: uploadId,
    PartNumber: partNumber,
  });
  return getSignedUrl(s3, cmd, { expiresIn });
}

export async function completeMultipartUpload(key: string, uploadId: string, parts: CompletedPart[]) {
  return s3.send(
    new CompleteMultipartUploadCommand({
      Bucket: BUCKET,
      Key: key,
      UploadId: uploadId,
      MultipartUpload: {
        Parts: parts.sort((a, b) => (a.PartNumber ?? 0) - (b.PartNumber ?? 0)),
      },
    }),
  );
}

export async function abortMultipartUpload(key: string, uploadId: string) {
  return s3.send(
    new AbortMultipartUploadCommand({
      Bucket: BUCKET,
      Key: key,
      UploadId: uploadId,
    }),
  );
}

export async function headObject(key: string) {
  return s3.send(
    new HeadObjectCommand({
      Bucket: BUCKET,
      Key: key,
    }),
  );
}
