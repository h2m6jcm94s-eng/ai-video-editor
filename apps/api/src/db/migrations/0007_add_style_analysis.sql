-- Add cached style analysis output to projects
ALTER TABLE "projects" ADD COLUMN IF NOT EXISTS "style_analysis" jsonb;
