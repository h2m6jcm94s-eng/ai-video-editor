-- Copyright (c) 2025 Devayan Dewri. All rights reserved.
-- Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

-- Snapshot of content signals extracted at render time.
CREATE TABLE IF NOT EXISTS "render_signals" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "render_id" uuid NOT NULL REFERENCES "renders"("id") ON DELETE CASCADE,
    "user_id" uuid NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
    "project_id" uuid NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
    "speech_ratio" real DEFAULT 0,
    "avg_speech_segment_duration_s" real DEFAULT 0,
    "multi_speaker_ratio" real DEFAULT 0,
    "song_present" boolean DEFAULT false,
    "song_energy_mean" real DEFAULT 0.5,
    "song_tempo_bpm" real DEFAULT 120,
    "song_section_count" integer DEFAULT 0,
    "clip_count" integer DEFAULT 0,
    "clip_avg_duration_s" real DEFAULT 0,
    "motion_density" real DEFAULT 0.5,
    "motion_variance" real DEFAULT 0,
    "aesthetic_score_mean" real DEFAULT 0.5,
    "face_screentime_ratio" real DEFAULT 0,
    "multi_face_ratio" real DEFAULT 0,
    "shot_diversity" real DEFAULT 0,
    "reference_present" boolean DEFAULT false,
    "reference_genome_hash" varchar(255),
    "content_embedding" jsonb,
    "created_at" timestamp with time zone DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS "render_signals_render_idx" ON "render_signals"("render_id");
CREATE INDEX IF NOT EXISTS "render_signals_user_idx" ON "render_signals"("user_id");
CREATE INDEX IF NOT EXISTS "render_signals_project_idx" ON "render_signals"("project_id");

-- Behavior vector applied to a render.
CREATE TABLE IF NOT EXISTS "render_behavior" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "render_id" uuid NOT NULL REFERENCES "renders"("id") ON DELETE CASCADE,
    "user_id" uuid NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
    "project_id" uuid NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
    "cut_density_per_sec" real DEFAULT 0.16 NOT NULL,
    "slot_duration_mean_s" real DEFAULT 2.5 NOT NULL,
    "slot_duration_std_s" real DEFAULT 0.8 NOT NULL,
    "clip_audio_inclusion_strategy" varchar(50) DEFAULT 'speech_only' NOT NULL,
    "clip_audio_min_importance" real DEFAULT 0.3 NOT NULL,
    "sfx_mute_aggressiveness" real DEFAULT 0.3 NOT NULL,
    "song_background_mode" varchar(50) DEFAULT 'ambient' NOT NULL,
    "hard_cut_ratio" real DEFAULT 0.7 NOT NULL,
    "duck_aggressiveness" real DEFAULT 0.5 NOT NULL,
    "text_density_per_sec" real DEFAULT 0 NOT NULL,
    "effect_intensity" real DEFAULT 0.5 NOT NULL,
    "predictor_version" varchar(100) DEFAULT 'heuristic-v1' NOT NULL,
    "predictor_confidence" real DEFAULT 0.5,
    "predictor_reasoning" jsonb,
    "created_at" timestamp with time zone DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS "render_behavior_render_idx" ON "render_behavior"("render_id");
CREATE INDEX IF NOT EXISTS "render_behavior_user_idx" ON "render_behavior"("user_id");
CREATE INDEX IF NOT EXISTS "render_behavior_predictor_version_idx" ON "render_behavior"("predictor_version");

-- Outcomes observed after a render (implicit + explicit feedback).
CREATE TABLE IF NOT EXISTS "render_outcomes" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "render_id" uuid NOT NULL REFERENCES "renders"("id") ON DELETE CASCADE,
    "user_id" uuid NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
    "project_id" uuid NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
    "exported" boolean DEFAULT false,
    "exported_at" timestamp with time zone,
    "downloaded" boolean DEFAULT false,
    "downloaded_at" timestamp with time zone,
    "regenerated" boolean DEFAULT false,
    "regenerated_at" timestamp with time zone,
    "abandoned" boolean DEFAULT false,
    "abandoned_at" timestamp with time zone,
    "edit_count" integer DEFAULT 0,
    "explicit_rating" integer,
    "thumbs_up" boolean,
    "thumb_comment" text,
    "inferred_quality_score" real,
    "uploaded_platform_id" varchar(255),
    "retention_30s_percent" real,
    "total_views" integer,
    "created_at" timestamp with time zone DEFAULT now(),
    "updated_at" timestamp with time zone DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS "render_outcomes_render_idx" ON "render_outcomes"("render_id");
CREATE INDEX IF NOT EXISTS "render_outcomes_user_idx" ON "render_outcomes"("user_id");
CREATE INDEX IF NOT EXISTS "render_outcomes_inferred_quality_idx" ON "render_outcomes"("inferred_quality_score");

-- Granular cutlist edit deltas attributed to behavior-vector changes.
CREATE TABLE IF NOT EXISTS "cutlist_edits" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "render_id" uuid REFERENCES "renders"("id") ON DELETE SET NULL,
    "project_id" uuid NOT NULL REFERENCES "projects"("id") ON DELETE CASCADE,
    "user_id" uuid NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
    "patch" jsonb NOT NULL,
    "attributed_behavior_deltas" jsonb DEFAULT '{}' NOT NULL,
    "source" varchar(50) DEFAULT 'manual_ui' NOT NULL,
    "prompt_text" text,
    "created_at" timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS "cutlist_edits_render_idx" ON "cutlist_edits"("render_id");
CREATE INDEX IF NOT EXISTS "cutlist_edits_user_idx" ON "cutlist_edits"("user_id");
CREATE INDEX IF NOT EXISTS "cutlist_edits_project_idx" ON "cutlist_edits"("project_id");

-- Per-user taste profile and personalization bias.
CREATE TABLE IF NOT EXISTS "user_taste_profiles" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "user_id" uuid NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
    "n_projects_completed" integer DEFAULT 0,
    "n_renders_exported" integer DEFAULT 0,
    "n_edits_accepted" integer DEFAULT 0,
    "personal_bias_vector" jsonb DEFAULT '{}' NOT NULL,
    "taste_embedding" jsonb,
    "profile_confidence" real DEFAULT 0,
    "contribute_to_global_corpus" boolean DEFAULT true,
    "last_updated_at" timestamp with time zone DEFAULT now(),
    "created_at" timestamp with time zone DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS "user_taste_profiles_user_idx" ON "user_taste_profiles"("user_id");

-- Global + personal behavior corpus entries for KNN / MLP training.
CREATE TABLE IF NOT EXISTS "behavior_corpus_entries" (
    "id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
    "signals" jsonb NOT NULL,
    "behavior" jsonb NOT NULL,
    "quality_weight" real DEFAULT 0 NOT NULL,
    "user_id" uuid NOT NULL REFERENCES "users"("id") ON DELETE CASCADE,
    "is_public" boolean DEFAULT true,
    "source" varchar(100) DEFAULT 'user_render' NOT NULL,
    "created_at" timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS "behavior_corpus_entries_user_idx" ON "behavior_corpus_entries"("user_id");
CREATE INDEX IF NOT EXISTS "behavior_corpus_entries_public_idx" ON "behavior_corpus_entries"("is_public", "quality_weight");
