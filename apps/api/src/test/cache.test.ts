import { beforeEach, describe, expect, it, vi } from "vitest";
import { cacheDel, cacheGet, cacheInvalidatePattern, cacheSet } from "../lib/cache";
import { redis } from "../lib/redis";

function makeStream(keys: string[]) {
  const stream = {
    on: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
      if (event === "data") {
        handler(keys);
      } else if (event === "end") {
        handler();
      }
    }),
  };
  return stream as unknown as ReturnType<typeof redis.scanStream>;
}

describe("Cache Helpers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("cacheGet returns parsed value when key exists", async () => {
    vi.mocked(redis.get).mockResolvedValueOnce(JSON.stringify({ data: "hello" }));
    const result = await cacheGet("my:key");
    expect(result).toEqual({ data: "hello" });
  });

  it("cacheGet returns null when key not found", async () => {
    vi.mocked(redis.get).mockResolvedValueOnce(null);
    const result = await cacheGet("my:key");
    expect(result).toBeNull();
  });

  it("cacheGet returns null when JSON.parse throws", async () => {
    vi.mocked(redis.get).mockResolvedValueOnce("not valid json");
    const result = await cacheGet("my:key");
    expect(result).toBeNull();
  });

  it("cacheSet stores serialized value with TTL", async () => {
    vi.mocked(redis.setex).mockResolvedValueOnce("OK");
    await cacheSet("my:key", { foo: "bar" }, 60);
    expect(redis.setex).toHaveBeenCalledWith("my:key", 60, JSON.stringify({ foo: "bar" }));
  });

  it("cacheSet uses default TTL when not specified", async () => {
    vi.mocked(redis.setex).mockResolvedValueOnce("OK");
    await cacheSet("my:key", "value");
    expect(redis.setex).toHaveBeenCalledWith("my:key", 30, JSON.stringify("value"));
  });

  it("cacheDel removes key", async () => {
    vi.mocked(redis.del).mockResolvedValueOnce(1);
    await cacheDel("my:key");
    expect(redis.del).toHaveBeenCalledWith("my:key");
  });

  it("cacheInvalidatePattern deletes matching keys via SCAN stream", async () => {
    vi.mocked(redis.scanStream).mockReturnValueOnce(makeStream(["a:1", "a:2"]));
    vi.mocked(redis.del).mockResolvedValueOnce(2);
    await cacheInvalidatePattern("a:*");
    expect(redis.scanStream).toHaveBeenCalledWith({ match: "a:*", count: 100 });
    expect(redis.del).toHaveBeenCalledWith("a:1", "a:2");
  });

  it("cacheInvalidatePattern does nothing when no keys match", async () => {
    vi.mocked(redis.scanStream).mockReturnValueOnce(makeStream([]));
    await cacheInvalidatePattern("b:*");
    expect(redis.scanStream).toHaveBeenCalledWith({ match: "b:*", count: 100 });
    expect(redis.del).not.toHaveBeenCalled();
  });

  it("cacheInvalidatePattern rejects when the SCAN stream errors", async () => {
    const error = new Error("Redis scan failed");
    vi.mocked(redis.scanStream).mockReturnValueOnce({
      on: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
        if (event === "error") {
          handler(error);
        }
      }),
    } as unknown as ReturnType<typeof redis.scanStream>);

    await expect(cacheInvalidatePattern("c:*")).rejects.toThrow("Redis scan failed");
  });
});
