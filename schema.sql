-- Analytics database schema
-- SQLite database for storing processed analytics data

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time INTEGER NOT NULL,  -- Unix timestamp in ms
    end_time INTEGER,              -- Unix timestamp in ms (NULL if incomplete)
    duration_ms INTEGER,
    phase TEXT NOT NULL CHECK(phase IN ('work', 'break')),
    session_number INTEGER,
    completed BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time);
CREATE INDEX IF NOT EXISTS idx_sessions_phase ON sessions(phase);
CREATE INDEX IF NOT EXISTS idx_sessions_completed ON sessions(completed);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,  -- YYYY-MM-DD format
    total_work_minutes INTEGER DEFAULT 0,
    total_break_minutes INTEGER DEFAULT 0,
    completed_sessions INTEGER DEFAULT 0,
    incomplete_sessions INTEGER DEFAULT 0,
    total_focus_score REAL DEFAULT 0.0,  -- Average completion rate
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_stats(date);

CREATE TABLE IF NOT EXISTS weekly_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT NOT NULL,  -- YYYY-MM-DD format (Monday)
    week_end TEXT NOT NULL,    -- YYYY-MM-DD format (Sunday)
    total_work_minutes INTEGER DEFAULT 0,
    total_sessions INTEGER DEFAULT 0,
    avg_daily_minutes REAL DEFAULT 0.0,
    best_day_minutes INTEGER DEFAULT 0,
    streak_days INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(week_start, week_end)
);

CREATE INDEX IF NOT EXISTS idx_weekly_stats_week ON weekly_stats(week_start);

CREATE TABLE IF NOT EXISTS events_processed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_timestamp INTEGER NOT NULL,  -- Last processed event timestamp
    last_line_number INTEGER NOT NULL,  -- Last processed line in events.log
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Initialize events_processed tracker
INSERT OR IGNORE INTO events_processed (id, last_timestamp, last_line_number) 
VALUES (1, 0, 0);
