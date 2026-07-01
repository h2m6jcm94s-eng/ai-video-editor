-- Copyright (c) 2025 Devayan Dewri. All rights reserved.
-- Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
--
-- PR-A5: Replace the single global personal bias vector with per-cluster bias
-- vectors so user taste can vary by content cluster (dialogue, music_video, etc.)
-- without collapsing into a single archetype.

ALTER TABLE user_taste_profiles
  RENAME COLUMN personal_bias_vector TO cluster_bias_vectors;

-- Empty/null legacy vectors become a default "general" bucket. Non-empty legacy
-- vectors are preserved under "general" so existing taste data is not lost.
UPDATE user_taste_profiles
SET cluster_bias_vectors = jsonb_build_object(
  'general',
  CASE
    WHEN cluster_bias_vectors IS NULL THEN '{}'::jsonb
    WHEN cluster_bias_vectors = '{}'::jsonb THEN '{}'::jsonb
    ELSE cluster_bias_vectors
  END
)
WHERE cluster_bias_vectors IS NULL
   OR cluster_bias_vectors = '{}'::jsonb
   OR jsonb_typeof(cluster_bias_vectors) != 'object'
   OR NOT (cluster_bias_vectors ? 'general');

-- Ensure a sane default for new rows.
ALTER TABLE user_taste_profiles
  ALTER COLUMN cluster_bias_vectors SET DEFAULT '{"general": {}}'::jsonb;

-- Add a GIN index for fast lookups of specific clusters (e.g. dialogue bias).
CREATE INDEX IF NOT EXISTS user_taste_profiles_cluster_bias_idx
  ON user_taste_profiles USING GIN (cluster_bias_vectors jsonb_path_ops);
