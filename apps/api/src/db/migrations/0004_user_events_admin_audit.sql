-- 0004_user_events_admin_audit.sql
-- Per-user error tracking + admin audit log (Pass 4.6)

CREATE TABLE IF NOT EXISTS user_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    code VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    route VARCHAR(255),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    dropped BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS user_events_user_idx ON user_events(user_id);
CREATE INDEX IF NOT EXISTS user_events_user_ack_idx ON user_events(user_id, acknowledged);
CREATE INDEX IF NOT EXISTS user_events_created_at_idx ON user_events(created_at);

CREATE TABLE IF NOT EXISTS admin_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS admin_audit_actor_idx ON admin_audit(actor_id);
CREATE INDEX IF NOT EXISTS admin_audit_created_at_idx ON admin_audit(created_at);
