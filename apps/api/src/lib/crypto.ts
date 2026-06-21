// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * AES-256-GCM encryption for provider API keys with KEK versioning support.
 *
 * Format (legacy): base64(iv(12) + authTag(16) + ciphertext)
 * Format (versioned): v{N}:base64(iv + authTag + ciphertext)
 *
 * The active KEK version is read from PROVIDER_KEK_VERSION (default "v1").
 * Decryption uses the version embedded in the payload, so existing keys keep
 * working after a rotation. Rotated KEKs can be supplied via PROVIDER_KEK_V2,
 * PROVIDER_KEK_V3, etc.
 */

import "../env";
import { createCipheriv, createDecipheriv, createHmac, randomBytes, timingSafeEqual } from "crypto";

const KEK_HEX = process.env.PROVIDER_KEK;
const KEK_VERSION = process.env.PROVIDER_KEK_VERSION || "v1";
const INTERNAL_TOKEN = process.env.INTERNAL_WORKER_TOKEN || "";

function getKek(version: string): Buffer {
  const envKey = version === "v1" ? KEK_HEX : process.env[`PROVIDER_KEK_${version.toUpperCase()}`];
  if (!envKey) {
    throw new Error(`PROVIDER_KEK${version === "v1" ? "" : `_${version.toUpperCase()}`} is not set`);
  }
  const key = Buffer.from(envKey, "hex");
  if (key.length !== 32) {
    throw new Error(`KEK for ${version} must be exactly 32 bytes (64 hex chars), got ${key.length} bytes`);
  }
  return key;
}

const IV_LENGTH = 12;
const AUTH_TAG_LENGTH = 16;
const ALGORITHM = "aes-256-gcm";

/**
 * Encrypt plaintext using AES-256-GCM with the active KEK version.
 * Returns v{N}:base64(iv + authTag + ciphertext).
 */
export function encrypt(plaintext: string): string {
  const key = getKek(KEK_VERSION);
  const iv = randomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGORITHM, key, iv);

  const encrypted = Buffer.concat([cipher.update(plaintext, "utf-8"), cipher.final()]);
  const authTag = cipher.getAuthTag();

  // iv(12) + authTag(16) + ciphertext
  const combined = Buffer.concat([iv, authTag, encrypted]);
  return `${KEK_VERSION}:${combined.toString("base64")}`;
}

/**
 * Decrypt ciphertext using AES-256-GCM.
 * Accepts both legacy base64(iv + authTag + ciphertext) and versioned
 * v{N}:base64(...) formats.
 */
export function decrypt(cipherbase64: string): string {
  const versionMatch = cipherbase64.match(/^(v\d+):(.+)$/);
  const version = versionMatch ? versionMatch[1] : "v1";
  const payload = versionMatch ? versionMatch[2] : cipherbase64;

  const key = getKek(version);
  const combined = Buffer.from(payload, "base64");

  if (combined.length < IV_LENGTH + AUTH_TAG_LENGTH) {
    throw new Error("Invalid ciphertext: too short");
  }

  const iv = combined.subarray(0, IV_LENGTH);
  const authTag = combined.subarray(IV_LENGTH, IV_LENGTH + AUTH_TAG_LENGTH);
  const ciphertext = combined.subarray(IV_LENGTH + AUTH_TAG_LENGTH);

  const decipher = createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(authTag);

  const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return decrypted.toString("utf-8");
}

/**
 * Create a render-scoped completion token used by the worker webhook.
 * The token is an HMAC over the render and project IDs signed with the
 * internal worker token so a leaked global token cannot mutate arbitrary jobs.
 */
export function createCompletionToken(renderId: string, projectId: string): string {
  if (!INTERNAL_TOKEN) {
    throw new Error("INTERNAL_WORKER_TOKEN is not set — required for render completion tokens");
  }
  return createHmac("sha256", INTERNAL_TOKEN).update(`${renderId}:${projectId}`).digest("base64url");
}

/**
 * Verify a render-scoped completion token in constant time.
 */
export function verifyCompletionToken(token: string, renderId: string, projectId: string): boolean {
  if (!INTERNAL_TOKEN) return false;
  try {
    const expected = createCompletionToken(renderId, projectId);
    const a = Buffer.from(token, "base64url");
    const b = Buffer.from(expected, "base64url");
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}
