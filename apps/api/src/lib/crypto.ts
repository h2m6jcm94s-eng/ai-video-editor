// Copyright (c) 2025 Devayan Dewri. All rights reserved.
// Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
/**
 * AES-256-GCM encryption for provider API keys.
 *
 * Format: base64(iv(12) + authTag(16) + ciphertext)
 * Key must be 32 bytes (256 bits) — hex-encoded in PROVIDER_KEK env var.
 */

import { createCipheriv, createDecipheriv, randomBytes } from "crypto";

const KEK_HEX = process.env.PROVIDER_KEK;

function getKey(): Buffer {
  if (!KEK_HEX) {
    throw new Error("PROVIDER_KEK is not set — required for AES-256-GCM encryption");
  }
  const key = Buffer.from(KEK_HEX, "hex");
  if (key.length !== 32) {
    throw new Error(`PROVIDER_KEK must be exactly 32 bytes (64 hex chars), got ${key.length} bytes`);
  }
  return key;
}

const IV_LENGTH = 12;
const AUTH_TAG_LENGTH = 16;
const ALGORITHM = "aes-256-gcm";

/**
 * Encrypt plaintext using AES-256-GCM.
 * Returns base64(iv + authTag + ciphertext).
 */
export function encrypt(plaintext: string): string {
  const key = getKey();
  const iv = randomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGORITHM, key, iv);

  const encrypted = Buffer.concat([cipher.update(plaintext, "utf-8"), cipher.final()]);
  const authTag = cipher.getAuthTag();

  // iv(12) + authTag(16) + ciphertext
  const combined = Buffer.concat([iv, authTag, encrypted]);
  return combined.toString("base64");
}

/**
 * Decrypt ciphertext using AES-256-GCM.
 * Expects base64(iv + authTag + ciphertext).
 */
export function decrypt(cipherbase64: string): string {
  const key = getKey();
  const combined = Buffer.from(cipherbase64, "base64");

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
