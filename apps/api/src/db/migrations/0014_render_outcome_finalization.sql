-- Copyright (c) 2025 Devayan Dewri. All rights reserved.
-- Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
--
-- PR-A6: Add a 7-day outcome labeling window. Outcomes start as provisional and
-- become finalized after the window elapses, at which point they can be used for
-- corpus learning.

ALTER TABLE render_outcomes
  ADD COLUMN IF NOT EXISTS is_finalized boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS finalized_at timestamp with time zone;

CREATE INDEX IF NOT EXISTS render_outcomes_finalized_idx
  ON render_outcomes (is_finalized, finalized_at);
