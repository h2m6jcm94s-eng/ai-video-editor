import { vi } from "vitest";

// Mock Clerk
vi.mock("@clerk/fastify", () => ({
  createClerkClient: () => ({
    authenticateRequest: vi.fn(async () => ({
      isSignedIn: true,
      toAuth: () => ({ userId: "test-user-id", sessionId: "test-session" }),
    })),
  }),
  clerkClient: {
    users: {
      getUser: vi.fn(async (userId: string) => ({
        id: userId,
        emailAddresses: [{ emailAddress: "test@test.com" }],
        fullName: "Test User",
      })),
    },
  },
}));

// Mock user sync so auth middleware resolves to a local UUID without hitting DB
vi.mock("../services/users", () => ({
  getUserByClerkId: vi.fn(async () => ({
    id: "test-user-id",
    clerkId: "test-user-id",
    email: "test@test.com",
    name: "Test User",
  })),
  upsertUser: vi.fn(async (clerkId: string, email: string, name: string) => ({
    id: clerkId,
    clerkId,
    email,
    name,
  })),
}));

// Mock DB
const createChainableInsert = () =>
  vi.fn().mockReturnValue({
    values: vi.fn().mockReturnValue({
      returning: vi.fn().mockResolvedValue([]),
    }),
  });

const createChainableUpdate = () =>
  vi.fn().mockReturnValue({
    set: vi.fn().mockReturnValue({
      where: vi.fn().mockReturnValue({
        returning: vi.fn().mockResolvedValue([]),
      }),
    }),
  });

const createChainableDelete = () =>
  vi.fn().mockReturnValue({
    where: vi.fn().mockResolvedValue(undefined),
  });

vi.mock("../db", () => ({
  db: {
    query: {
      projects: { findFirst: vi.fn(), findMany: vi.fn() },
      assets: { findFirst: vi.fn(), findMany: vi.fn() },
      renders: { findFirst: vi.fn(), findMany: vi.fn() },
      templates: { findFirst: vi.fn(), findMany: vi.fn() },
      providerKeys: { findFirst: vi.fn().mockResolvedValue(null) },
    },
    insert: createChainableInsert(),
    update: createChainableUpdate(),
    delete: createChainableDelete(),
    execute: vi.fn().mockResolvedValue([]),
  },
}));

// Mock Storage
vi.mock("../services/storage", () => ({
  createPresignedUploadUrl: vi.fn(async () => ({ url: "https://r2.example.com/upload", fields: {} })),
  createPresignedDownloadUrl: vi.fn(async () => "https://r2.example.com/download"),
  downloadAsset: vi.fn(async () => "/tmp/test.mp3"),
  deleteProjectAssets: vi.fn(async () => {}),
  probeS3Connection: vi.fn(async () => {}),
}));

// Mock fs
vi.mock("fs", () => ({
  default: {
    readFileSync: vi.fn(() => Buffer.from("fake-audio")),
    unlinkSync: vi.fn(),
    existsSync: vi.fn(() => true),
    mkdirSync: vi.fn(),
    createWriteStream: vi.fn(() => ({ pipe: vi.fn(), on: vi.fn() })),
  },
}));

// Mock os
vi.mock("os", () => ({
  default: {
    tmpdir: vi.fn(() => "/tmp"),
  },
}));

// Mock ioredis before queue/progress import it
vi.mock("ioredis", () => ({
  default: class MockRedis {
    on = vi.fn();
    subscribe = vi.fn().mockResolvedValue(undefined);
    unsubscribe = vi.fn().mockResolvedValue(undefined);
    quit = vi.fn().mockResolvedValue(undefined);
    ping = vi.fn().mockResolvedValue("PONG");
    zadd = vi.fn().mockResolvedValue(1);
    zpopmin = vi.fn().mockResolvedValue([]);
    publish = vi.fn().mockResolvedValue(1);
    get = vi.fn().mockResolvedValue(null);
    setex = vi.fn().mockResolvedValue("OK");
    del = vi.fn().mockResolvedValue(1);
    keys = vi.fn().mockResolvedValue([]);
  },
}));

// Mock Queue
vi.mock("../services/queue", () => ({
  enqueueJob: vi.fn(async () => {}),
  probeRedis: vi.fn(async () => {}),
}));

// Mock Temporal
vi.mock("../services/temporal", () => ({
  startRenderWorkflow: vi.fn(async () => "wf-test-123"),
  sendCutlistApprovedSignal: vi.fn(async () => {}),
}));
