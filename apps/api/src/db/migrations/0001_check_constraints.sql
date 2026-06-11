-- CHECK constraints for enum columns (idempotent via exception guards)
DO $$ BEGIN
  ALTER TABLE projects ADD CONSTRAINT projects_status_chk CHECK (status IN ('uploading', 'processing', 'complete', 'failed'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  ALTER TABLE projects ADD CONSTRAINT projects_style_tier_chk CHECK (style_tier IN ('cuts_only', 'color_grade', 'with_text', 'with_effects', 'full_remix'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  ALTER TABLE projects ADD CONSTRAINT projects_mode_chk CHECK (mode IN ('auto', 'assisted'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  ALTER TABLE assets ADD CONSTRAINT assets_type_chk CHECK (type IN ('reference_video', 'song', 'clip', 'render', 'preview', 'subtitle', 'lut', 'sfx'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
  ALTER TABLE renders ADD CONSTRAINT renders_status_chk CHECK (status IN ('queued', 'running', 'complete', 'failed'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;
