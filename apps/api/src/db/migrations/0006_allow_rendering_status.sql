-- Allow projects to enter the "rendering" status used by the render pipeline.
DO $$ BEGIN
  ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_status_chk;
  ALTER TABLE projects ADD CONSTRAINT projects_status_chk CHECK (status IN ('uploading', 'processing', 'rendering', 'complete', 'failed'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;
