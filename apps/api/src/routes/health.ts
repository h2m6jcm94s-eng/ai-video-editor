import { FastifyInstance } from "fastify";
import { sql } from "drizzle-orm";
import { db } from "../db";

export async function healthRoutes(app: FastifyInstance) {
  app.get("/", async () => {
    return { status: "ok", timestamp: new Date().toISOString() };
  });

  app.get("/db", async (request, reply) => {
    try {
      await db.execute(sql`SELECT 1`);
      return { status: "ok", db: "connected" };
    } catch (e: any) {
      return reply.status(503).send({ status: "error", db: "disconnected", error: e.message });
    }
  });
}
