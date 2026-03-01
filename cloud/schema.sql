-- Hari Cloud Database Schema
-- Cloudflare D1 (SQLite at edge)

-- Users table - stores minimal data for heartbeat/nudges
CREATE TABLE IF NOT EXISTS users (
    chat_id TEXT PRIMARY KEY,
    last_heartbeat INTEGER NOT NULL,  -- Unix timestamp in milliseconds
    last_nudge INTEGER,                -- Last inactivity nudge sent
    last_goal_reminder INTEGER,        -- Last "goal not met today" reminder (once per day)
    settings TEXT DEFAULT '{}',        -- JSON: nudge preferences, etc
    stats TEXT DEFAULT '{}',           -- JSON: streak, today_work_minutes, goal_minutes, etc
    created_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

-- Index for finding users to nudge
CREATE INDEX IF NOT EXISTS idx_last_heartbeat ON users(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_last_nudge ON users(last_nudge);

-- Migration: if you already have users table without last_goal_reminder, run:
-- ALTER TABLE users ADD COLUMN last_goal_reminder INTEGER;

-- Example settings JSON:
-- {
--   "nudges_enabled": true,
--   "goal_reminders_enabled": true,
--   "goal_reminder_hour_utc": 20,
--   "threshold_hours": 48
-- }

-- Example stats JSON (sent by hari-services heartbeat):
-- Single goal (backward compat):
--   "today_work_minutes": 45, "goal_minutes": 90, "goal_label": "2h deep work"
-- Multiple goals:
--   "today_work_minutes": 45,
--   "goals": [
--     { "goal_minutes": 90, "goal_label": "focus" },
--     { "goal_minutes": 120, "goal_label": "deep work" }
--   ]
