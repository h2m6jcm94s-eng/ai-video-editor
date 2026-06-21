-- Add 'mask' to the assets.type check constraint (idempotent)
DO $$ BEGIN
  ALTER TABLE assets DROP CONSTRAINT IF EXISTS assets_type_chk;
EXCEPTION WHEN undefined_object THEN null;
END $$;

DO $$ BEGIN
  ALTER TABLE assets ADD CONSTRAINT assets_type_chk CHECK (type IN ('reference_video', 'song', 'clip', 'render', 'preview', 'subtitle', 'lut', 'sfx', 'mask'));
EXCEPTION WHEN duplicate_object THEN null;
END $$;
