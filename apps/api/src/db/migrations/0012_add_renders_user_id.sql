-- Copyright (c) 2025 Devayan Dewri. All rights reserved.
-- Licensed under the Elastic License 2.0 — see LICENSE in the repo root.

-- Add denormalized user_id to renders so feedback-pipeline writes can resolve
-- the owner without joining through projects.
ALTER TABLE "renders" ADD COLUMN "user_id" uuid;

UPDATE "renders"
SET "user_id" = "projects"."user_id"
FROM "projects"
WHERE "renders"."project_id" = "projects"."id";

-- Every render must belong to a project, so all rows should now have a user.
-- If any row is orphaned, assign it to a dummy user is not acceptable; fail fast.
ALTER TABLE "renders" ALTER COLUMN "user_id" SET NOT NULL;
ALTER TABLE "renders" ADD CONSTRAINT "renders_user_id_fk"
  FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS "renders_user_idx" ON "renders"("user_id");
