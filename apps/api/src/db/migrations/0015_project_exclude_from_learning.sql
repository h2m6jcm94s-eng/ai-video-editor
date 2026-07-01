-- Copyright (c) 2025 Devayan Dewri. All rights reserved.
-- Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
--
-- PR-A7: Per-project opt-out from behavior-corpus learning. Users can run
-- experimental renders without polluting the shared taste model.

ALTER TABLE projects
  ADD COLUMN IF NOT EXISTS exclude_from_learning boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS projects_exclude_from_learning_idx
  ON projects (exclude_from_learning);
