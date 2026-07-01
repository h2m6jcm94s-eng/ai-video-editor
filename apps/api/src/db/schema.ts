// Copyright (c) 2025 Devayan Dewri. All rights reserved.
import { relations } from "drizzle-orm";
// Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
// Commercial SaaS use is prohibited without written permission.
import {
  boolean,
  index,
  integer,
  jsonb,
  pgTable,
  primaryKey,
  real,
  text,
  timestamp,
  uuid,
  varchar,
} from "drizzle-orm/pg-core";

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  clerkId: varchar("clerk_id", { length: 255 }).unique(),
  email: varchar("email", { length: 255 }).notNull().unique(),
  name: varchar("name", { length: 255 }),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
});

export const projects = pgTable(
  "projects",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    name: varchar("name", { length: 255 }).notNull(),
    status: varchar("status", { length: 50 }).notNull().default("uploading"),
    styleTier: varchar("style_tier", { length: 50 }).notNull().default("with_effects"),
    mode: varchar("mode", { length: 50 }).notNull().default("auto"),
    referenceAssetId: uuid("reference_asset_id"),
    songAssetId: uuid("song_asset_id"),
    clipAssetIds: jsonb("clip_asset_ids").$type<string[]>().default([]),
    cutList: jsonb("cut_list"),
    styleAnalysis: jsonb("style_analysis"),
    excludeFromLearning: boolean("exclude_from_learning").default(false).notNull(),
    renderAssetId: uuid("render_asset_id"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    userIdx: index("projects_user_idx").on(table.userId),
  }),
);

export const assets = pgTable(
  "assets",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    type: varchar("type", { length: 50 }).notNull(),
    filename: varchar("filename", { length: 255 }).notNull(),
    mimeType: varchar("mime_type", { length: 100 }).notNull(),
    sizeBytes: integer("size_bytes").notNull().default(0),
    durationSec: real("duration_sec"),
    width: integer("width"),
    height: integer("height"),
    fps: real("fps"),
    storageKey: text("storage_key").notNull(),
    storageUrl: text("storage_url"),
    metadata: jsonb("metadata"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    projectIdx: index("assets_project_idx").on(table.projectId),
  }),
);

export const renders = pgTable(
  "renders",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    userId: uuid("user_id").notNull(),
    status: varchar("status", { length: 50 }).notNull().default("queued"),
    stage: varchar("stage", { length: 100 }).notNull().default("queued"),
    progress: real("progress").notNull().default(0),
    workflowId: text("workflow_id"),
    outputAssetId: uuid("output_asset_id"),
    previewAssetId: uuid("preview_asset_id"),
    errorMessage: text("error_message"),
    options: jsonb("options"),
    startedAt: timestamp("started_at", { withTimezone: true }),
    completedAt: timestamp("completed_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    projectIdx: index("renders_project_idx").on(table.projectId),
    userIdx: index("renders_user_idx").on(table.userId),
    statusIdx: index("renders_status_idx").on(table.status),
    projectStatusIdx: index("renders_project_status_idx").on(table.projectId, table.status),
  }),
);

export const generationJobs = pgTable(
  "generation_jobs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    status: varchar("status", { length: 50 }).notNull().default("queued"),
    stage: varchar("stage", { length: 100 }).notNull().default("queued"),
    progress: real("progress").notNull().default(0),
    workflowId: text("workflow_id"),
    outputCutList: jsonb("output_cut_list"),
    errorMessage: text("error_message"),
    options: jsonb("options"),
    startedAt: timestamp("started_at", { withTimezone: true }),
    completedAt: timestamp("completed_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    projectIdx: index("generation_jobs_project_idx").on(table.projectId),
    statusIdx: index("generation_jobs_status_idx").on(table.status),
    projectStatusIdx: index("generation_jobs_project_status_idx").on(table.projectId, table.status),
  }),
);

export const templates = pgTable(
  "templates",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    name: varchar("name", { length: 255 }).notNull(),
    description: text("description"),
    cutList: jsonb("cut_list").notNull(),
    tags: jsonb("tags").$type<string[]>().default([]),
    isPublic: boolean("is_public").default(false),
    usageCount: integer("usage_count").default(0),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    userIdx: index("templates_user_idx").on(table.userId),
  }),
);

export const providerKeys = pgTable(
  "provider_keys",
  {
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    provider: varchar("provider", { length: 50 }).notNull(),
    encryptedKey: text("encrypted_key").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.userId, table.provider] }),
    userIdx: index("provider_keys_user_idx").on(table.userId),
  }),
);

export const userEvents = pgTable(
  "user_events",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id").notNull(),
    code: varchar("code", { length: 50 }).notNull(),
    message: text("message").notNull(),
    details: jsonb("details"),
    route: varchar("route", { length: 255 }),
    occurrenceCount: integer("occurrence_count").notNull().default(1),
    acknowledged: boolean("acknowledged").notNull().default(false),
    dropped: boolean("dropped").notNull().default(false),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    userIdx: index("user_events_user_idx").on(table.userId),
    userAckIdx: index("user_events_user_ack_idx").on(table.userId, table.acknowledged),
    createdAtIdx: index("user_events_created_at_idx").on(table.createdAt),
  }),
);

export const adminAudit = pgTable(
  "admin_audit",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    actorId: uuid("actor_id").notNull(),
    action: varchar("action", { length: 100 }).notNull(),
    targetType: varchar("target_type", { length: 50 }),
    targetId: varchar("target_id", { length: 255 }),
    metadata: jsonb("metadata"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    actorIdx: index("admin_audit_actor_idx").on(table.actorId),
    createdAtIdx: index("admin_audit_created_at_idx").on(table.createdAt),
  }),
);

// ---------------------------------------------------------------------------
// Feedback pipeline tables (PR-4)
// ---------------------------------------------------------------------------

export const renderSignals = pgTable(
  "render_signals",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    renderId: uuid("render_id")
      .notNull()
      .references(() => renders.id, { onDelete: "cascade" }),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    speechRatio: real("speech_ratio").default(0),
    avgSpeechSegmentDurationS: real("avg_speech_segment_duration_s").default(0),
    multiSpeakerRatio: real("multi_speaker_ratio").default(0),
    songPresent: boolean("song_present").default(false),
    songEnergyMean: real("song_energy_mean").default(0.5),
    songTempoBpm: real("song_tempo_bpm").default(120),
    songSectionCount: integer("song_section_count").default(0),
    clipCount: integer("clip_count").default(0),
    clipAvgDurationS: real("clip_avg_duration_s").default(0),
    motionDensity: real("motion_density").default(0.5),
    motionVariance: real("motion_variance").default(0),
    aestheticScoreMean: real("aesthetic_score_mean").default(0.5),
    faceScreentimeRatio: real("face_screentime_ratio").default(0),
    multiFaceRatio: real("multi_face_ratio").default(0),
    shotDiversity: real("shot_diversity").default(0),
    referencePresent: boolean("reference_present").default(false),
    referenceGenomeHash: varchar("reference_genome_hash", { length: 255 }),
    contentEmbedding: jsonb("content_embedding"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    renderIdx: index("render_signals_render_idx").on(table.renderId),
    userIdx: index("render_signals_user_idx").on(table.userId),
    projectIdx: index("render_signals_project_idx").on(table.projectId),
  }),
);

export const renderBehavior = pgTable(
  "render_behavior",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    renderId: uuid("render_id")
      .notNull()
      .references(() => renders.id, { onDelete: "cascade" }),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    cutDensityPerSec: real("cut_density_per_sec").notNull().default(0.16),
    slotDurationMeanS: real("slot_duration_mean_s").notNull().default(2.5),
    slotDurationStdS: real("slot_duration_std_s").notNull().default(0.8),
    clipAudioInclusionStrategy: varchar("clip_audio_inclusion_strategy", { length: 50 })
      .notNull()
      .default("speech_only"),
    clipAudioMinImportance: real("clip_audio_min_importance").notNull().default(0.3),
    sfxMuteAggressiveness: real("sfx_mute_aggressiveness").notNull().default(0.3),
    songBackgroundMode: varchar("song_background_mode", { length: 50 }).notNull().default("ambient"),
    hardCutRatio: real("hard_cut_ratio").notNull().default(0.7),
    duckAggressiveness: real("duck_aggressiveness").notNull().default(0.5),
    textDensityPerSec: real("text_density_per_sec").notNull().default(0),
    effectIntensity: real("effect_intensity").notNull().default(0.5),
    predictorVersion: varchar("predictor_version", { length: 100 }).notNull().default("heuristic-v1"),
    predictorConfidence: real("predictor_confidence").default(0.5),
    predictorReasoning: jsonb("predictor_reasoning"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    renderIdx: index("render_behavior_render_idx").on(table.renderId),
    userIdx: index("render_behavior_user_idx").on(table.userId),
    predictorVersionIdx: index("render_behavior_predictor_version_idx").on(table.predictorVersion),
  }),
);

export const renderOutcomes = pgTable(
  "render_outcomes",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    renderId: uuid("render_id")
      .notNull()
      .references(() => renders.id, { onDelete: "cascade" }),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    exported: boolean("exported").default(false),
    exportedAt: timestamp("exported_at", { withTimezone: true }),
    downloaded: boolean("downloaded").default(false),
    downloadedAt: timestamp("downloaded_at", { withTimezone: true }),
    regenerated: boolean("regenerated").default(false),
    regeneratedAt: timestamp("regenerated_at", { withTimezone: true }),
    abandoned: boolean("abandoned").default(false),
    abandonedAt: timestamp("abandoned_at", { withTimezone: true }),
    editCount: integer("edit_count").default(0),
    explicitRating: integer("explicit_rating"),
    thumbsUp: boolean("thumbs_up"),
    thumbComment: text("thumb_comment"),
    inferredQualityScore: real("inferred_quality_score"),
    uploadedPlatformId: varchar("uploaded_platform_id", { length: 255 }),
    retention30sPercent: real("retention_30s_percent"),
    totalViews: integer("total_views"),
    isFinalized: boolean("is_finalized").default(false).notNull(),
    finalizedAt: timestamp("finalized_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    renderIdx: index("render_outcomes_render_idx").on(table.renderId),
    userIdx: index("render_outcomes_user_idx").on(table.userId),
    inferredQualityIdx: index("render_outcomes_inferred_quality_idx").on(table.inferredQualityScore),
    finalizedIdx: index("render_outcomes_finalized_idx").on(table.isFinalized, table.finalizedAt),
  }),
);

export const cutlistEdits = pgTable(
  "cutlist_edits",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    renderId: uuid("render_id").references(() => renders.id, { onDelete: "set null" }),
    projectId: uuid("project_id")
      .notNull()
      .references(() => projects.id, { onDelete: "cascade" }),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    patch: jsonb("patch").notNull(),
    attributedBehaviorDeltas: jsonb("attributed_behavior_deltas").default({}).notNull(),
    source: varchar("source", { length: 50 }).notNull().default("manual_ui"),
    promptText: text("prompt_text"),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    renderIdx: index("cutlist_edits_render_idx").on(table.renderId),
    userIdx: index("cutlist_edits_user_idx").on(table.userId),
    projectIdx: index("cutlist_edits_project_idx").on(table.projectId),
  }),
);

export const userTasteProfiles = pgTable(
  "user_taste_profiles",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    nProjectsCompleted: integer("n_projects_completed").default(0),
    nRendersExported: integer("n_renders_exported").default(0),
    nEditsAccepted: integer("n_edits_accepted").default(0),
    clusterBiasVectors: jsonb("cluster_bias_vectors").default({ general: {} }).notNull(),
    tasteEmbedding: jsonb("taste_embedding"),
    profileConfidence: real("profile_confidence").default(0),
    contributeToGlobalCorpus: boolean("contribute_to_global_corpus").default(true),
    lastUpdatedAt: timestamp("last_updated_at", { withTimezone: true }).defaultNow(),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    userIdx: index("user_taste_profiles_user_idx").on(table.userId),
  }),
);

export const behaviorCorpusEntries = pgTable(
  "behavior_corpus_entries",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    signals: jsonb("signals").notNull(),
    behavior: jsonb("behavior").notNull(),
    qualityWeight: real("quality_weight").notNull().default(0),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    isPublic: boolean("is_public").default(true),
    status: varchar("status", { length: 20 }).notNull().default("active"),
    source: varchar("source", { length: 100 }).notNull().default("user_render"),
    producingPredictorVersion: varchar("producing_predictor_version", { length: 100 }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    userIdx: index("behavior_corpus_entries_user_idx").on(table.userId),
    publicIdx: index("behavior_corpus_entries_public_idx").on(table.isPublic, table.qualityWeight),
    statusIdx: index("behavior_corpus_entries_status_idx").on(table.status),
    userCreatedIdx: index("behavior_corpus_entries_user_created_idx").on(table.userId, table.createdAt),
  }),
);

export const usersRelations = relations(users, ({ many }) => ({
  projects: many(projects),
  templates: many(templates),
  providerKeys: many(providerKeys),
}));

export const projectsRelations = relations(projects, ({ one, many }) => ({
  user: one(users, { fields: [projects.userId], references: [users.id] }),
  assets: many(assets),
  renders: many(renders),
  generationJobs: many(generationJobs),
}));

export const assetsRelations = relations(assets, ({ one }) => ({
  project: one(projects, { fields: [assets.projectId], references: [projects.id] }),
}));

export const rendersRelations = relations(renders, ({ one }) => ({
  project: one(projects, { fields: [renders.projectId], references: [projects.id] }),
  user: one(users, { fields: [renders.userId], references: [users.id] }),
}));

export const generationJobsRelations = relations(generationJobs, ({ one }) => ({
  project: one(projects, { fields: [generationJobs.projectId], references: [projects.id] }),
}));

export const templatesRelations = relations(templates, ({ one }) => ({
  user: one(users, { fields: [templates.userId], references: [users.id] }),
}));

export type User = typeof users.$inferSelect;
export type NewUser = typeof users.$inferInsert;
export type Project = typeof projects.$inferSelect;
export type NewProject = typeof projects.$inferInsert;
export type Asset = typeof assets.$inferSelect;
export type NewAsset = typeof assets.$inferInsert;
export type Render = typeof renders.$inferSelect;
export type NewRender = typeof renders.$inferInsert;
export type GenerationJob = typeof generationJobs.$inferSelect;
export type NewGenerationJob = typeof generationJobs.$inferInsert;
export type Template = typeof templates.$inferSelect;
export type NewTemplate = typeof templates.$inferInsert;
export type ProviderKey = typeof providerKeys.$inferSelect;
export type NewProviderKey = typeof providerKeys.$inferInsert;
export type UserEvent = typeof userEvents.$inferSelect;
export type NewUserEvent = typeof userEvents.$inferInsert;
export type AdminAudit = typeof adminAudit.$inferSelect;
export type NewAdminAudit = typeof adminAudit.$inferInsert;
export type RenderSignals = typeof renderSignals.$inferSelect;
export type NewRenderSignals = typeof renderSignals.$inferInsert;
export type RenderBehavior = typeof renderBehavior.$inferSelect;
export type NewRenderBehavior = typeof renderBehavior.$inferInsert;
export type RenderOutcomes = typeof renderOutcomes.$inferSelect;
export type NewRenderOutcomes = typeof renderOutcomes.$inferInsert;
export type CutlistEdit = typeof cutlistEdits.$inferSelect;
export type NewCutlistEdit = typeof cutlistEdits.$inferInsert;
export type UserTasteProfile = typeof userTasteProfiles.$inferSelect;
export type NewUserTasteProfile = typeof userTasteProfiles.$inferInsert;
export type BehaviorCorpusEntry = typeof behaviorCorpusEntries.$inferSelect;
export type NewBehaviorCorpusEntry = typeof behaviorCorpusEntries.$inferInsert;
