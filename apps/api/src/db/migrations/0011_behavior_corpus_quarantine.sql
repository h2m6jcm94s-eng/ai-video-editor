-- 0011_behavior_corpus_quarantine.sql
-- Harden behavior corpus against spam and poisoning (PR-A4).

ALTER TABLE "behavior_corpus_entries"
    ADD COLUMN IF NOT EXISTS "status" varchar(20) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS "producing_predictor_version" varchar(100);

-- Backfill existing rows so they remain active.
UPDATE "behavior_corpus_entries" SET "status" = 'active' WHERE "status" IS NULL;

CREATE INDEX IF NOT EXISTS "behavior_corpus_entries_status_idx" ON "behavior_corpus_entries"("status");
CREATE INDEX IF NOT EXISTS "behavior_corpus_entries_user_created_idx" ON "behavior_corpus_entries"("user_id", "created_at");
