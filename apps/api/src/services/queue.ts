import Redis from "ioredis";

const redis = new Redis(process.env.REDIS_URL || "redis://localhost:6379");

export interface JobMessage {
  jobId: string;
  projectId: string;
  type: string;
  payload: Record<string, unknown>;
  priority: number;
  createdAt: string;
}

export async function enqueueJob(message: JobMessage): Promise<void> {
  // Use a scored set for priority instead of a simple list
  const score = message.priority || 1;
  await redis.zadd("ave:jobs:queue", score, JSON.stringify(message));
}

export async function dequeueJob(): Promise<JobMessage | null> {
  const data = await redis.zpopmin("ave:jobs:queue");
  if (!data || data.length === 0) return null;
  try {
    return JSON.parse(data[1]);
  } catch (e) {
    console.error("Failed to parse job from queue:", data[1]);
    return null;
  }
}

export async function publishProgress(
  jobId: string,
  stage: string,
  progress: number,
  message: string
): Promise<void> {
  await redis.publish(
    `job:${jobId}`,
    JSON.stringify({ jobId, stage, progress, message, timestamp: new Date().toISOString() })
  );
}

export async function getJobStatus(jobId: string): Promise<{
  stage: string;
  progress: number;
  message: string;
}> {
  const data = await redis.get(`ave:job:${jobId}:status`);
  if (!data) return { stage: "unknown", progress: 0, message: "" };
  try {
    return JSON.parse(data);
  } catch {
    return { stage: "unknown", progress: 0, message: "" };
  }
}

export async function setJobStatus(
  jobId: string,
  stage: string,
  progress: number,
  message: string
): Promise<void> {
  await redis.setex(
    `ave:job:${jobId}:status`,
    86400, // 24 hours
    JSON.stringify({ stage, progress, message, updatedAt: new Date().toISOString() })
  );
}

export async function probeRedis(): Promise<void> {
  await redis.ping();
}
