-- Additive migration: no changes to English progress, news or subscriptions.
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS privacy_choice_at TIMESTAMPTZ;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS notice_version TEXT;
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS privacy_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE admin_chat_messages ADD COLUMN IF NOT EXISTS turn_id TEXT;
CREATE INDEX IF NOT EXISTS ix_admin_chat_cursor ON admin_chat_messages(user_id, message_id DESC);
CREATE INDEX IF NOT EXISTS ix_admin_users_seen ON admin_users(last_seen_at DESC, user_id);

CREATE TABLE IF NOT EXISTS admin_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    target_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS admin_sessions (
    token_hash TEXT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    credential_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_login_challenges (
    token_hash TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL,
    owner_id BIGINT NOT NULL,
    credential_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_admin_login_bucket ON admin_login_attempts(bucket, created_at);

CREATE TABLE IF NOT EXISTS admin_dispatches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    target_id BIGINT,
    content TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','queued','complete','cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS admin_deliveries (
    dispatch_id BIGINT NOT NULL REFERENCES admin_dispatches(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','sending','sent','failed','skipped','unknown')),
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    error_code TEXT,
    PRIMARY KEY(dispatch_id, user_id)
);
CREATE INDEX IF NOT EXISTS ix_admin_delivery_pending ON admin_deliveries(available_at) WHERE state='pending';
