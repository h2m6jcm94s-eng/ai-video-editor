import { beforeEach, describe, expect, it, vi } from "vitest";

const mockSend = vi.fn();
const mockGetSignedUrl = vi.fn();

vi.mock("@aws-sdk/client-s3", () => ({
  S3Client: vi.fn().mockImplementation(function () {
    return { send: mockSend };
  }),
  PutObjectCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  GetObjectCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  DeleteObjectCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  ListObjectsV2Command: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  HeadBucketCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  HeadObjectCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  CreateMultipartUploadCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  UploadPartCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  CompleteMultipartUploadCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
  AbortMultipartUploadCommand: vi.fn(function (this: any, input: any) {
    this.input = input;
  }),
}));

vi.mock("@aws-sdk/s3-request-presigner", () => ({
  getSignedUrl: mockGetSignedUrl,
}));

vi.mock("fs", () => ({
  default: {
    existsSync: vi.fn(() => true),
    mkdirSync: vi.fn(),
    createWriteStream: vi.fn(() => ({ pipe: vi.fn(), on: vi.fn() })),
  },
}));

// Unmock storage so we get the real module with mocked SDK underneath
vi.doUnmock("../services/storage");

describe("Storage service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSend.mockReset();
    mockGetSignedUrl.mockReset();
  });

  describe("Multipart helpers", () => {
    it("createMultipartUpload returns UploadId from R2", async () => {
      const { createMultipartUpload } = await import("../services/storage");
      mockSend.mockResolvedValueOnce({ UploadId: "test-upload-id" });

      const id = await createMultipartUpload("key", "video/mp4");
      expect(id).toBe("test-upload-id");
    });

    it("createMultipartUpload throws when UploadId is missing", async () => {
      const { createMultipartUpload } = await import("../services/storage");
      mockSend.mockResolvedValueOnce({ UploadId: undefined });

      await expect(createMultipartUpload("key", "video/mp4")).rejects.toThrow("R2 did not return UploadId");
    });

    it("presignUploadPart returns a signed URL", async () => {
      const { presignUploadPart } = await import("../services/storage");
      mockGetSignedUrl.mockResolvedValueOnce("https://r2.example.com/part-url");

      const url = await presignUploadPart("key", "upload-id", 1);
      expect(url).toBe("https://r2.example.com/part-url");
    });

    it("completeMultipartUpload sorts parts by PartNumber before sending", async () => {
      const { completeMultipartUpload } = await import("../services/storage");
      mockSend.mockResolvedValueOnce({});

      const parts = [
        { PartNumber: 3, ETag: '"etag3"' },
        { PartNumber: 1, ETag: '"etag1"' },
        { PartNumber: 2, ETag: '"etag2"' },
      ];

      await completeMultipartUpload("key", "upload-id", parts);
      const call = mockSend.mock.calls[0][0];
      expect(call.input.MultipartUpload.Parts).toEqual([
        { PartNumber: 1, ETag: '"etag1"' },
        { PartNumber: 2, ETag: '"etag2"' },
        { PartNumber: 3, ETag: '"etag3"' },
      ]);
    });

    it("abortMultipartUpload sends AbortMultipartUploadCommand", async () => {
      const { abortMultipartUpload } = await import("../services/storage");
      mockSend.mockResolvedValueOnce({});

      await abortMultipartUpload("key", "upload-id");
      expect(mockSend).toHaveBeenCalledTimes(1);
      const call = mockSend.mock.calls[0][0];
      expect(call.input).toMatchObject({ Bucket: expect.any(String), Key: "key", UploadId: "upload-id" });
    });

    it("headObject sends HeadObjectCommand", async () => {
      const { headObject } = await import("../services/storage");
      mockSend.mockResolvedValueOnce({ ETag: '"abc"', ContentLength: 1024 });

      const result = await headObject("key");
      expect(result.ETag).toBe('"abc"');
      expect(result.ContentLength).toBe(1024);
    });
  });
});
