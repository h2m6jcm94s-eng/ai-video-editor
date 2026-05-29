import "./env";
import { buildApp } from "./app";
import { probeS3Connection } from "./services/storage";
import { probeRedis } from "./services/queue";
import { db } from "./db";
import { sql } from "drizzle-orm";
import { env } from "./env";

async function main() {
  // Startup probes
  try {
    await db.execute(sql`SELECT 1`);
  } catch (e) {
    console.error("Database unreachable — check DATABASE_URL");
    process.exit(1);
  }

  try {
    await probeS3Connection();
  } catch (e) {
    console.error("R2 bucket unreachable — check R2_* env vars");
    process.exit(1);
  }

  try {
    await probeRedis();
  } catch (e) {
    console.error("Redis unreachable — check REDIS_URL");
    process.exit(1);
  }

  const app = await buildApp();
  const port = env.API_PORT;
  await app.listen({ port, host: "0.0.0.0" });
  console.log(`API server running on port ${port}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
