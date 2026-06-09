-- 0003_camelcase_cutlist.sql
-- Backfill: convert any remaining snake_case keys in projects.cut_list JSONB to camelCase.
-- One-shot. Idempotent (re-running on already-camelCase data is a no-op).
--
-- Rollback: pre-revenue, simplest rollback is wipe dev DB and recreate.
-- The transform is lossless for our key set (snake → camel is bijective).

CREATE OR REPLACE FUNCTION snake_to_camel(snake TEXT) RETURNS TEXT AS $$
  SELECT regexp_replace(snake, '_([a-z])', UPPER('\1'), 'g')
$$ LANGUAGE SQL IMMUTABLE;

CREATE OR REPLACE FUNCTION camel_case_keys(j JSONB) RETURNS JSONB AS $$
  SELECT CASE jsonb_typeof(j)
    WHEN 'object' THEN (
      SELECT jsonb_object_agg(snake_to_camel(key), camel_case_keys(value))
      FROM jsonb_each(j)
    )
    WHEN 'array' THEN (
      SELECT jsonb_agg(camel_case_keys(elem))
      FROM jsonb_array_elements(j) elem
    )
    ELSE j
  END
$$ LANGUAGE SQL IMMUTABLE;

UPDATE projects
SET cut_list = camel_case_keys(cut_list)
WHERE cut_list IS NOT NULL
  AND cut_list::text LIKE '%_%';

UPDATE templates
SET cut_list = camel_case_keys(cut_list)
WHERE cut_list IS NOT NULL
  AND cut_list::text LIKE '%_%';

-- Don't drop the helper functions — they're useful if we add more JSONB columns.
