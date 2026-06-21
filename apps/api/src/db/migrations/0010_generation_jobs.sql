-- Copyright (c) 2025 Devayan Dewri. All rights reserved.
-- Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
CREATE TABLE IF NOT EXISTS "generation_jobs" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "project_id" uuid NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
    "status" varchar(50) NOT NULL DEFAULT 'queued',
    "stage" varchar(100) NOT NULL DEFAULT 'queued',
    "progress" real NOT NULL DEFAULT 0,
    "workflow_id" text,
    "output_cut_list" jsonb,
    "error_message" text,
    "options" jsonb,
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS "generation_jobs_project_idx" ON "generation_jobs"("project_id");
CREATE INDEX IF NOT EXISTS "generation_jobs_status_idx" ON "generation_jobs"("status");
CREATE INDEX IF NOT EXISTS "generation_jobs_project_status_idx" ON "generation_jobs"("project_id", "status");
