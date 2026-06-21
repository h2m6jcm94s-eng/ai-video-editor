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
    status: varchar("status", { length: 50 }).notNull().default("queued"),
    stage: varchar("stage", { length: 100 }).notNull().default("queued"),
    progress: real("progress").notNull().default(0),
    workflowId: text("workflow_id"),
    outputAssetId: uuid("output_asset_id"),
    previewAssetId: uuid("preview_asset_id"),
    errorMessage: text("error_message"),
    startedAt: timestamp("started_at", { withTimezone: true }),
    completedAt: timestamp("completed_at", { withTimezone: true }),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (table) => ({
    projectIdx: index("renders_project_idx").on(table.projectId),
    statusIdx: index("renders_status_idx").on(table.status),
    projectStatusIdx: index("renders_project_status_idx").on(table.projectId, table.status),
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

export const usersRelations = relations(users, ({ many }) => ({
  projects: many(projects),
  templates: many(templates),
  providerKeys: many(providerKeys),
}));

export const projectsRelations = relations(projects, ({ one, many }) => ({
  user: one(users, { fields: [projects.userId], references: [users.id] }),
  assets: many(assets),
  renders: many(renders),
}));

export const assetsRelations = relations(assets, ({ one }) => ({
  project: one(projects, { fields: [assets.projectId], references: [projects.id] }),
}));

export const rendersRelations = relations(renders, ({ one }) => ({
  project: one(projects, { fields: [renders.projectId], references: [projects.id] }),
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
export type Template = typeof templates.$inferSelect;
export type NewTemplate = typeof templates.$inferInsert;
export type ProviderKey = typeof providerKeys.$inferSelect;
export type NewProviderKey = typeof providerKeys.$inferInsert;
export type UserEvent = typeof userEvents.$inferSelect;
export type NewUserEvent = typeof userEvents.$inferInsert;
export type AdminAudit = typeof adminAudit.$inferSelect;
export type NewAdminAudit = typeof adminAudit.$inferInsert;
