-- Global pacing persists across restarts, also for long Telegram RetryAfter.
CREATE TABLE IF NOT EXISTS admin_dispatch_rate (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO admin_dispatch_rate(singleton) VALUES(TRUE) ON CONFLICT DO NOTHING;
CREATE UNIQUE INDEX IF NOT EXISTS ix_admin_chat_turn
ON admin_chat_messages(user_id,turn_id,direction) WHERE turn_id IS NOT NULL;
