-- Add render options JSONB column to persist export presets and future render settings.
ALTER TABLE "renders" ADD COLUMN IF NOT EXISTS "options" jsonb;
