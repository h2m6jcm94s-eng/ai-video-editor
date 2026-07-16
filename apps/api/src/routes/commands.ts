import type { CutList } from "@ai-video-editor/shared-types";
import { eq } from "drizzle-orm";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { db } from "../db";
import { assets, cutlistEdits, projects } from "../db/schema";
import { computeBehaviorDeltas } from "../lib/attribution";
import { cacheDel } from "../lib/cache";
import { parseCommand } from "../lib/commandParser";
import { buildInitialCutList } from "../lib/cutlist";
import { sendError } from "../lib/errors";
import { incrementTokenUsage } from "../middleware/tokenBudget";
import { validateBody } from "../middleware/validate";
import { applyPromptEdit } from "../services/ai";
import { applyCommand } from "../services/commandEdit";

const commandRequestSchema = z
  .object({
    prompt: z.string().min(1).max(2000),
    contextSlotIndex: z.number().int().nonnegative().optional(),
  })
  .strict();

const parseOnlySchema = z
  .object({
    prompt: z.string().min(1).max(2000),
  })
  .strict();

export async function commandRoutes(app: FastifyInstance) {
  app.post(
    "/projects/:id/commands",
    { preHandler: validateBody(commandRequestSchema) },
    async (request, reply) => {
      const { id } = request.params as { id: string };
      const userId = request.userId;
      if (!userId) {
        return sendError(reply, 401, "Unauthorized", "UNAUTHORIZED");
      }

      const project = await db.query.projects.findFirst({
        where: eq(projects.id, id),
      });
      if (!project) {
        return sendError(reply, 404, "Not found", "NOT_FOUND");
      }
      if (project.userId !== userId) {
        return sendError(reply, 403, "Forbidden", "FORBIDDEN");
      }

      const body = request.validatedBody as {
        prompt: string;
        contextSlotIndex?: number;
      };

      const projectAssets = await db.query.assets.findMany({
        where: eq(assets.projectId, id),
      });

      let currentCutList = project.cutList as CutList | null;
      if (!currentCutList) {
        currentCutList = buildInitialCutList(projectAssets || []);
        await db
          .update(projects)
          .set({ cutList: currentCutList, updatedAt: new Date() })
          .where(eq(projects.id, id));
      }

      const command = parseCommand(body.prompt, currentCutList);
      let result;
      let source: "deterministic_verb" | "llm_fallback";

      if (command && command.confidence >= 0.7) {
        result = applyCommand(command, currentCutList);
        source = "deterministic_verb";
      } else {
        const llmResult = await applyPromptEdit({
          userId,
          prompt: body.prompt,
          cutList: currentCutList,
          assets: (projectAssets || []).map((a) => ({
            id: a.id,
            type: a.type,
            filename: a.filename,
            durationSec: a.durationSec,
          })),
        });
        result = {
          diff: llmResult.diff,
          explanation: llmResult.explanation,
          newCutList: llmResult.newCutList as CutList,
          verb: undefined,
          fallbackToLLM: true,
        };
        source = "llm_fallback";
        const provider = (process.env.AI_PROVIDER ?? "claude").split(",")[0]?.trim() || "claude";
        await incrementTokenUsage(
          userId,
          llmResult.usage.totalTokens,
          provider,
          "/api/projects/:id/commands",
        );
      }

      const [updated] = await db
        .update(projects)
        .set({ cutList: result.newCutList, updatedAt: new Date() })
        .where(eq(projects.id, id))
        .returning();

      await db.insert(cutlistEdits).values({
        projectId: id,
        userId,
        renderId: null,
        patch: { before: currentCutList, after: result.newCutList },
        attributedBehaviorDeltas: computeBehaviorDeltas(currentCutList, result.newCutList),
        source,
        promptText: body.prompt,
      });

      await cacheDel(`projects:list:${userId}`);

      return {
        project: updated,
        diff: result.diff,
        explanation: result.explanation,
        verb: result.verb,
        fallbackToLLM: result.fallbackToLLM,
      };
    },
  );

  app.post("/commands/parse", { preHandler: validateBody(parseOnlySchema) }, async (request) => {
    const body = request.validatedBody as { prompt: string };
    const command = parseCommand(body.prompt);
    return {
      command,
      fallbackToLLM: command === null || command.confidence < 0.7,
    };
  });
}
