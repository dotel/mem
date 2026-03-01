#!/usr/bin/env python3
"""
Hari Services - Unified Python Service
Handles LLM commands, notification events, and analytics in a single process.
Includes natural language analytics queries (RAG).
"""

import queue
import json
import sys
import os
import signal
import re
import time
import threading
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def _get_config_path() -> Path:
    """Config path: config.json in the app directory (same folder as this file)."""
    return Path(__file__).resolve().parent / "config.json"


try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[WARN] requests library not available; Ollama/Telegram disabled")

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    SentenceTransformer = None  # type: ignore
    np = None  # type: ignore
    print("[WARN] sentence-transformers/numpy not available; memory RAG disabled")

try:
    from fastapi import FastAPI, Body, HTTPException, Depends
    from fastapi.responses import StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from typing import Optional
    import uvicorn
    WEBAPI_AVAILABLE = True
except ImportError:
    WEBAPI_AVAILABLE = False
    FastAPI = None  # type: ignore
    print("[WARN] fastapi/uvicorn not available; web API disabled (pip install fastapi uvicorn)")

try:
    from llm_providers import create_llm_provider, LLMProvider
    LLM_PROVIDERS_AVAILABLE = True
except ImportError:
    LLM_PROVIDERS_AVAILABLE = False
    create_llm_provider = None  # type: ignore
    LLMProvider = None  # type: ignore

try:
    import jwt
    import bcrypt
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    jwt = None  # type: ignore
    bcrypt = None  # type: ignore
    print("[WARN] pyjwt/bcrypt not available; auth disabled (pip install pyjwt bcrypt)")


# LLM defaults (overridden by config via llm_providers)
OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2:7b"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class TelegramNotifier:
    """Handles Telegram notifications"""
    
    def __init__(self):
        self.logger = logging.getLogger('telegram')
        self.config_path = _get_config_path()
        self.enabled = False
        self.bot_token = None
        self.chat_id = None
        self.load_config()
    
    def load_config(self):
        """Load configuration from config.json in the app directory."""
        if not self.config_path.exists():
            self.logger.error(f"Config file not found: {self.config_path}")
            return
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            telegram_config = config.get('telegram', {})
            self.enabled = telegram_config.get('enabled', False)
            self.bot_token = telegram_config.get('bot_token', '')
            self.chat_id = telegram_config.get('chat_id', '')
            
            if self.enabled:
                if not self.bot_token or not self.chat_id:
                    self.logger.error("Telegram enabled but bot_token or chat_id missing in config")
                    self.enabled = False
                else:
                    self.logger.info(f"Telegram notifications enabled (chat_id: {self.chat_id})")
            else:
                self.logger.info("Telegram notifications disabled")
        
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse config: {e}")
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
    
    def send_message(self, message):
        """Send a message via Telegram Bot API"""
        if not self.enabled:
            self.logger.debug("Telegram disabled, skipping notification")
            return False
        
        if not REQUESTS_AVAILABLE:
            self.logger.error("requests library not available, cannot send Telegram message")
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': message
        }
        
        try:
            self.logger.info(f"Sending: '{message}'")
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info("✅ Sent successfully")
                return True
            else:
                self.logger.error(f"❌ API error {response.status_code}: {response.text}")
                try:
                    error_data = response.json()
                    error_desc = error_data.get('description', 'Unknown error')
                    self.logger.error(f"Description: {error_desc}")
                except:
                    pass
                return False
        
        except requests.exceptions.Timeout:
            self.logger.error("Request timed out")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send: {e}")
            return False
    
    def handle_event(self, event):
        """Handle an event and send appropriate notification"""
        event_type = event.get('type_name', event.get('type', 'unknown'))
        
        messages = {
            'pomodoro_complete': '🍅 Pomodoro complete! Time for a break.',
            'pomodoro_start': '🎯 Pomodoro started! Stay focused.',
            'pomodoro_pause': '⏸️ Pomodoro paused.',
            'pomodoro_cancel': '❌ Pomodoro cancelled.',
            'usage_threshold': '⚠️ Usage threshold exceeded! Time to refocus.',
            'daily_summary': '📊 Daily Summary: Check your productivity stats!'
        }
        
        message = messages.get(event_type)
        if message:
            self.send_message(message)


# Event type constants (match legacy C daemon for events.log compatibility)
EVENT_POMODORO_COMPLETE = 0
EVENT_POMODORO_START = 1
EVENT_POMODORO_PAUSE = 2
EVENT_POMODORO_CANCEL = 3

EVENT_TYPE_NAMES = {
    EVENT_POMODORO_COMPLETE: "pomodoro_complete",
    EVENT_POMODORO_START: "pomodoro_start",
    EVENT_POMODORO_PAUSE: "pomodoro_pause",
    EVENT_POMODORO_CANCEL: "pomodoro_cancel",
}


class PomodoroEngine:
    """In-process pomodoro timer. Replaces the C daemon for start/pause/resume/stop and event emission."""

    def __init__(self, on_event_cb=None):
        self.logger = logging.getLogger("pomodoro")
        self.hari_dir = Path.home() / ".hari"
        self.events_log = self.hari_dir / "events.log"
        self.on_event_cb = on_event_cb
        self._lock = threading.Lock()
        self._phase = "idle"  # idle | working | paused | short_break | long_break
        self._active = False
        self._start_time_mono = 0.0  # time.monotonic() when current segment started (or would end)
        self._remaining_ms = 0
        self._duration_minutes = 25
        self._session_count = 0
        self._work_duration = 25
        self._short_break_duration = 5
        self._long_break_duration = 15
        self._sessions_until_long_break = 4
        self._auto_start_breaks = False
        self._project = ""
        self._running = True
        self._thread = None
        self._start_time_wall_ms = 0  # for event timestamp when segment started

    def get_settings(self):
        """Return current pomodoro durations for API."""
        with self._lock:
            return {
                "work_duration_minutes": self._work_duration,
                "short_break_minutes": self._short_break_duration,
                "long_break_minutes": self._long_break_duration,
                "sessions_until_long_break": self._sessions_until_long_break,
            }

    def _append_event_to_log(self, event_dict):
        self.hari_dir.mkdir(exist_ok=True)
        line = json.dumps(event_dict, separators=(",", ":")) + "\n"
        try:
            with open(self.events_log, "a") as f:
                f.write(line)
        except IOError as e:
            self.logger.warning("Failed to append to events.log: %s", e)

    def _emit(self, type_id, data=None):
        ts_ms = int(time.time() * 1000)
        event = {
            "timestamp": ts_ms,
            "type": type_id,
            "type_name": EVENT_TYPE_NAMES.get(type_id, "unknown"),
            "data": data if data is not None else {},
        }
        self._append_event_to_log(event)
        if self.on_event_cb:
            try:
                self.on_event_cb(event)
            except Exception as e:
                self.logger.error("on_event_cb error: %s", e)

    def start(self, duration_minutes=None, project=None):
        with self._lock:
            # Already running (not paused) - one timer per user, don't replace
            if self._active and self._phase in ("working", "short_break", "long_break"):
                return {"status": "error", "message": "Timer already running"}
            if self._phase == "paused":
                # Resume: restore remaining time
                self._phase = "working"
                self._active = True
                # start_time_mono set so that (now - start_time_mono) = elapsed so far, i.e. remaining = duration_ms - elapsed
                elapsed_ms = (self._duration_minutes * 60 * 1000) - self._remaining_ms
                self._start_time_mono = time.monotonic() - (elapsed_ms / 1000.0)
                self._start_time_wall_ms = int(time.time() * 1000) - int(elapsed_ms)
                self.logger.info("Pomodoro resumed (remaining %d ms)", self._remaining_ms)
                return {"status": "ok", "message": "Pomodoro resumed"}

            # New work session
            self._phase = "working"
            self._active = True
            self._duration_minutes = int(duration_minutes) if duration_minutes is not None else self._work_duration
            self._duration_minutes = max(1, min(24 * 60, self._duration_minutes))
            self._remaining_ms = self._duration_minutes * 60 * 1000
            self._start_time_mono = time.monotonic()
            self._start_time_wall_ms = int(time.time() * 1000)
            self._project = (project or "").strip()[:95]

            data = {
                "duration_minutes": self._duration_minutes,
                "phase": "work",
                "session_count": self._session_count,
            }
            if self._project:
                data["project"] = self._project
            self._emit(EVENT_POMODORO_START, data)
            self.logger.info("Pomodoro started (%d min)", self._duration_minutes)
            return {"status": "ok", "message": "Pomodoro started"}

    def pause(self):
        with self._lock:
            if not self._active or self._phase != "working":
                return {"status": "error", "message": "No active work session to pause"}
            elapsed_ms = int((time.monotonic() - self._start_time_mono) * 1000)
            duration_ms = self._duration_minutes * 60 * 1000
            self._remaining_ms = max(0, duration_ms - elapsed_ms)
            self._phase = "paused"
            self._active = False
            self._emit(EVENT_POMODORO_PAUSE, {"phase": "work"})
            self.logger.info("Pomodoro paused")
            return {"status": "ok", "message": "Pomodoro paused"}

    def resume(self):
        return self.start()

    def stop(self):
        with self._lock:
            was_active = self._active or self._phase != "idle"
            self._phase = "idle"
            self._active = False
            self._remaining_ms = 0
            self._emit(EVENT_POMODORO_CANCEL, {})
            if was_active:
                self.logger.info("Pomodoro stopped")
            return {"status": "ok", "message": "Pomodoro stopped"}

    def get_status(self):
        with self._lock:
            phase = self._phase
            active = self._active
            remaining_ms = self._remaining_ms
            duration_minutes = self._duration_minutes
            session_count = self._session_count
            project = self._project
        if phase == "idle" and not active:
            return {"status": "ok", "message": "Idle. Start a pomodoro when ready."}
        msg = f"Phase: {phase}, Session #{session_count}"
        if active and remaining_ms > 0:
            msg += f", {remaining_ms // 60000}m {(remaining_ms % 60000) // 1000}s remaining"
        elif phase == "paused":
            msg += f", {remaining_ms // 60000}m {(remaining_ms % 60000) // 1000}s remaining (paused)"
        if project:
            msg += f", project: {project}"
        return {"status": "ok", "message": msg}

    def get_structured_status(self):
        """Return structured status for frontend sync (remaining_ms, phase, etc.)."""
        with self._lock:
            phase = self._phase
            active = self._active
            remaining_ms = self._remaining_ms
            duration_minutes = self._duration_minutes
            session_count = self._session_count
            project = self._project
            work_dur = self._work_duration
            short_dur = self._short_break_duration
            long_dur = self._long_break_duration
        phase_map = {"working": "work", "short_break": "short", "long_break": "long", "paused": "paused", "idle": "idle"}
        mode = phase_map.get(phase, "idle")
        if phase == "paused":
            mode = "work" if duration_minutes == work_dur else "short" if duration_minutes == short_dur else "long"
        return {
            "phase": phase,
            "mode": mode,
            "running": active and phase in ("working", "short_break", "long_break"),
            "paused": phase == "paused",
            "remaining_ms": remaining_ms,
            "duration_minutes": duration_minutes,
            "session_count": session_count,
            "project": project or "",
            "work_duration_minutes": work_dur,
            "short_break_minutes": short_dur,
            "long_break_minutes": long_dur,
        }

    def _tick(self):
        while getattr(self, "_running", True):
            time.sleep(1.0)
            with self._lock:
                if not self._active or self._phase in ("paused", "idle"):
                    continue
                elapsed_ms = int((time.monotonic() - self._start_time_mono) * 1000)
                duration_ms = self._duration_minutes * 60 * 1000
                if elapsed_ms < duration_ms:
                    self._remaining_ms = duration_ms - elapsed_ms
                    continue
                # Segment complete
                wall_ms = int(time.time() * 1000)
                phase_name = "work" if self._phase == "working" else "break"
                data = {
                    "session_count": self._session_count,
                    "duration_minutes": self._duration_minutes,
                    "phase": phase_name,
                    "elapsed_ms": elapsed_ms,
                }
                if self._project:
                    data["project"] = self._project
                self._emit(EVENT_POMODORO_COMPLETE, data)

                if self._phase == "working":
                    self._session_count += 1
                    if self._session_count % self._sessions_until_long_break == 0:
                        self._phase = "long_break"
                        self._duration_minutes = self._long_break_duration
                    else:
                        self._phase = "short_break"
                        self._duration_minutes = self._short_break_duration
                    self._remaining_ms = self._duration_minutes * 60 * 1000
                    self._start_time_mono = time.monotonic()
                    if self._auto_start_breaks:
                        self._active = True
                    else:
                        self._active = False
                        self._phase = "idle"
                else:
                    self._phase = "idle"
                    self._active = False

    def start_background_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._running = True
            self._thread = threading.Thread(target=self._tick, daemon=True)
            self._thread.start()
            self.logger.info("Pomodoro engine started")

    def stop_background_thread(self):
        self._running = False


class AnalyticsHandler:
    """Handles analytics processing and queries"""

    def __init__(self, llm_provider=None):
        self.logger = logging.getLogger('analytics')
        self.llm_provider = llm_provider  # LLMProvider for RAG (Ollama/Bedrock)
        self.hari_dir = Path.home() / '.hari'
        self.db_path = self.hari_dir / 'analytics.db'
        self.conn = None
        self.db_lock = threading.Lock()

        self.embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
        self.embedder = None

        # Pending metadata for next pomodoro_start event (set by LLM request)
        self._pending_lock = threading.Lock()
        self._pending_project = None
        
        # Create .hari directory if needed
        self.hari_dir.mkdir(exist_ok=True)
        
        # Initialize database
        self.init_db()
    
    def init_db(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        
        # Read and execute schema
        schema_path = Path(__file__).parent / 'schema.sql'
        if not schema_path.exists():
            self.logger.warning(f"Schema file not found: {schema_path}, creating basic schema")
            self.create_basic_schema()
        else:
            with open(schema_path, 'r') as f:
                schema = f.read()
                self.conn.executescript(schema)
        
        self.conn.commit()
        self.logger.info(f"Analytics database ready: {self.db_path}")

        # Ensure memory docs schema exists (same DB)
        self.ensure_memory_schema()

        # Ensure users table exists (for frontend user management)
        self.ensure_users_schema()

        # Ensure users have password_hash column (migration)
        self.ensure_users_password_column()

        # Ensure sessions table has project column (migration)
        self.ensure_sessions_project_column()

        # Spaced repetition schema
        self.ensure_sr_schema()
        self.ensure_sr_retired_column()
        self.ensure_sr_first_due_date_column()

        # Pomodoro settings (per-user, in DB)
        self.ensure_pomodoro_settings_schema()

        # Initialize embedder (if available)
        if EMBEDDINGS_AVAILABLE:
            try:
                self.embedder = SentenceTransformer(self.embedding_model_name)
                self.logger.info(f"Memory embeddings enabled: {self.embedding_model_name}")
            except Exception as e:
                self.embedder = None
                self.logger.error(f"Failed to load embedder: {e}")
        else:
            self.logger.warning("Memory embeddings disabled (missing sentence-transformers/numpy)")

    def ensure_memory_schema(self):
        """Create memory_docs table in analytics.db if missing."""
        with self.db_lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS memory_docs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    doc_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    tags_json TEXT DEFAULT '[]',
                    embedding BLOB,
                    embedding_dim INTEGER,
                    model TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_memory_docs_ts ON memory_docs(ts_ms);
                CREATE INDEX IF NOT EXISTS idx_memory_docs_type ON memory_docs(doc_type);

                CREATE TABLE IF NOT EXISTS memory_pending (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    doc_type TEXT NOT NULL,
                    text TEXT NOT NULL,
                    meta_json TEXT DEFAULT '{}',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_memory_pending_ts ON memory_pending(ts_ms);

                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    target_minutes_per_day INTEGER NOT NULL,
                    label TEXT,
                    raw_text TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_goals_ts ON goals(ts_ms);
                CREATE INDEX IF NOT EXISTS idx_goals_active ON goals(active);

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL CHECK(source_type IN ('website', 'document')),
                    url TEXT,
                    title TEXT,
                    status TEXT DEFAULT 'crawled',
                    pages_crawled INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_sources(source_type);
            """)
            self.conn.commit()

    def ensure_users_schema(self):
        """Create users table if missing (no-op; table created in ensure_memory_schema block)."""
        pass

    def ensure_users_password_column(self):
        """Add password_hash column to users if missing."""
        with self.db_lock:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(users)").fetchall()]
            if "password_hash" not in cols:
                self.logger.info("Migrating users table: adding password_hash column")
                self.conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
                self.conn.commit()

    def list_users(self):
        """Return all users as list of dicts."""
        with self.db_lock:
            cur = self.conn.execute(
                "SELECT id, name, email, created_at, updated_at FROM users ORDER BY id"
            )
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "email": r["email"] or "",
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in cur.fetchall()
            ]

    def get_user(self, user_id: int):
        """Return one user or None."""
        with self.db_lock:
            cur = self.conn.execute(
                "SELECT id, name, email, created_at, updated_at FROM users WHERE id = ?",
                (user_id,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "name": r["name"],
                "email": r["email"] or "",
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }

    def get_user_by_email(self, email: str):
        """Return user by email or None."""
        email = (email or "").strip().lower()
        if not email:
            return None
        with self.db_lock:
            cur = self.conn.execute(
                "SELECT id, name, email, password_hash, created_at, updated_at FROM users WHERE LOWER(email) = ?",
                (email,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return dict(r)

    def create_user(self, name: str, email: str = "", password: str = None):
        """Insert user; return new user dict."""
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        email = (email or "").strip()
        if password and not email:
            raise ValueError("email is required for registration")
        if email and self.get_user_by_email(email):
            raise ValueError("email already registered")
        password_hash = None
        if password and AUTH_AVAILABLE:
            pw_bytes = password.encode("utf-8")[:72]  # bcrypt limit
            password_hash = bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12)).decode("ascii")
        with self.db_lock:
            self.conn.execute(
                "INSERT INTO users (name, email, password_hash, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (name, email, password_hash),
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return self.get_user(row_id)

    def update_user(self, user_id: int, name: str = None, email: str = None):
        """Update user; return updated user dict or None."""
        u = self.get_user(user_id)
        if not u:
            return None
        name = (name or u["name"] or "").strip()
        email = (email if email is not None else u["email"] or "").strip()
        with self.db_lock:
            self.conn.execute(
                "UPDATE users SET name = ?, email = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, email, user_id),
            )
            self.conn.commit()
        return self.get_user(user_id)

    def delete_user(self, user_id: int):
        """Delete user; return True if deleted."""
        with self.db_lock:
            cur = self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def verify_user_password(self, email: str, password: str):
        """Verify credentials; return user dict (without password_hash) or None."""
        u = self.get_user_by_email(email)
        if not u or not password or not AUTH_AVAILABLE:
            return None
        pw_hash = u.get("password_hash")
        if not pw_hash:
            return None
        pw_bytes = password.encode("utf-8")[:72]  # bcrypt limit
        if not bcrypt.checkpw(pw_bytes, pw_hash.encode("ascii")):
            return None
        return {k: v for k, v in u.items() if k != "password_hash"}

    def list_knowledge_sources(self, source_type: str = None):
        """List knowledge sources (websites/documents)."""
        with self.db_lock:
            if source_type:
                cur = self.conn.execute(
                    "SELECT id, source_type, url, title, status, pages_crawled, created_at FROM knowledge_sources WHERE source_type = ? ORDER BY id DESC",
                    (source_type,),
                )
            else:
                cur = self.conn.execute(
                    "SELECT id, source_type, url, title, status, pages_crawled, created_at FROM knowledge_sources ORDER BY id DESC"
                )
            return [
                {
                    "id": r["id"],
                    "source_type": r["source_type"],
                    "url": r["url"] or "",
                    "title": r["title"] or "",
                    "status": r["status"] or "crawled",
                    "pages_crawled": r["pages_crawled"] or 0,
                    "created_at": r["created_at"],
                }
                for r in cur.fetchall()
            ]

    def add_knowledge_source(self, source_type: str, url: str = None, title: str = None):
        """Add website or document to knowledge base."""
        source_type = (source_type or "website").lower()
        if source_type not in ("website", "document"):
            raise ValueError("source_type must be 'website' or 'document'")
        url = (url or "").strip()
        if not title:
            if url:
                try:
                    from urllib.parse import urlparse
                    p = urlparse(url)
                    base = p.netloc or p.path or "Untitled"
                    title = base.replace("www.", "")[:100]
                    if p.path and p.path != "/":
                        title = (p.path.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").title() or title)
                except Exception:
                    title = url[:255]
            else:
                title = "Untitled"
        title = (title or "Untitled")[:255]
        with self.db_lock:
            self.conn.execute(
                "INSERT INTO knowledge_sources (source_type, url, title, status, pages_crawled) VALUES (?, ?, ?, 'crawled', ?)",
                (source_type, url if url else None, title, 1 if url else 0),
            )
            self.conn.commit()
            row_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            row = self.conn.execute(
                "SELECT id, source_type, url, title, status, pages_crawled, created_at FROM knowledge_sources WHERE id = ?",
                (row_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_knowledge_source(self, source_id: int):
        """Delete a knowledge source."""
        with self.db_lock:
            cur = self.conn.execute("DELETE FROM knowledge_sources WHERE id = ?", (source_id,))
            self.conn.commit()
            return cur.rowcount > 0

    _SR_INTERVALS = [1, 3, 7, 14]

    def _sr_next_interval(self, current_days: int, difficulty: str) -> int:
        """Compute next interval from difficulty. easy=+2 steps, medium=+1, hard=-1."""
        try:
            idx = self._SR_INTERVALS.index(current_days)
        except ValueError:
            idx = 0
        if difficulty == "easy":
            idx = min(len(self._SR_INTERVALS) - 1, idx + 2)
        elif difficulty == "medium":
            idx = min(len(self._SR_INTERVALS) - 1, idx + 1)
        else:
            idx = max(0, idx - 1)
        return self._SR_INTERVALS[idx]

    def sr_list_topics(self, user_id: int):
        """List all topics for user, with last_reviewed and next_interval_days from latest review."""
        with self.db_lock:
            self.conn.row_factory = sqlite3.Row
            row = self.conn.execute("PRAGMA table_info(sr_topics)").fetchall()
            has_first_due = any(r[1] == "first_due_date" for r in row)
            extra = ", t.first_due_date" if has_first_due else ""
            rows = self.conn.execute(
                f"""SELECT t.id, t.user_id, t.name, t.estimated_minutes, t.created_at{extra},
                   (SELECT reviewed_at FROM sr_reviews WHERE topic_id = t.id AND user_id = t.user_id ORDER BY id DESC LIMIT 1) as last_reviewed,
                   COALESCE((SELECT next_interval_days FROM sr_reviews WHERE topic_id = t.id AND user_id = t.user_id ORDER BY id DESC LIMIT 1), 1) as next_interval_days,
                   (SELECT show_again_date FROM sr_skip_overrides WHERE user_id = t.user_id AND topic_id = t.id) as skip_show_again_date
                   FROM sr_topics t WHERE t.user_id = ? AND t.retired_at IS NULL ORDER BY t.name""",
                (user_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("next_interval_days") is not None:
                    d["next_interval_days"] = int(d["next_interval_days"])
                result.append(d)
            return result

    def sr_create_topic(self, user_id: int, name: str, estimated_minutes: int = 60, first_due_date: str = None):
        """Create a topic. Manual add: first_due_date=None means due today. Bulk: pass first_due_date to pre-schedule."""
        name = (name or "").strip()[:200]
        if not name:
            raise ValueError("Topic name required")
        estimated_minutes = max(1, min(480, int(estimated_minutes or 60)))
        with self.db_lock:
            row = self.conn.execute("PRAGMA table_info(sr_topics)").fetchall()
            has_first_due = any(r[1] == "first_due_date" for r in row)
            if has_first_due and first_due_date:
                self.conn.execute(
                    "INSERT INTO sr_topics (user_id, name, estimated_minutes, first_due_date) VALUES (?, ?, ?, ?)",
                    (user_id, name, estimated_minutes, first_due_date),
                )
            else:
                self.conn.execute(
                    "INSERT INTO sr_topics (user_id, name, estimated_minutes) VALUES (?, ?, ?)",
                    (user_id, name, estimated_minutes),
                )
            self.conn.commit()
            rid = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            self._sr_ensure_today_task(user_id, rid, lock_held=True)
            sel = "SELECT id, user_id, name, estimated_minutes, created_at"
            if has_first_due:
                sel += ", first_due_date"
            row = self.conn.execute(f"{sel} FROM sr_topics WHERE id = ?", (rid,)).fetchone()
            return dict(row) if row else None

    def _sr_ensure_today_task(self, user_id: int, topic_id: int, *, lock_held: bool = False):
        """Ensure today's task entry exists for (user, topic). Caller must hold db_lock if lock_held=True."""
        today = datetime.now().strftime("%Y-%m-%d")

        def _do():
            self.conn.execute(
                """INSERT INTO sr_daily_tasks (user_id, topic_id, date, completed)
                   VALUES (?, ?, ?, 0) ON CONFLICT(user_id, topic_id, date) DO NOTHING""",
                (user_id, topic_id, today),
            )
            self.conn.commit()

        if lock_held:
            _do()
        else:
            with self.db_lock:
                _do()

    def sr_update_topic(self, user_id: int, topic_id: int, name: str = None, estimated_minutes: int = None):
        """Update topic. Returns updated topic or None."""
        with self.db_lock:
            row = self.conn.execute(
                "SELECT id, user_id, name, estimated_minutes FROM sr_topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            ).fetchone()
            if not row:
                return None
            updates = []
            params = []
            if name is not None:
                updates.append("name = ?")
                params.append((name or "").strip()[:200])
            if estimated_minutes is not None:
                updates.append("estimated_minutes = ?")
                params.append(max(1, min(480, int(estimated_minutes))))
            if not updates:
                return dict(row)
            params.append(topic_id)
            self.conn.execute(
                f"UPDATE sr_topics SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT id, user_id, name, estimated_minutes, created_at FROM sr_topics WHERE id = ?",
                (topic_id,),
            ).fetchone()
            return dict(row) if row else None

    def sr_delete_topic(self, user_id: int, topic_id: int) -> bool:
        """Delete topic and its reviews."""
        with self.db_lock:
            cur = self.conn.execute("DELETE FROM sr_reviews WHERE topic_id = ? AND user_id = ?", (topic_id, user_id))
            cur = self.conn.execute("DELETE FROM sr_topics WHERE id = ? AND user_id = ?", (topic_id, user_id))
            self.conn.commit()
            return cur.rowcount > 0

    def sr_delete_all_topics(self, user_id: int) -> int:
        """Delete all SR topics for user. Clears schedule and task list; preserves completion history (reviews, daily_tasks for streak)."""
        with self.db_lock:
            topics = self.conn.execute(
                "SELECT id FROM sr_topics WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            topic_ids = [r[0] for r in topics]
            if not topic_ids:
                return 0
            placeholders = ",".join("?" * len(topic_ids))
            # Clear schedule overrides only (skips, skip_until)
            self.conn.execute(
                f"DELETE FROM sr_daily_skips WHERE topic_id IN ({placeholders}) AND user_id = ?",
                topic_ids + [user_id],
            )
            self.conn.execute(
                f"DELETE FROM sr_skip_overrides WHERE topic_id IN ({placeholders}) AND user_id = ?",
                topic_ids + [user_id],
            )
            # Delete topics; keep sr_reviews and sr_daily_tasks for completion history / streak
            cur = self.conn.execute("DELETE FROM sr_topics WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return cur.rowcount

    def sr_skip_topic_today(self, user_id: int, topic_id: int) -> bool:
        """Mark topic as skipped for today. Does not alter schedule. Returns True if recorded."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.db_lock:
            row = self.conn.execute(
                "SELECT id FROM sr_topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            ).fetchone()
            if not row:
                return False
            self.conn.execute(
                "INSERT OR IGNORE INTO sr_daily_skips (user_id, topic_id, date) VALUES (?, ?, ?)",
                (user_id, topic_id, today),
            )
            self.conn.commit()
            return True

    def sr_retire_topic(self, user_id: int, topic_id: int) -> bool:
        """Mark topic as done completely. Excludes from practice. Returns True if updated."""
        with self.db_lock:
            row = self.conn.execute(
                "SELECT id FROM sr_topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            ).fetchone()
            if not row:
                return False
            self.conn.execute(
                "UPDATE sr_topics SET retired_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            )
            self.conn.commit()
            return True

    def sr_skip_topic_until(self, user_id: int, topic_id: int, days: int) -> bool:
        """Skip topic and set it to show again in N days. Clears daily skip for today. Returns True if recorded."""
        if days not in (1, 3, 7, 14):
            raise ValueError("days must be 1, 3, 7, or 14")
        today_d = datetime.now().date()
        show_again = (today_d + timedelta(days=days)).strftime("%Y-%m-%d")
        with self.db_lock:
            row = self.conn.execute(
                "SELECT id FROM sr_topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            ).fetchone()
            if not row:
                return False
            self.conn.execute(
                """INSERT INTO sr_skip_overrides (user_id, topic_id, show_again_date)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, topic_id) DO UPDATE SET show_again_date = excluded.show_again_date""",
                (user_id, topic_id, show_again),
            )
            self.conn.execute(
                "DELETE FROM sr_daily_skips WHERE user_id = ? AND topic_id = ? AND date = ?",
                (user_id, topic_id, today_d.strftime("%Y-%m-%d")),
            )
            self.conn.commit()
            return True

    def _sr_compute_first_due_dates(
        self, items: list, daily_capacity_minutes: int
    ) -> list:
        """Given items with estimated_minutes, return list of (index, first_due_date) in YYYY-MM-DD.
        Uses strict capacity-aware scheduling - no overflow."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_d = datetime.now().date()
        day_minutes = {}

        def get_day_mins(d):
            return day_minutes.get(d, 0)

        def add_to_day(d, mins):
            day_minutes[d] = get_day_mins(d) + mins

        result = []
        cap = daily_capacity_minutes
        for i, item in enumerate(items):
            mins = int(item.get("estimated_minutes") or 60)
            d = today
            if mins <= cap:
                while get_day_mins(d) + mins > cap:
                    next_d = datetime.strptime(d, "%Y-%m-%d").date() + timedelta(days=1)
                    d = next_d.strftime("%Y-%m-%d")
            add_to_day(d, mins)
            result.append((i, d))
        return result

    def sr_get_due_today(self, user_id: int) -> list:
        """Topics due for review today.
        - Bulk-imported (first_due_date set): only when first_due_date=today or next review=today.
        - Manual adds (first_due_date null): all due topics, no capacity limit."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self.db_lock:
            self.conn.row_factory = sqlite3.Row
            row = self.conn.execute(
                "PRAGMA table_info(sr_topics)"
            ).fetchall()
            has_first_due = any(r[1] == "first_due_date" for r in row)
            cols = "id, user_id, name, estimated_minutes, created_at"
            if has_first_due:
                cols += ", first_due_date"
            topics = self.conn.execute(
                f"SELECT {cols} FROM sr_topics WHERE user_id = ? AND retired_at IS NULL ORDER BY name",
                (user_id,),
            ).fetchall()
            result = []
            for t in topics:
                skipped = self.conn.execute(
                    "SELECT 1 FROM sr_daily_skips WHERE user_id = ? AND topic_id = ? AND date = ?",
                    (user_id, t["id"], today),
                ).fetchone()
                if skipped:
                    continue
                override = self.conn.execute(
                    "SELECT show_again_date FROM sr_skip_overrides WHERE user_id = ? AND topic_id = ?",
                    (user_id, t["id"]),
                ).fetchone()
                if override and override["show_again_date"] > today:
                    continue
                tdict = dict(t)
                first_due = tdict.get("first_due_date") if has_first_due else None
                last = self.conn.execute(
                    "SELECT reviewed_at, next_interval_days FROM sr_reviews WHERE topic_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                    (t["id"], user_id),
                ).fetchone()

                if not last:
                    # Never reviewed
                    if first_due:
                        due = first_due == today
                    else:
                        due = True  # Manual add: always due
                else:
                    last_d = datetime.strptime(last["reviewed_at"], "%Y-%m-%d").date()
                    next_d = last_d + timedelta(days=int(last["next_interval_days"]))
                    due = next_d <= datetime.now().date()

                if due:
                    self._sr_ensure_today_task(user_id, t["id"], lock_held=True)
                    task = self.conn.execute(
                        "SELECT completed FROM sr_daily_tasks WHERE user_id = ? AND topic_id = ? AND date = ?",
                        (user_id, t["id"], today),
                    ).fetchone()
                    tdict["last_reviewed"] = last["reviewed_at"] if last else None
                    tdict["next_interval_days"] = int(last["next_interval_days"]) if last else 1
                    tdict["skip_show_again_date"] = override["show_again_date"] if override else None
                    tdict["completed"] = bool(task and task["completed"])
                    result.append(tdict)
            return result

    def _sr_compute_streak(self, user_id: int, *, lock_held: bool = False) -> dict:
        """Compute current_streak and longest_streak from completed daily tasks. Caller holds db_lock if lock_held."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_d = datetime.now().date()

        def _do():
            rows = self.conn.execute(
                """SELECT DISTINCT date FROM sr_daily_tasks
                   WHERE user_id = ? AND completed = 1 ORDER BY date DESC""",
                (user_id,),
            ).fetchall()
            dates = [r[0] for r in rows]
            if not dates:
                return {"current_streak": 0, "longest_streak": 0}

            most_recent = datetime.strptime(dates[0], "%Y-%m-%d").date()
            # Streak is alive only if most recent activity is today or yesterday
            if (today_d - most_recent).days > 1:
                current = 0
            else:
                # Count consecutive days backwards from most_recent
                current = 1
                prev = most_recent
                for dstr in dates[1:]:
                    d = datetime.strptime(dstr, "%Y-%m-%d").date()
                    if (prev - d).days == 1:
                        current += 1
                        prev = d
                    else:
                        break

            # Longest streak: find max consecutive run
            longest = 1
            run = 1
            for i in range(1, len(dates)):
                curr_d = datetime.strptime(dates[i], "%Y-%m-%d").date()
                prev_d = datetime.strptime(dates[i - 1], "%Y-%m-%d").date()
                if (prev_d - curr_d).days == 1:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 1
            return {"current_streak": current, "longest_streak": max(longest, current)}

        if lock_held:
            return _do()
        with self.db_lock:
            return _do()

    def sr_get_streak(self, user_id: int) -> dict:
        """Return current_streak and longest_streak for SR practice."""
        return self._sr_compute_streak(user_id)

    def sr_complete_task(self, user_id: int, project: str, difficulty: str = None) -> tuple[bool, dict]:
        """Mark today's task as completed. If difficulty (easy/medium/hard) provided, record review first to adjust schedule. Returns (updated, streak)."""
        if not (project or "").strip():
            return False, self._sr_compute_streak(user_id)
        difficulty = (difficulty or "").strip().lower() or None
        if difficulty and difficulty not in ("easy", "medium", "hard"):
            difficulty = None
        today = datetime.now().strftime("%Y-%m-%d")
        with self.db_lock:
            row = self.conn.execute(
                "SELECT id FROM sr_topics WHERE user_id = ? AND LOWER(TRIM(name)) = LOWER(TRIM(?))",
                (user_id, project.strip()),
            ).fetchone()
            if not row:
                return False, self._sr_compute_streak(user_id, lock_held=True)
            topic_id = row[0]
            if difficulty:
                self.sr_record_review(user_id, topic_id, difficulty, lock_held=True)
            self.conn.execute(
                """INSERT INTO sr_daily_tasks (user_id, topic_id, date, completed)
                   VALUES (?, ?, ?, 1) ON CONFLICT(user_id, topic_id, date) DO UPDATE SET completed = 1""",
                (user_id, topic_id, today),
            )
            self.conn.commit()
            streak = self._sr_compute_streak(user_id, lock_held=True)
            return True, streak

    def sr_record_review(self, user_id: int, topic_id: int, difficulty: str, *, lock_held: bool = False) -> dict:
        """Record a review. difficulty: easy, medium, hard. Returns updated topic with next_due."""
        if difficulty not in ("easy", "medium", "hard"):
            raise ValueError("difficulty must be easy, medium, or hard")
        today = datetime.now().strftime("%Y-%m-%d")

        def _do():
            row = self.conn.execute(
                "SELECT id, user_id, name FROM sr_topics WHERE id = ? AND user_id = ?",
                (topic_id, user_id),
            ).fetchone()
            if not row:
                return None
            last = self.conn.execute(
                "SELECT next_interval_days FROM sr_reviews WHERE topic_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (topic_id, user_id),
            ).fetchone()
            current_interval = int(last["next_interval_days"]) if last else 1
            next_days = self._sr_next_interval(current_interval, difficulty)
            self.conn.execute(
                "INSERT INTO sr_reviews (topic_id, user_id, reviewed_at, difficulty, next_interval_days) VALUES (?, ?, ?, ?, ?)",
                (topic_id, user_id, today, difficulty, next_days),
            )
            # Clear any skip override when user completes a review
            self.conn.execute("DELETE FROM sr_skip_overrides WHERE user_id = ? AND topic_id = ?", (user_id, topic_id))
            self.conn.commit()
            return {
                "topic_id": topic_id,
                "reviewed_at": today,
                "difficulty": difficulty,
                "next_interval_days": next_days,
            }

        if lock_held:
            return _do()
        with self.db_lock:
            return _do()

    def sr_get_settings(self, user_id: int) -> dict:
        """Get SR settings for user."""
        with self.db_lock:
            row = self.conn.execute(
                "SELECT user_id, daily_capacity_minutes, created_at, updated_at FROM sr_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return {"user_id": row["user_id"], "daily_capacity_minutes": row["daily_capacity_minutes"] or 120}
            return {"user_id": user_id, "daily_capacity_minutes": 120}

    def sr_update_settings(self, user_id: int, daily_capacity_minutes: int = None) -> dict:
        """Update SR settings."""
        if daily_capacity_minutes is not None:
            daily_capacity_minutes = max(15, min(720, int(daily_capacity_minutes)))
        with self.db_lock:
            self.conn.execute(
                """INSERT INTO sr_settings (user_id, daily_capacity_minutes, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(user_id) DO UPDATE SET
                     daily_capacity_minutes = COALESCE(?, daily_capacity_minutes),
                     updated_at = CURRENT_TIMESTAMP""",
                (user_id, daily_capacity_minutes or 120, daily_capacity_minutes),
            )
            self.conn.commit()
            # Read inline; do not call sr_get_settings (would deadlock)
            row = self.conn.execute(
                "SELECT user_id, daily_capacity_minutes FROM sr_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return {"user_id": row[0], "daily_capacity_minutes": (row[1] or 120)}
            return {"user_id": user_id, "daily_capacity_minutes": 120}

    def ensure_sr_schema(self):
        """Create spaced repetition tables if missing."""
        with self.db_lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS sr_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    estimated_minutes INTEGER DEFAULT 60,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_sr_topics_user ON sr_topics(user_id);

                CREATE TABLE IF NOT EXISTS sr_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    difficulty TEXT NOT NULL CHECK(difficulty IN ('easy', 'medium', 'hard')),
                    next_interval_days INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (topic_id) REFERENCES sr_topics(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sr_reviews_topic ON sr_reviews(topic_id);
                CREATE INDEX IF NOT EXISTS idx_sr_reviews_user ON sr_reviews(user_id);

                CREATE TABLE IF NOT EXISTS sr_settings (
                    user_id INTEGER PRIMARY KEY,
                    daily_capacity_minutes INTEGER DEFAULT 120,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS sr_daily_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    topic_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    completed INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, topic_id, date),
                    FOREIGN KEY (topic_id) REFERENCES sr_topics(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sr_daily_tasks_user_date ON sr_daily_tasks(user_id, date);

                CREATE TABLE IF NOT EXISTS sr_daily_skips (
                    user_id INTEGER NOT NULL,
                    topic_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, topic_id, date),
                    FOREIGN KEY (topic_id) REFERENCES sr_topics(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sr_daily_skips_user_date ON sr_daily_skips(user_id, date);

                CREATE TABLE IF NOT EXISTS sr_skip_overrides (
                    user_id INTEGER NOT NULL,
                    topic_id INTEGER NOT NULL,
                    show_again_date TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, topic_id),
                    FOREIGN KEY (topic_id) REFERENCES sr_topics(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sr_skip_overrides_user ON sr_skip_overrides(user_id);
            """)
            self.conn.commit()

    def ensure_sr_retired_column(self):
        """Add retired_at to sr_topics if missing (migration)."""
        with self.db_lock:
            row = self.conn.execute("PRAGMA table_info(sr_topics)").fetchall()
            cols = [r[1] for r in row]
            if "retired_at" not in cols:
                self.conn.execute("ALTER TABLE sr_topics ADD COLUMN retired_at DATETIME DEFAULT NULL")
                self.conn.commit()

    def ensure_sr_first_due_date_column(self):
        """Add first_due_date to sr_topics if missing (migration). Bulk-imported topics get pre-scheduled."""
        with self.db_lock:
            row = self.conn.execute("PRAGMA table_info(sr_topics)").fetchall()
            cols = [r[1] for r in row]
            if "first_due_date" not in cols:
                self.conn.execute("ALTER TABLE sr_topics ADD COLUMN first_due_date TEXT DEFAULT NULL")
                self.conn.commit()

    def ensure_pomodoro_settings_schema(self):
        """Create pomodoro_settings table for per-user preferences."""
        with self.db_lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS pomodoro_settings (
                    user_id INTEGER PRIMARY KEY,
                    work_duration_minutes INTEGER DEFAULT 25,
                    short_break_minutes INTEGER DEFAULT 5,
                    long_break_minutes INTEGER DEFAULT 15,
                    sessions_until_long_break INTEGER DEFAULT 4,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            """)
            self.conn.commit()

    def get_pomodoro_settings(self, user_id: int) -> dict:
        """Get pomodoro settings for user. Returns defaults if not set."""
        with self.db_lock:
            row = self.conn.execute(
                """SELECT user_id, work_duration_minutes, short_break_minutes, long_break_minutes,
                          sessions_until_long_break FROM pomodoro_settings WHERE user_id = ?""",
                (user_id,),
            ).fetchone()
            if row:
                return {
                    "work_duration_minutes": int(row[1] or 25),
                    "short_break_minutes": int(row[2] or 5),
                    "long_break_minutes": int(row[3] or 15),
                    "sessions_until_long_break": int(row[4] or 4),
                }
            return {
                "work_duration_minutes": 25,
                "short_break_minutes": 5,
                "long_break_minutes": 15,
                "sessions_until_long_break": 4,
            }

    def update_pomodoro_settings(
        self, user_id: int,
        work_duration_minutes: int = None,
        short_break_minutes: int = None,
        long_break_minutes: int = None,
        sessions_until_long_break: int = None,
    ) -> dict:
        """Update pomodoro settings for user. Returns updated settings."""
        updates = []
        params = []
        if work_duration_minutes is not None:
            v = max(1, min(24 * 60, int(work_duration_minutes)))
            updates.append("work_duration_minutes = ?")
            params.append(v)
        if short_break_minutes is not None:
            v = max(1, min(60, int(short_break_minutes)))
            updates.append("short_break_minutes = ?")
            params.append(v)
        if long_break_minutes is not None:
            v = max(1, min(60, int(long_break_minutes)))
            updates.append("long_break_minutes = ?")
            params.append(v)
        if sessions_until_long_break is not None:
            v = max(1, min(20, int(sessions_until_long_break)))
            updates.append("sessions_until_long_break = ?")
            params.append(v)
        if not updates:
            return self.get_pomodoro_settings(user_id)
        with self.db_lock:
            self.conn.execute(
                f"""INSERT INTO pomodoro_settings (user_id, work_duration_minutes, short_break_minutes,
                    long_break_minutes, sessions_until_long_break, updated_at)
                    VALUES (?, 25, 5, 15, 4, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                    {", ".join(updates)}, updated_at = CURRENT_TIMESTAMP""",
                [user_id] + params,
            )
            self.conn.commit()
            # Read inline; do not call get_pomodoro_settings (would deadlock: same thread re-acquiring Lock)
            row = self.conn.execute(
                """SELECT user_id, work_duration_minutes, short_break_minutes, long_break_minutes,
                          sessions_until_long_break FROM pomodoro_settings WHERE user_id = ?""",
                (user_id,),
            ).fetchone()
            if row:
                return {
                    "work_duration_minutes": int(row[1] or 25),
                    "short_break_minutes": int(row[2] or 5),
                    "long_break_minutes": int(row[3] or 15),
                    "sessions_until_long_break": int(row[4] or 4),
                }
            return {
                "work_duration_minutes": 25,
                "short_break_minutes": 5,
                "long_break_minutes": 15,
                "sessions_until_long_break": 4,
            }

    def ensure_sessions_project_column(self):
        """SQLite migration: add sessions.project column if missing."""
        with self.db_lock:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(sessions)").fetchall()]
            if "project" not in cols:
                self.logger.info("Migrating sessions table: adding project column")
                self.conn.execute("ALTER TABLE sessions ADD COLUMN project TEXT")
                self.conn.commit()

    def set_pending_project(self, project: str):
        project = (project or "").strip()
        if not project:
            return
        # normalize to a stable key for filtering
        project_norm = re.sub(r"\s+", " ", project).strip().lower()
        with self._pending_lock:
            self._pending_project = project_norm

    def pop_pending_project(self):
        with self._pending_lock:
            p = self._pending_project
            self._pending_project = None
            return p

    def _embed_text(self, text: str):
        """Return normalized float32 embedding vector or None."""
        if not self.embedder or not EMBEDDINGS_AVAILABLE:
            return None
        try:
            vec = self.embedder.encode([text], normalize_embeddings=True)[0]
            return vec.astype(np.float32)
        except Exception as e:
            self.logger.error(f"Embedding failed: {e}")
            return None

    def add_memory_doc(self, doc_type: str, text: str, tags=None, ts_ms=None):
        """Insert a memory document (note/checkin/review/goal) and store embedding."""
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)  # wall clock for memory
        if tags is None:
            tags = []

        emb = self._embed_text(text)
        emb_blob = emb.tobytes() if emb is not None else None
        emb_dim = int(emb.shape[0]) if emb is not None else None
        model = self.embedding_model_name if emb is not None else None

        with self.db_lock:
            self.conn.execute(
                """
                INSERT INTO memory_docs (ts_ms, doc_type, text, tags_json, embedding, embedding_dim, model)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ts_ms, doc_type, text, json.dumps(tags), emb_blob, emb_dim, model),
            )
            self.conn.commit()

    def _parse_goal_target_minutes(self, raw_text: str):
        """
        Parse a goal like:
        - "4 hours a day"
        - "2h/day"
        - "120 minutes daily"
        Returns (minutes_per_day, label_or_none).
        """
        t = (raw_text or "").strip()
        if not t:
            return None, None

        lower = t.lower()

        # Try to infer a label/project if user says "work on X for ..."
        label = None
        m_label = re.search(r"work on\s+([a-z0-9 _-]+?)\s+for\s+(\d+)", lower)
        if m_label:
            label = m_label.group(1).strip() or None

        # Hours patterns
        m = re.search(r"(\d+(?:\.\d+)?)\s*(hours|hour|hrs|hr|h)\b", lower)
        if m:
            hours = float(m.group(1))
            minutes = int(round(hours * 60))
            if minutes <= 0:
                return None, label
            return minutes, label

        # Minutes patterns
        m = re.search(r"(\d+)\s*(minutes|minute|mins|min|m)\b", lower)
        if m:
            minutes = int(m.group(1))
            if minutes <= 0:
                return None, label
            return minutes, label

        return None, label

    def set_structured_goal(self, raw_text: str):
        """
        Set the active daily focus goal. Stores a structured numeric target in goals table
        and also stores the raw goal text in memory_docs for retrieval/history.
        """
        if not raw_text or not raw_text.strip():
            return False, "Goal text is empty."

        minutes, label = self._parse_goal_target_minutes(raw_text)
        if minutes is None:
            return False, (
                "Couldn't parse a numeric goal from that. Try something like "
                "'goal 4 hours a day' or 'goal 120 minutes daily'."
            )

        ts_ms = int(time.time() * 1000)

        with self.db_lock:
            # Add new goal (multiple goals can be active concurrently)
            self.conn.execute(
                "INSERT INTO goals (ts_ms, target_minutes_per_day, label, raw_text, active) VALUES (?, ?, ?, ?, 1)",
                (ts_ms, minutes, label, raw_text.strip()),
            )
            self.conn.commit()

        # Keep human-readable goal in memories (for RAG / history)
        self.add_memory_doc("goal", raw_text.strip(), tags=["goal"])

        return True, f"Saved goal: {minutes} minutes/day" + (f" ({label})" if label else "") + "."

    def get_active_goal(self):
        """Return the single most recently added active goal (backward compat)."""
        goals = self.get_active_goals()
        return goals[0] if goals else None

    def get_active_goals(self):
        """Return all active goals (multiple goals can be active concurrently)."""
        with self.db_lock:
            rows = self.conn.execute(
                "SELECT id, ts_ms, target_minutes_per_day, label, raw_text FROM goals WHERE active = 1 ORDER BY ts_ms DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "ts_ms": row["ts_ms"],
                "target_minutes_per_day": row["target_minutes_per_day"],
                "label": row["label"],
                "raw_text": row["raw_text"],
            }
            for row in rows
        ]

    def goal_status_today(self):
        goals = self.get_active_goals()
        if not goals:
            return "You don't have a structured daily goal yet. Set one like: `hari goal 4 hours a day`."

        today = self.get_daily_summary()
        worked = int((today or {}).get("total_work_minutes") or 0)
        lines = []
        all_met = True
        for g in goals:
            target = int(g["target_minutes_per_day"])
            remaining = max(0, target - worked)
            pct = int(round((worked / target) * 100)) if target > 0 else 0
            label = (g.get("label") or g.get("raw_text") or "").strip() or f"{target} min"
            if worked >= target:
                lines.append(f"✅ {label}: {worked} min ({pct}%)")
            else:
                all_met = False
                lines.append(f"📌 {label}: {worked}/{target} min — {remaining} to go")
        if all_met:
            return "✅ All goals met today.\n" + "\n".join(lines)
        return "\n".join(lines) + "\n\nNext: start a short session to close the gap."

    def list_memories(self, limit: int = 20, doc_types=None):
        """List recent memory docs (without embeddings)."""
        params = []
        where = "1=1"
        if doc_types:
            where = "doc_type IN ({})".format(",".join(["?"] * len(doc_types)))
            params.extend(doc_types)

        with self.db_lock:
            rows = list(
                self.conn.execute(
                    f"SELECT id, ts_ms, doc_type, text FROM memory_docs WHERE {where} ORDER BY ts_ms DESC LIMIT ?",
                    params + [limit],
                )
            )
        return [{"id": r["id"], "ts_ms": r["ts_ms"], "doc_type": r["doc_type"], "text": r["text"]} for r in rows]

    def forget_memory_by_id(self, memory_id: int):
        with self.db_lock:
            cur = self.conn.execute("DELETE FROM memory_docs WHERE id = ?", (memory_id,))
            self.conn.commit()
            return cur.rowcount

    def forget_memory_by_substring(self, needle: str, limit: int = 20):
        """Forget up to limit memories containing needle (case-insensitive)."""
        needle_l = needle.lower()
        with self.db_lock:
            rows = list(
                self.conn.execute(
                    "SELECT id FROM memory_docs WHERE LOWER(text) LIKE ? ORDER BY ts_ms DESC LIMIT ?",
                    (f"%{needle_l}%", limit),
                )
            )
            ids = [r["id"] for r in rows]
            if not ids:
                return 0
            q = "DELETE FROM memory_docs WHERE id IN ({})".format(",".join(["?"] * len(ids)))
            cur = self.conn.execute(q, ids)
            self.conn.commit()
            return cur.rowcount

    def get_latest_profile_field(self, field: str):
        """Return the latest stored profile field value if present."""
        prefix = f"{field}:"
        with self.db_lock:
            row = self.conn.execute(
                "SELECT text FROM memory_docs WHERE doc_type = 'profile' AND text LIKE ? ORDER BY ts_ms DESC LIMIT 1",
                (prefix + "%",),
            ).fetchone()
        if not row:
            return None
        val = row["text"][len(prefix):].strip()
        return val or None

    def add_pending_memory(self, doc_type: str, text: str, meta=None, ts_ms=None):
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)
        if meta is None:
            meta = {}
        with self.db_lock:
            cur = self.conn.execute(
                "INSERT INTO memory_pending (ts_ms, doc_type, text, meta_json) VALUES (?, ?, ?, ?)",
                (ts_ms, doc_type, text, json.dumps(meta)),
            )
            self.conn.commit()
            return cur.lastrowid

    def pop_latest_pending(self):
        """Pop the latest pending memory; returns dict or None."""
        with self.db_lock:
            row = self.conn.execute(
                "SELECT id, ts_ms, doc_type, text, meta_json FROM memory_pending ORDER BY ts_ms DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            self.conn.execute("DELETE FROM memory_pending WHERE id = ?", (row["id"],))
            self.conn.commit()
        return {
            "id": row["id"],
            "ts_ms": row["ts_ms"],
            "doc_type": row["doc_type"],
            "text": row["text"],
            "meta": json.loads(row["meta_json"] or "{}"),
        }

    def clear_pending(self):
        with self.db_lock:
            self.conn.execute("DELETE FROM memory_pending")
            self.conn.commit()

    def search_memory(self, query: str, k: int = 5, days: int = 30, doc_types=None):
        """Semantic search over memory_docs; returns top-k with scores. Requires embeddings."""
        since_ms = int(time.time() * 1000) - days * 24 * 60 * 60 * 1000

        if not self.embedder or not EMBEDDINGS_AVAILABLE:
            return []

        q = self._embed_text(query)
        if q is None:
            return []

        params = [since_ms]
        where = "ts_ms >= ? AND embedding IS NOT NULL"
        if doc_types:
            where += " AND doc_type IN ({})".format(",".join(["?"] * len(doc_types)))
            params.extend(doc_types)

        with self.db_lock:
            rows = list(
                self.conn.execute(
                    f"SELECT id, ts_ms, doc_type, text, tags_json, embedding, embedding_dim, model FROM memory_docs WHERE {where}",
                    params,
                )
            )

        if not rows:
            return []

        # Build embedding matrix
        vecs = []
        meta = []
        for r in rows:
            emb = np.frombuffer(r["embedding"], dtype=np.float32)
            vecs.append(emb)
            meta.append(r)

        E = np.stack(vecs, axis=0)  # (n, d), already normalized
        scores = E @ q  # cosine similarity
        top_idx = scores.argsort()[-k:][::-1]

        results = []
        for idx in top_idx:
            r = meta[int(idx)]
            results.append(
                {
                    "id": r["id"],
                    "ts_ms": r["ts_ms"],
                    "doc_type": r["doc_type"],
                    "text": r["text"],
                    "tags": json.loads(r["tags_json"] or "[]"),
                    "score": float(scores[int(idx)]),
                }
            )
        return results

    def rag_answer(self, question: str, days: int = 30, k: int = 6):
        """
        RAG-style answer: retrieve relevant memory docs + add basic stats,
        then ask Ollama to generate a grounded response.
        """
        retrieved = self.search_memory(question, k=k, days=days)

        today = self.get_daily_summary()
        week = self.get_weekly_summary()

        context_lines = []
        for r in retrieved:
            ts = datetime.fromtimestamp(r["ts_ms"] / 1000).strftime("%Y-%m-%d %H:%M")
            context_lines.append(
                f"- [{ts}] ({r['doc_type']}, score={r['score']:.3f}) {r['text']}"
            )

        context = "\n".join(context_lines) if context_lines else "(no relevant memories found)"

        stats_block = {
            "today": today or {},
            "week": week or {},
        }

        prompt = f"""You are Hari, a practical accountability friend.
Answer the user's question using ONLY the provided memories and stats. If there isn't enough information, say what is missing.

User question:
{question}

Memories (retrieved):
{context}

Stats (structured JSON):
{json.dumps(stats_block, indent=2)}

Rules:
- Ground claims in the memories/stats above. Do not invent events.
- If you reference a memory, quote a short phrase and its timestamp.
- End with ONE small next action (<= 2 minutes) that reduces procrastination.

Answer:"""

        if self.llm_provider and self.llm_provider.available():
            text = self.llm_provider.generate(prompt, stream=False)
            return (text or "").strip() or "No response from LLM."
        if REQUESTS_AVAILABLE:
            return "No LLM provider configured or available. Check config (llm.provider: ollama|bedrock)."
        return "RAG generation is unavailable (requests not installed)."

    def rag_answer_stream(self, question: str, days: int = 30, k: int = 6):
        """
        RAG-style streaming: retrieve context, then stream Ollama response token by token.
        Yields text chunks.
        """
        retrieved = self.search_memory(question, k=k, days=days)
        today = self.get_daily_summary()
        week = self.get_weekly_summary()

        context_lines = []
        for r in retrieved:
            ts = datetime.fromtimestamp(r["ts_ms"] / 1000).strftime("%Y-%m-%d %H:%M")
            context_lines.append(
                f"- [{ts}] ({r['doc_type']}, score={r['score']:.3f}) {r['text']}"
            )

        context = "\n".join(context_lines) if context_lines else "(no relevant memories found)"
        stats_block = {"today": today or {}, "week": week or {}}

        prompt = f"""You are Hari, a practical accountability friend.
Answer the user's question using ONLY the provided memories and stats. If there isn't enough information, say what is missing.

User question:
{question}

Memories (retrieved):
{context}

Stats (structured JSON):
{json.dumps(stats_block, indent=2)}

Rules:
- Ground claims in the memories/stats above. Do not invent events.
- If you reference a memory, quote a short phrase and its timestamp.
- End with ONE small next action (<= 2 minutes) that reduces procrastination.

Answer:"""

        if self.llm_provider and self.llm_provider.available():
            gen = self.llm_provider.generate(prompt, stream=True)
            if hasattr(gen, "__iter__") and not isinstance(gen, str):
                for chunk in gen:
                    yield chunk
            else:
                yield str(gen)
            return
        yield "No LLM provider configured or available. Check config (llm.provider: ollama|bedrock)."
    
    def create_basic_schema(self):
        """Create basic schema if file not found"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time INTEGER NOT NULL,
                end_time INTEGER,
                duration_ms INTEGER,
                phase TEXT NOT NULL,
                session_number INTEGER,
                completed BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_work_minutes INTEGER DEFAULT 0,
                total_break_minutes INTEGER DEFAULT 0,
                completed_sessions INTEGER DEFAULT 0,
                incomplete_sessions INTEGER DEFAULT 0,
                total_focus_score REAL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS events_processed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                last_timestamp INTEGER NOT NULL,
                last_line_number INTEGER NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            INSERT OR IGNORE INTO events_processed (id, last_timestamp, last_line_number) 
            VALUES (1, 0, 0);
        """)
    
    def process_event(self, event):
        """Process a single event in real-time"""
        event_type = event.get('type_name', '')
        timestamp = event.get('timestamp', 0)
        data = event.get('data', {})
        
        try:
            if event_type == 'pomodoro_start':
                self.handle_pomodoro_start(timestamp, data)
            elif event_type == 'pomodoro_complete':
                self.handle_pomodoro_complete(timestamp, data)
            elif event_type == 'pomodoro_cancel':
                self.handle_pomodoro_cancel(timestamp, data)
        except Exception as e:
            self.logger.error(f"Error processing event: {e}")
    
    def handle_pomodoro_start(self, timestamp, data):
        """Handle pomodoro start event"""
        duration_minutes = data.get('duration_minutes', 25)
        phase = data.get('phase', 'work')
        session_number = data.get('session_count', 0)
        project = data.get('project')

        with self.db_lock:
            self.conn.execute("""
                INSERT INTO sessions (start_time, phase, session_number, completed, duration_ms, project)
                VALUES (?, ?, ?, 0, ?, ?)
            """, (timestamp, phase, session_number, duration_minutes * 60 * 1000, project))
            self.conn.commit()
        self.logger.debug(f"Session started: {phase} session #{session_number}")
    
    def handle_pomodoro_complete(self, timestamp, data):
        """Handle pomodoro complete event"""
        session_count = data.get('session_count', 0)
        phase = data.get('phase', 'work')
        elapsed_ms = data.get('elapsed_ms', 0)
        
        # Find the most recent incomplete session matching this phase
        with self.db_lock:
            cursor = self.conn.execute("""
                SELECT id, start_time FROM sessions 
                WHERE completed = 0 AND phase = ?
                ORDER BY start_time DESC LIMIT 1
            """, (phase,))
            
            row = cursor.fetchone()
            if row:
                session_id = row['id']
                start_time = row['start_time']
                duration_ms = timestamp - start_time
                
                self.conn.execute("""
                    UPDATE sessions 
                    SET end_time = ?, duration_ms = ?, completed = 1
                    WHERE id = ?
                """, (timestamp, duration_ms, session_id))
                
                self.logger.debug(f"Session completed: {phase} #{session_count}")
            else:
                # Create a completed session (in case we missed the start event)
                project = data.get("project")
                self.conn.execute("""
                    INSERT INTO sessions (start_time, end_time, duration_ms, phase, session_number, completed, project)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                """, (timestamp - elapsed_ms, timestamp, elapsed_ms, phase, session_count))
            
            # Update daily stats
            self.update_daily_stats(timestamp)
            self.conn.commit()
    
    def handle_pomodoro_cancel(self, timestamp, data):
        """Handle pomodoro cancel event"""
        self.logger.debug(f"Session cancelled at {timestamp}")
    
    def update_daily_stats(self, timestamp):
        """Update daily statistics"""
        date_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d')
        
        cursor = self.conn.execute("""
            SELECT 
                SUM(CASE WHEN phase = 'work' AND completed = 1 THEN duration_ms ELSE 0 END) / 60000.0 as work_minutes,
                SUM(CASE WHEN phase = 'break' AND completed = 1 THEN duration_ms ELSE 0 END) / 60000.0 as break_minutes,
                SUM(CASE WHEN phase = 'work' AND completed = 1 THEN 1 ELSE 0 END) as completed_work,
                SUM(CASE WHEN phase = 'work' AND completed = 0 THEN 1 ELSE 0 END) as incomplete_work
            FROM sessions
            WHERE date(start_time / 1000, 'unixepoch') = ?
        """, (date_str,))
        
        row = cursor.fetchone()
        work_minutes = int(row[0] or 0)
        break_minutes = int(row[1] or 0)
        completed = int(row[2] or 0)
        incomplete = int(row[3] or 0)
        
        total_sessions = completed + incomplete
        focus_score = (completed / total_sessions * 100) if total_sessions > 0 else 0.0
        
        self.conn.execute("""
            INSERT INTO daily_stats (date, total_work_minutes, total_break_minutes, completed_sessions, incomplete_sessions, total_focus_score)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_work_minutes = excluded.total_work_minutes,
                total_break_minutes = excluded.total_break_minutes,
                completed_sessions = excluded.completed_sessions,
                incomplete_sessions = excluded.incomplete_sessions,
                total_focus_score = excluded.total_focus_score,
                updated_at = CURRENT_TIMESTAMP
        """, (date_str, work_minutes, break_minutes, completed, incomplete, focus_score))
        self.conn.commit()
    
    def get_daily_summary(self, date_str=None):
        """Get summary for a specific date"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        with self.db_lock:
            cursor = self.conn.execute("""
                SELECT * FROM daily_stats WHERE date = ?
            """, (date_str,))
            row = cursor.fetchone()
        if not row:
            return None
        
        return dict(row)
    
    def get_weekly_summary(self):
        """Get summary for the current week"""
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
        week_end = (today + timedelta(days=(6 - today.weekday()))).strftime('%Y-%m-%d')

        with self.db_lock:
            cursor = self.conn.execute("""
                SELECT 
                    SUM(total_work_minutes) as total_minutes,
                    SUM(completed_sessions) as total_sessions,
                    AVG(total_work_minutes) as avg_daily_minutes,
                    MAX(total_work_minutes) as best_day_minutes,
                    COUNT(DISTINCT date) as active_days
                FROM daily_stats
                WHERE date BETWEEN ? AND ?
            """, (week_start, week_end))
            row = cursor.fetchone()
        return {
            'week_start': week_start,
            'week_end': week_end,
            'total_minutes': int(row[0] or 0),
            'total_sessions': int(row[1] or 0),
            'avg_daily_minutes': round(row[2] or 0, 1),
            'best_day_minutes': int(row[3] or 0),
            'active_days': int(row[4] or 0)
        }
    
    def get_recent_sessions(self, limit=5):
        """Get recent completed sessions"""

        with self.db_lock:
            cursor = self.conn.execute("""
                SELECT start_time, end_time, duration_ms, phase, project
                FROM sessions
                WHERE completed = 1
                ORDER BY start_time DESC
                LIMIT ?
            """, (limit,))
            rows = list(cursor)

        sessions = []
        for row in rows:
            sessions.append({
                'start_time': row['start_time'],
                'duration_minutes': round((row['duration_ms'] or 0) / 60000, 1),
                'phase': row['phase'],
                'project': row['project']
            })
        
        return sessions

    def get_week_project_minutes(self, project: str):
        """Return total completed work minutes for the current week for a given project."""
        if not project:
            return 0, None, None
        project_norm = project.strip().lower()

        today = datetime.now()
        week_start_dt = today - timedelta(days=today.weekday())
        week_end_dt = week_start_dt + timedelta(days=6)
        week_start = week_start_dt.strftime('%Y-%m-%d')
        week_end = week_end_dt.strftime('%Y-%m-%d')

        with self.db_lock:
            row = self.conn.execute("""
                SELECT SUM(duration_ms) as total_ms
                FROM sessions
                WHERE completed = 1
                  AND phase = 'work'
                  AND project = ?
                  AND date(start_time / 1000, 'unixepoch') BETWEEN ? AND ?
            """, (project_norm, week_start, week_end)).fetchone()

        total_ms = row[0] or 0
        total_min = int(round(total_ms / 60000.0))
        return total_min, week_start, week_end
    
    def format_natural_language_response(self, query_type, data):
        """Format analytics data as natural language response"""
        if query_type == 'today':
            if not data:
                return "No productivity data for today yet. Start a pomodoro session to begin tracking!"
            
            return (f"📊 Today's Productivity:\n\n"
                   f"You completed {data['completed_sessions']} pomodoro sessions "
                   f"({data['total_work_minutes']} minutes of focused work). "
                   f"Your focus score is {data['total_focus_score']:.0f}% - "
                   f"{'excellent!' if data['total_focus_score'] >= 80 else 'good progress!' if data['total_focus_score'] >= 60 else 'keep going!'}")
        
        elif query_type == 'week':
            if data['total_sessions'] == 0:
                return "No productivity data for this week yet."
            
            return (f"📅 This Week's Productivity:\n\n"
                   f"Total work: {data['total_minutes']} minutes ({data['total_minutes']/60:.1f} hours)\n"
                   f"Sessions: {data['total_sessions']} completed\n"
                   f"Daily average: {data['avg_daily_minutes']:.0f} minutes\n"
                   f"Best day: {data['best_day_minutes']} minutes\n"
                   f"Active days: {data['active_days']}/7")
        
        elif query_type == 'recent':
            if not data:
                return "No recent sessions found."
            
            response = "🕒 Recent Sessions:\n\n"
            for i, session in enumerate(data, 1):
                start = datetime.fromtimestamp(session['start_time'] / 1000)
                response += f"{i}. {start.strftime('%H:%M')} - {session['phase']} ({session['duration_minutes']:.0f} min)\n"
            
            return response.strip()
        
        return "Analytics data retrieved successfully."


class LLMHandler:
    """Handles LLM command parsing via configurable provider (Ollama or Bedrock)."""

    def __init__(self, provider=None):
        self.logger = logging.getLogger('llm')
        if provider is not None:
            self.provider = provider
            self.use_ollama = provider.available()
        else:
            self.provider = create_llm_provider() if (LLM_PROVIDERS_AVAILABLE and create_llm_provider) else None
            self.use_ollama = (self.provider is not None and self.provider.available())
        self.ollama_available = self.use_ollama  # legacy alias

    def _query_llm(self, prompt):
        """Query LLM for structured JSON response (command parsing)."""
        if self.provider is None:
            return None
        return self.provider.generate_json(prompt)

    def parse_command_with_llm(self, natural_language, history=None, session_context=None):
        """Parse natural language using LLM, with optional conversation history and session context."""
        ctx_lines = []
        if session_context:
            ctx_lines.append(f"Current session state:\n{json.dumps(session_context, indent=2)}")
        if history:
            hist_str = "\n".join(f"{m.get('role','user')}: {m.get('text','')}" for m in history[-10:])
            ctx_lines.append(f"Recent conversation:\n{hist_str}")

        ctx_block = ""
        if ctx_lines:
            ctx_block = "\n\n" + "\n\n".join(ctx_lines) + "\n\n"

        prompt = f"""You are a command parser for a productivity assistant. Parse the following natural language command into a JSON object.
{ctx_block}
Available actions:
- pomodoro_start: Start a pomodoro timer (can include duration in minutes). Use for "start timer", "work 45 min", or follow-ups like "make it 45 minutes" when a timer is running.
- pomodoro_pause: Pause the current timer ("pause it", "pause", "hold")
- pomodoro_stop: Stop/cancel the timer
- status: Get system status
- analytics_today: Get today's productivity stats
- analytics_week: Get this week's productivity stats
- analytics_recent: Get recent sessions
- memory_note: Save a note/memory (requires text)
- memory_checkin: Save a daily check-in (requires text)
- memory_review: Save a weekly review/reflection (requires text)
- memory_goal: Save/update a goal statement (requires text)
- memory_query: Ask an open-ended question that should use RAG memory + stats

Command: "{natural_language}"

Return ONLY a JSON object with this format:
{{"action": "<one of the actions above>", "duration": <minutes int, only for pomodoro_start>, "project": "<optional project like leetcode>", "text": "<required for memory_* add actions>", "params": {{}}}}

Examples:
- "start a timer" -> {{"action": "pomodoro_start"}}
- "work for 30 minutes" -> {{"action": "pomodoro_start", "duration": 30}}
- "work on leetcode" -> {{"action": "pomodoro_start", "project": "leetcode"}}
- "work on leetcode for 25 minutes" -> {{"action": "pomodoro_start", "project": "leetcode", "duration": 25}}
- "pause my pomodoro" / "pause it" / "pause" -> {{"action": "pomodoro_pause"}}
- "make it 45 minutes" / "extend to 45" (when timer running) -> {{"action": "pomodoro_start", "duration": 45}}
- "how productive was I today" -> {{"action": "analytics_today"}}
- "note I felt stuck and avoided starting" -> {{"action": "memory_note", "text": "I felt stuck and avoided starting"}}
- "checkin today I want 2 hours of deep work" -> {{"action": "memory_checkin", "text": "today I want 2 hours of deep work"}}
- "weekly review I did well Mon/Tue but crashed Wed" -> {{"action": "memory_review", "text": "I did well Mon/Tue but crashed Wed"}}
- "goal become consistent: 2h/day" -> {{"action": "memory_goal", "text": "become consistent: 2h/day"}}
- "why am I procrastinating this week?" -> {{"action": "memory_query"}}

JSON response:"""

        result = self._query_llm(prompt)

        if result and "action" in result:
            action_map = {
                "pomodoro_start": {"action": "pomodoro", "command": "start"},
                "pomodoro_pause": {"action": "pomodoro", "command": "pause"},
                "pomodoro_stop": {"action": "pomodoro", "command": "stop"},
                "status": {"action": "status", "command": ""},
                "analytics_today": {"action": "analytics", "query": "today"},
                "analytics_week": {"action": "analytics", "query": "week"},
                "analytics_recent": {"action": "analytics", "query": "recent"},
                "memory_note": {"action": "memory_add", "doc_type": "note"},
                "memory_checkin": {"action": "memory_add", "doc_type": "checkin"},
                "memory_review": {"action": "memory_add", "doc_type": "weekly_review"},
                "memory_goal": {"action": "memory_add", "doc_type": "goal"},
                "memory_query": {"action": "memory_query"},
            }
            
            llm_action = result.get("action")
            if llm_action in action_map:
                parsed = action_map[llm_action].copy()
                
                if "duration" in result:
                    parsed["duration"] = result["duration"]

                if "project" in result and isinstance(result.get("project"), str):
                    parsed["project"] = result["project"].strip()

                if parsed["action"] == "memory_add":
                    parsed["text"] = (result.get("text") or "").strip()
                
                self.logger.info(f"LLM parsed: {llm_action}")
                return parsed
        
        return None
    
    def parse_command(self, natural_language):
        """Parse natural language command using simple pattern matching"""
        text = natural_language.lower().strip()

        # Memory add patterns
        if text.startswith("note "):
            return {"action": "memory_add", "doc_type": "note", "text": natural_language.strip()[5:].strip()}
        if text.startswith("checkin "):
            return {"action": "memory_add", "doc_type": "checkin", "text": natural_language.strip()[8:].strip()}
        if text.startswith("weekly review "):
            return {"action": "memory_add", "doc_type": "weekly_review", "text": natural_language.strip()[13:].strip()}
        if text.startswith("review "):
            return {"action": "memory_add", "doc_type": "weekly_review", "text": natural_language.strip()[7:].strip()}
        if text.startswith("goal "):
            return {"action": "goal_set", "text": natural_language.strip()[5:].strip()}

        # Open-ended accountability / reflection questions → RAG memory query
        if any(w in text for w in ["procrast", "lazy", "motivat", "accountab", "why am i", "why do i", "what is wrong", "help me start"]):
            return {"action": "memory_query"}
        
        # Analytics patterns
        if any(word in text for word in ["productive", "productivity", "stats", "statistics", "summary"]):
            if any(word in text for word in ["today", "today's"]):
                return {"action": "analytics", "query": "today"}
            if any(word in text for word in ["week", "weekly", "this week"]):
                mproj = re.search(r"on\s+([a-z0-9 _-]+)", text)
                if mproj:
                    return {"action": "analytics", "query": "week", "project": mproj.group(1).strip()}
                return {"action": "analytics", "query": "week"}
            if any(word in text for word in ["recent", "last", "latest"]):
                return {"action": "analytics", "query": "recent"}

        # Project-specific weekly progress without saying "stats"
        if any(word in text for word in ["this week", "weekly"]) and "on " in text:
            mproj = re.search(r"on\s+([a-z0-9 _-]+)", text)
            if mproj:
                return {"action": "analytics", "query": "week", "project": mproj.group(1).strip()}
        
        # Pomodoro start patterns
        mboth = re.search(r"work on\s+([a-z0-9 _-]+?)\s+for\s+(\d+)\s*(?:min(?:ute)?s?)?", text)
        if mboth:
            return {"action": "pomodoro", "command": "start", "project": mboth.group(1).strip(), "duration": int(mboth.group(2))}
        mdur = re.search(r"(?:work|focus|timer)\s+(?:for\s+)?(\d+)\s*(?:min(?:ute)?s?)?", text)
        if mdur:
            return {"action": "pomodoro", "command": "start", "duration": int(mdur.group(1))}
        mproj = re.search(r"work on\s+([a-z0-9 _-]+)", text)
        if mproj and any(word in text for word in ["work", "start", "begin", "pomodoro", "focus", "timer"]):
            return {"action": "pomodoro", "command": "start", "project": mproj.group(1).strip()}

        # "Make it X min" / "extend to X" - parse duration (follow-up when timer running)
        m = re.search(r"(?:make it|extend to?|set to|change to|change it to)\s*(\d+)\s*(?:min(?:ute)?s?)?", text)
        if m:
            return {"action": "pomodoro", "command": "start", "duration": int(m.group(1))}

        if any(word in text for word in ["start", "begin", "commence"]):
            if any(word in text for word in ["timer", "pomodoro", "focus", "work"]):
                return {"action": "pomodoro", "command": "start"}
                
        # Pomodoro pause patterns (including "pause it", "pause")
        if any(word in text for word in ["pause", "hold", "suspend"]):
            if any(word in text for word in ["timer", "pomodoro", "it"]) or text.strip() in ("pause", "pause it"):
                return {"action": "pomodoro", "command": "pause"}
                
        # Pomodoro stop patterns
        if any(word in text for word in ["stop", "cancel", "end", "quit"]):
            if any(word in text for word in ["timer", "pomodoro"]):
                return {"action": "pomodoro", "command": "stop"}
                
        # Status
        if any(word in text for word in ["status", "how", "what"]):
            return {"action": "status", "command": ""}
            
        return None
    
    def parse(self, natural_language, history=None, session_context=None):
        """Parse command using LLM or fallback. history/session_context aid follow-up commands."""
        if self.use_ollama and self.ollama_available:
            parsed = self.parse_command_with_llm(natural_language, history=history, session_context=session_context)
            if parsed is None:
                self.logger.warning("LLM parsing failed, trying pattern matching")
                parsed = self.parse_command(natural_language)
        else:
            parsed = self.parse_command(natural_language)
        
        return parsed


class LLMServer:
    """Handles LLM commands and pomodoro daemon (web API)."""

    def __init__(self, llm_handler, analytics_handler, pomodoro_engine=None):
        self.logger = logging.getLogger("llm_server")
        self.llm_handler = llm_handler
        self.analytics = analytics_handler
        self.pomodoro_engine = pomodoro_engine
        self.running = True

    def send_to_hari_daemon(self, command_type, payload=""):
        """Execute daemon command (pomodoro/status) via in-process PomodoroEngine."""
        if self.pomodoro_engine is None:
            return {"status": "error", "message": "Pomodoro engine not available"}
        if command_type == "status":
            return self.pomodoro_engine.get_status()
        if command_type == "pomodoro_structured":
            return self.pomodoro_engine.get_structured_status()
        if command_type == "pomodoro":
            if payload == "pause":
                return self.pomodoro_engine.pause()
            if payload == "resume":
                return self.pomodoro_engine.resume()
            if payload in ("stop", "cancel"):
                return self.pomodoro_engine.stop()
            # JSON payload for start (with optional duration_minutes, project)
            try:
                obj = json.loads(payload) if isinstance(payload, str) else payload
                cmd = obj.get("command", "")
                if cmd == "start":
                    return self.pomodoro_engine.start(
                        duration_minutes=obj.get("duration_minutes"),
                        project=obj.get("project"),
                    )
            except (json.JSONDecodeError, TypeError):
                pass
            return {"status": "error", "message": f"Unknown pomodoro payload: {payload}"}
        return {"status": "error", "message": f"Unknown command: {command_type}"}
    
    def handle_request(self, request_data):
        """Handle incoming request from CLI (raw bytes)."""
        try:
            request = json.loads(request_data.decode())
            command_text = request.get("command", "")
            return self.handle_command(command_text)
        except json.JSONDecodeError as e:
            return {"version": 1, "status": "error", "message": f"Invalid JSON: {e}"}
        except Exception as e:
            return {"version": 1, "status": "error", "message": f"Error: {e}"}

    def _get_session_context(self):
        """Build session context (pomodoro state) for LLM."""
        if self.pomodoro_engine is None:
            return None
        try:
            s = self.send_to_hari_daemon("pomodoro_structured")
            if s and isinstance(s, dict):
                return {
                    "pomodoro": {
                        "phase": s.get("phase", "idle"),
                        "mode": s.get("mode", "idle"),
                        "running": s.get("running", False),
                        "paused": s.get("paused", False),
                        "remaining_ms": s.get("remaining_ms", 0),
                        "remaining_minutes": round(s.get("remaining_ms", 0) / 60000),
                        "duration_minutes": s.get("duration_minutes", 0),
                        "session_count": s.get("session_count", 0),
                        "project": s.get("project", "") or "(none)",
                    }
                }
        except Exception:
            pass
        return None

    def handle_command(self, command_text: str, history=None):
        """Handle a single command string (CLI or API). history: list of {role, text} for context."""
        try:
            self.logger.info(f"Processing: '{command_text}'")

            # -------- Memory management & guardrails (deterministic) --------
            text = (command_text or "").strip()
            lower = text.lower()

            # Helpers
            def _looks_sensitive(s: str) -> bool:
                if re.search(r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY", s):
                    return True
                if re.search(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", s):  # telegram-like token
                    return True
                if "api key" in s.lower() or "password" in s.lower() or "secret" in s.lower():
                    return True
                return False

            def _save_profile_name(name: str):
                name = name.strip()
                if not name:
                    return None
                self.analytics.add_memory_doc("profile", f"name: {name}", tags=["identity"])
                return name

            # List memories
            if lower in ("memories", "memory", "what do you remember", "what do you remember about me", "list memories"):
                items = self.analytics.list_memories(limit=15)
                if not items:
                    return {"version": 1, "status": "ok", "message": "No memories saved yet."}
                lines = []
                for r in items:
                    ts = datetime.fromtimestamp(r["ts_ms"] / 1000).strftime("%Y-%m-%d %H:%M")
                    snippet = r["text"].replace("\n", " ")
                    if len(snippet) > 120:
                        snippet = snippet[:117] + "..."
                    lines.append(f"- #{r['id']} [{ts}] ({r['doc_type']}) {snippet}")
                return {"version": 1, "status": "ok", "message": "Here’s what I remember:\n\n" + "\n".join(lines)}

            # Forget memories
            if lower.startswith("forget "):
                arg = text[7:].strip()
                if not arg:
                    return {"version": 1, "status": "error", "message": "Usage: 'hari forget <id|phrase>'"}
                if arg.isdigit():
                    n = self.analytics.forget_memory_by_id(int(arg))
                    return {"version": 1, "status": "ok", "message": f"Forgot {n} memory item(s)."}
                n = self.analytics.forget_memory_by_substring(arg)
                return {"version": 1, "status": "ok", "message": f"Forgot {n} memory item(s) matching '{arg}'."}

            # Confirm/deny pending memory
            if lower in ("remember yes", "remember y", "remember sure", "remember ok", "remember okay", "remember"):
                pending = self.analytics.pop_latest_pending()
                if not pending:
                    return {"version": 1, "status": "ok", "message": "No pending memory to save."}
                if _looks_sensitive(pending["text"]):
                    return {"version": 1, "status": "error", "message": "I won’t save that because it looks sensitive."}
                self.analytics.add_memory_doc(pending["doc_type"], pending["text"], tags=["confirmed"])
                return {"version": 1, "status": "ok", "message": f"Saved as {pending['doc_type']}."}

            if lower in ("remember no", "remember n", "don't remember", "do not remember", "forget that"):
                pending = self.analytics.pop_latest_pending()
                if not pending:
                    return {"version": 1, "status": "ok", "message": "No pending memory to discard."}
                return {"version": 1, "status": "ok", "message": "Okay — I won’t save that."}

            # Explicit "remember ..." statements
            if lower.startswith("remember "):
                payload = text[len("remember "):].strip()
                if not payload:
                    return {"version": 1, "status": "error", "message": "Usage: 'hari remember <something>'"}
                if _looks_sensitive(payload):
                    return {"version": 1, "status": "error", "message": "I won’t save that because it looks sensitive."}

                m = re.match(r"(?i)my name is\s+(.+)$", payload)
                if m:
                    name = _save_profile_name(m.group(1))
                    return {"version": 1, "status": "ok", "message": f"Got it — I’ll remember your name is {name}."}
                m = re.match(r"(?i)call me\s+(.+)$", payload)
                if m:
                    name = _save_profile_name(m.group(1))
                    return {"version": 1, "status": "ok", "message": f"Got it — I’ll call you {name}."}
                m = re.match(r"(?i)my goal is\s+(.+)$", payload)
                if m:
                    ok, msg = self.analytics.set_structured_goal(m.group(1).strip())
                    return {"version": 1, "status": "ok" if ok else "error", "message": msg}
                # default explicit remember → note
                self.analytics.add_memory_doc("note", payload, tags=["explicit"])
                return {"version": 1, "status": "ok", "message": "Saved."}

            # Auto-save for profile/goals/preferences only when explicit (no confirmation)
            m = re.match(r"(?i)my name is\s+(.+)$", text)
            if m:
                name = _save_profile_name(m.group(1))
                return {"version": 1, "status": "ok", "message": f"Got it — I’ll remember your name is {name}."}
            m = re.match(r"(?i)call me\s+(.+)$", text)
            if m:
                name = _save_profile_name(m.group(1))
                return {"version": 1, "status": "ok", "message": f"Got it — I’ll call you {name}."}
            m = re.match(r"(?i)(my goal is|goal:|i want to become)\s+(.+)$", text)
            if m:
                goal = m.group(2).strip()
                if _looks_sensitive(goal):
                    return {"version": 1, "status": "error", "message": "I won’t save that because it looks sensitive."}
                ok, msg = self.analytics.set_structured_goal(goal)
                return {"version": 1, "status": "ok" if ok else "error", "message": msg}
            m = re.match(r"(?i)i prefer\s+(gentle|direct|strict)\s+nudges", text)
            if m:
                pref = m.group(1).lower()
                self.analytics.add_memory_doc("preference", f"nudge_style: {pref}", tags=["preference"])
                return {"version": 1, "status": "ok", "message": f"Saved preference: nudge_style = {pref}."}

            # If user asks for their name, answer from profile memory first
            if re.search(r"(?i)\b(my name|do you know my name|what is my name)\b", text):
                name = self.analytics.get_latest_profile_field("name")
                if name:
                    return {"version": 1, "status": "ok", "message": f"Yes — your name is {name}."}
                return {"version": 1, "status": "ok", "message": "I don’t know your name yet. Tell me: 'my name is ...' or 'remember my name is ...'."}

            # Deterministic goal status
            if re.search(r"(?i)\b(goal)\b", text) and re.search(r"(?i)\b(today|daily|on track|achieve|achieved|met)\b", text):
                return {"version": 1, "status": "ok", "message": self.analytics.goal_status_today()}

            # Ask-before-save for reflections (procrastination context)
            if any(k in lower for k in ["i procrast", "procrastinat", "lazy", "stuck", "overwhelm", "avoid starting", "i feel"]):
                if not _looks_sensitive(text):
                    self.analytics.add_pending_memory("reflection", text, meta={"source": "auto"})
                    return {
                        "version": 1,
                        "status": "ok",
                        "message": (
                            "Do you want me to remember this as a reflection?\n\n"
                            f"“{text}”\n\n"
                            "Reply with `hari remember yes` or `hari remember no`."
                        ),
                    }
            
            session_context = self._get_session_context()
            parsed = self.llm_handler.parse(command_text, history=history, session_context=session_context)

            if parsed is None:
                return {
                    "version": 1,
                    "status": "error",
                    "message": "Could not understand command"
                }

            # Structured goal set via pattern matching: "goal ..."
            if parsed["action"] == "goal_set":
                goal_text = (parsed.get("text") or "").strip()
                ok, msg = self.analytics.set_structured_goal(goal_text)
                return {"version": 1, "status": "ok" if ok else "error", "message": msg}

            # Handle memory add (notes/checkins/reviews/goals)
            if parsed["action"] == "memory_add":
                text = (parsed.get("text") or "").strip()
                if not text:
                    return {
                        "version": 1,
                        "status": "error",
                        "message": "Missing text for memory entry. Try: 'note ...' or 'checkin ...'"
                    }
                doc_type = parsed.get("doc_type", "note")
                self.analytics.add_memory_doc(doc_type=doc_type, text=text)
                return {
                    "version": 1,
                    "status": "ok",
                    "message": f"Saved {doc_type}."
                }

            # Handle memory query (RAG)
            if parsed["action"] == "memory_query":
                message = self.analytics.rag_answer(command_text)
                return {
                    "version": 1,
                    "status": "ok",
                    "message": message
                }
            
            # Handle analytics queries
            if parsed["action"] == "analytics":
                query_type = parsed.get("query", "today")
                project = parsed.get("project")
                
                if query_type == "today":
                    data = self.analytics.get_daily_summary()
                    message = self.analytics.format_natural_language_response("today", data)
                elif query_type == "week":
                    if project:
                        mins, ws, we = self.analytics.get_week_project_minutes(project)
                        message = f"📅 This week on **{project}** ({ws} to {we}): {mins} minutes of focused work."
                    else:
                        data = self.analytics.get_weekly_summary()
                        message = self.analytics.format_natural_language_response("week", data)
                elif query_type == "recent":
                    data = self.analytics.get_recent_sessions()
                    message = self.analytics.format_natural_language_response("recent", data)
                else:
                    message = "Unknown analytics query"
                
                return {
                    "version": 1,
                    "status": "ok",
                    "message": message
                }
            
            # Handle pomodoro commands
            if parsed["action"] == "pomodoro":
                payload = parsed["command"]
                # Structured start payload: allow per-session duration + project tags
                if parsed.get("command") == "start":
                    duration = parsed.get("duration")
                    project = parsed.get("project")
                    if duration is not None or project:
                        payload_obj = {"command": "start"}
                        if duration is not None:
                            payload_obj["duration_minutes"] = int(duration)
                        if project:
                            payload_obj["project"] = str(project)
                        payload = json.dumps(payload_obj, separators=(",", ":"))
                        # "Make it X min" / extend: stop current work session first, then start with new duration
                        if session_context and duration is not None:
                            pom = session_context.get("pomodoro", {})
                            if pom.get("phase") in ("working", "paused"):
                                self.send_to_hari_daemon("pomodoro", "stop")

                response = self.send_to_hari_daemon("pomodoro", payload)
                
                if "duration" in parsed:
                    response["message"] = f"{response.get('message', '')} ({parsed['duration']} minutes)"
                    
            elif parsed["action"] == "status":
                response = self.send_to_hari_daemon("status")
            else:
                response = {"status": "error", "message": "Unknown action"}
                
            response["version"] = 1
            return response

        except Exception as e:
            return {"version": 1, "status": "error", "message": f"Error: {e}"}

    def start(self):
        """Block until stopped (no socket server)."""
        import time
        while self.running:
            time.sleep(1.0)

    def stop(self):
        """Stop the server"""
        self.running = False


def _get_api_port():
    """API port from env HARI_API_PORT or 8765."""
    port = os.environ.get("HARI_API_PORT")
    if port:
        try:
            return int(port)
        except ValueError:
            pass
    return 8765


def create_web_app(llm_server, analytics, sse_event_queue=None):
    """Create FastAPI app for Web API (frontend / integrations)."""
    if not WEBAPI_AVAILABLE:
        return None
    if sse_event_queue is None:
        sse_event_queue = queue.Queue()
    app = FastAPI(
        title="Hari API",
        description="REST API for Hari productivity assistant (pomodoro, analytics, natural language)",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth dependency (must be defined before routes that use it)
    JWT_SECRET = os.environ.get("HARI_JWT_SECRET", "dev-secret-change-in-production")
    JWT_ALG = "HS256"
    security = HTTPBearer(auto_error=False)

    def _decode_token(creds: Optional[HTTPAuthorizationCredentials] = None):
        if not creds or not creds.credentials or not AUTH_AVAILABLE:
            return None
        try:
            payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
            return payload.get("user_id")
        except Exception:
            return None

    def require_user_id(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
        """Dependency: return user_id or 401."""
        user_id = _decode_token(creds)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        return int(user_id)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "hari"}

    @app.post("/api/command")
    def api_command(body: dict):
        """Natural language command (same as CLI). Optional body.history: [{role, text}, ...] for context."""
        cmd = body.get("command", "")
        history = body.get("history")
        if not isinstance(history, list):
            history = None
        return llm_server.handle_command(cmd, history=history)

    @app.post("/api/command/stream")
    def api_command_stream(body: dict):
        """Stream natural language command response (SSE). Optional body.history for context."""
        cmd = (body.get("command") or "").strip()
        history = body.get("history")
        if not isinstance(history, list):
            history = None

        def generate():
            session_context = llm_server._get_session_context()
            parsed = llm_server.llm_handler.parse(cmd, history=history, session_context=session_context)
            if parsed and parsed.get("action") == "memory_query":
                for chunk in analytics.rag_answer_stream(cmd):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                yield f"data: {json.dumps({'done': True, 'status': 'ok'})}\n\n"
            else:
                result = llm_server.handle_command(cmd, history=history)
                msg = result.get("message", "")
                if msg:
                    yield f"data: {json.dumps({'chunk': msg})}\n\n"
                yield f"data: {json.dumps({'done': True, 'status': result.get('status', 'ok')})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/status")
    def api_status():
        """Daemon status (uptime, modules)."""
        return llm_server.send_to_hari_daemon("status")

    @app.post("/api/pomodoro/start")
    def pomodoro_start(body: Optional[dict] = Body(None)):
        """Start pomodoro. Body: optional duration_minutes, project."""
        body = body or {}
        payload = {"command": "start"}
        if body.get("duration_minutes") is not None:
            payload["duration_minutes"] = int(body["duration_minutes"])
        if body.get("project"):
            payload["project"] = str(body["project"])
        resp = llm_server.send_to_hari_daemon("pomodoro", json.dumps(payload, separators=(",", ":")))
        resp["version"] = 1
        return resp

    @app.post("/api/pomodoro/pause")
    def pomodoro_pause():
        return llm_server.send_to_hari_daemon("pomodoro", "pause")

    @app.post("/api/pomodoro/resume")
    def pomodoro_resume():
        return llm_server.send_to_hari_daemon("pomodoro", "resume")

    @app.post("/api/pomodoro/stop")
    def pomodoro_stop():
        return llm_server.send_to_hari_daemon("pomodoro", "stop")

    @app.get("/api/pomodoro/status")
    def pomodoro_structured_status():
        """Structured pomodoro state for frontend sync (remaining_ms, phase, etc.)."""
        return llm_server.send_to_hari_daemon("pomodoro_structured", "")

    @app.get("/api/pomodoro/settings")
    def pomodoro_get_settings(user_id: int = Depends(require_user_id)):
        """Get pomodoro settings for current user (from DB)."""
        return analytics.get_pomodoro_settings(user_id)

    @app.put("/api/pomodoro/settings")
    def pomodoro_update_settings(
        body: Optional[dict] = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        """Update pomodoro settings. Body: work_duration_minutes, short_break_minutes, long_break_minutes, sessions_until_long_break."""
        body = body or {}
        return analytics.update_pomodoro_settings(
            user_id,
            work_duration_minutes=body.get("work_duration_minutes"),
            short_break_minutes=body.get("short_break_minutes"),
            long_break_minutes=body.get("long_break_minutes"),
            sessions_until_long_break=body.get("sessions_until_long_break"),
        )

    @app.get("/api/pomodoro/events")
    def pomodoro_events():
        """SSE stream of pomodoro events (complete, start, pause, cancel)."""
        def generate():
            while True:
                try:
                    event = sse_event_queue.get(timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'ping', 'timestamp': int(time.time() * 1000)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/analytics/today")
    def analytics_today():
        data = analytics.get_daily_summary()
        return {"date": datetime.now().strftime('%Y-%m-%d'), "data": data}

    @app.get("/api/analytics/week")
    def analytics_week():
        data = analytics.get_weekly_summary()
        return data

    @app.get("/api/analytics/sessions")
    def analytics_sessions(limit: int = 10):
        data = analytics.get_recent_sessions(limit=min(limit, 100))
        return {"sessions": data}

    @app.get("/api/analytics/history")
    def analytics_history(days: int = 7):
        days = min(max(1, days), 365)
        result = []
        for i in range(days):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            row = analytics.get_daily_summary(date_str=d)
            result.append({"date": d, "data": row})
        return {"history": result}

    # User management CRUD
    @app.get("/api/users")
    def users_list():
        return {"users": analytics.list_users()}

    @app.post("/api/users")
    def users_create(body: dict = Body(None)):
        body = body or {}
        try:
            user = analytics.create_user(
                name=body.get("name", ""),
                email=body.get("email", ""),
            )
            return user
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/users/{user_id:int}")
    def users_get(user_id: int):
        user = analytics.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @app.put("/api/users/{user_id:int}")
    def users_update(user_id: int, body: dict = Body(None)):
        body = body or {}
        user = analytics.update_user(
            user_id,
            name=body.get("name"),
            email=body.get("email"),
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    @app.delete("/api/users/{user_id:int}")
    def users_delete(user_id: int):
        if not analytics.delete_user(user_id):
            raise HTTPException(status_code=404, detail="User not found")
        return {"status": "ok"}

    # Auth (login, register) - JWT_SECRET, security, _decode_token, require_user_id defined above
    @app.post("/api/auth/register")
    def auth_register(body: dict = Body(None)):
        """Register: name, email, password."""
        body = body or {}
        if not AUTH_AVAILABLE:
            raise HTTPException(status_code=501, detail="Auth not available (install pyjwt passlib)")
        name = (body.get("name") or "").strip()
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        if not name or not email or not password:
            raise HTTPException(status_code=400, detail="name, email, and password required")
        if len(password) < 6:
            raise HTTPException(status_code=400, detail="password must be at least 6 characters")
        try:
            user = analytics.create_user(name=name, email=email, password=password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        token = jwt.encode({"user_id": user["id"], "email": user["email"]}, JWT_SECRET, algorithm=JWT_ALG)
        return {"user": {k: v for k, v in user.items()}, "token": token}

    @app.post("/api/auth/login")
    def auth_login(body: dict = Body(None)):
        """Login: email, password. Returns user + token."""
        body = body or {}
        if not AUTH_AVAILABLE:
            raise HTTPException(status_code=501, detail="Auth not available")
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        user = analytics.verify_user_password(email, password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token = jwt.encode({"user_id": user["id"], "email": user["email"]}, JWT_SECRET, algorithm=JWT_ALG)
        return {"user": {k: v for k, v in user.items() if k != "password_hash"}, "token": token}

    @app.get("/api/auth/me")
    def auth_me(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
        """Get current user from token."""
        user_id = _decode_token(creds)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        user = analytics.get_user(int(user_id))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user

    # Spaced Repetition
    @app.get("/api/sr/topics")
    def sr_topics_list(user_id: int = Depends(require_user_id)):
        return {"topics": analytics.sr_list_topics(user_id)}

    @app.get("/api/sr/neetcode150")
    def sr_neetcode150_list():
        """Return NeetCode 150 problem list for import."""
        path = Path(__file__).parent / "neetcode150.json"
        if not path.exists():
            return {"problems": []}
        try:
            with open(path) as f:
                return {"problems": json.load(f)}
        except (json.JSONDecodeError, OSError):
            return {"problems": []}

    @app.post("/api/sr/import-neetcode150")
    def sr_import_neetcode150(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        """Import selected NeetCode 150 problems as SR topics. Body: { slugs: string[] } or { indices: number[] }."""
        body = body or {}
        path = Path(__file__).parent / "neetcode150.json"
        if not path.exists():
            raise HTTPException(status_code=500, detail="NeetCode 150 list not available")
        try:
            with open(path) as f:
                problems = json.load(f)
        except (json.JSONDecodeError, OSError):
            raise HTTPException(status_code=500, detail="NeetCode 150 list not available")
        slugs = body.get("slugs")
        indices = body.get("indices")
        if slugs is not None:
            to_import = [p for p in problems if p.get("slug") in slugs]
        elif indices is not None:
            to_import = [problems[i] for i in indices if 0 <= i < len(problems)]
        else:
            raise HTTPException(status_code=400, detail="slugs or indices required")
        if not to_import:
            return {"created": 0, "topics": analytics.sr_list_topics(user_id)}
        existing = {t["name"] for t in analytics.sr_list_topics(user_id)}
        # Estimate: Easy 30min, Medium 45min, Hard 60min
        def est_mins(p):
            d = (p.get("difficulty") or "").lower()
            return 30 if d == "easy" else 60 if d == "hard" else 45
        to_create = [
            {"name": (p.get("title") or "").strip(), "estimated_minutes": est_mins(p)}
            for p in to_import
            if (p.get("title") or "").strip() and (p.get("title") or "").strip() not in existing
        ]
        if not to_create:
            return {"created": 0, "topics": analytics.sr_list_topics(user_id)}
        settings = analytics.sr_get_settings(user_id)
        cap = settings.get("daily_capacity_minutes") or 120
        schedule = analytics._sr_compute_first_due_dates(to_create, cap)
        created = 0
        for idx, first_due in schedule:
            item = to_create[idx]
            name = item["name"]
            if name in existing:
                continue
            try:
                analytics.sr_create_topic(user_id, name, item["estimated_minutes"], first_due_date=first_due)
                created += 1
                existing.add(name)
            except ValueError:
                pass
        return {"created": created, "topics": analytics.sr_list_topics(user_id)}

    @app.post("/api/sr/topics")
    def sr_topics_create(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        body = body or {}
        name = (body.get("name") or "").strip()
        estimated = body.get("estimated_minutes", 60)
        try:
            return analytics.sr_create_topic(user_id, name, estimated)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.put("/api/sr/topics/{topic_id:int}")
    def sr_topics_update(
        topic_id: int,
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        body = body or {}
        updated = analytics.sr_update_topic(
            user_id, topic_id,
            name=body.get("name"),
            estimated_minutes=body.get("estimated_minutes"),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Topic not found")
        return updated

    @app.delete("/api/sr/topics/{topic_id:int}")
    def sr_topics_delete(topic_id: int, user_id: int = Depends(require_user_id)):
        if not analytics.sr_delete_topic(user_id, topic_id):
            raise HTTPException(status_code=404, detail="Topic not found")
        return {"status": "ok"}

    @app.delete("/api/sr/topics")
    def sr_topics_delete_all(user_id: int = Depends(require_user_id)):
        """Delete all SR topics for the current user. Does not touch sessions/analytics history."""
        count = analytics.sr_delete_all_topics(user_id)
        return {"status": "ok", "deleted": count}

    @app.post("/api/sr/topics/{topic_id:int}/retire")
    def sr_topics_retire(topic_id: int, user_id: int = Depends(require_user_id)):
        """Mark topic as done completely. Removes from practice."""
        if not analytics.sr_retire_topic(user_id, topic_id):
            raise HTTPException(status_code=404, detail="Topic not found")
        return {"status": "ok", "topics": analytics.sr_get_due_today(user_id)}

    @app.get("/api/sr/due-today")
    def sr_due_today(user_id: int = Depends(require_user_id)):
        return {"topics": analytics.sr_get_due_today(user_id)}

    @app.post("/api/sr/skip-today")
    def sr_skip_today(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        """Skip a topic for today only. Schedule unchanged."""
        body = body or {}
        topic_id = body.get("topic_id")
        if not topic_id:
            raise HTTPException(status_code=400, detail="topic_id required")
        if not analytics.sr_skip_topic_today(user_id, int(topic_id)):
            raise HTTPException(status_code=404, detail="Topic not found")
        return {"status": "ok", "topics": analytics.sr_get_due_today(user_id)}

    @app.post("/api/sr/skip-until")
    def sr_skip_until(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        """Skip a topic and show again in N days (1, 3, 7, or 14)."""
        body = body or {}
        topic_id = body.get("topic_id")
        days = body.get("days")
        if not topic_id or days not in (1, 3, 7, 14):
            raise HTTPException(status_code=400, detail="topic_id and days (1, 3, 7, 14) required")
        try:
            if not analytics.sr_skip_topic_until(user_id, int(topic_id), int(days)):
                raise HTTPException(status_code=404, detail="Topic not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "ok", "topics": analytics.sr_get_due_today(user_id)}

    @app.post("/api/sr/review")
    def sr_review(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        body = body or {}
        topic_id = body.get("topic_id")
        difficulty = (body.get("difficulty") or "").lower()
        if not topic_id or difficulty not in ("easy", "medium", "hard"):
            raise HTTPException(
                status_code=400,
                detail="topic_id and difficulty (easy/medium/hard) required",
            )
        try:
            return analytics.sr_record_review(user_id, int(topic_id), difficulty)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/sr/settings")
    def sr_settings_get(user_id: int = Depends(require_user_id)):
        return analytics.sr_get_settings(user_id)

    @app.put("/api/sr/settings")
    def sr_settings_update(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        body = body or {}
        cap = body.get("daily_capacity_minutes")
        return analytics.sr_update_settings(user_id, daily_capacity_minutes=cap)

    @app.post("/api/sr/complete-task")
    def sr_complete_task_endpoint(
        body: dict = Body(None),
        user_id: int = Depends(require_user_id),
    ):
        """Mark today's task complete. Optional difficulty (easy/medium/hard) records review and adjusts schedule."""
        body = body or {}
        project = (body.get("project") or "").strip()
        difficulty = (body.get("difficulty") or "").strip().lower() or None
        if not project:
            raise HTTPException(status_code=400, detail="project required")
        updated, streak = analytics.sr_complete_task(user_id, project, difficulty)
        if not updated:
            raise HTTPException(status_code=404, detail="Topic not found")
        return {"status": "ok", "streak": streak}

    @app.get("/api/sr/streak")
    def sr_streak_get(user_id: int = Depends(require_user_id)):
        """Get current and longest practice streak (consecutive days with completed tasks)."""
        return analytics.sr_get_streak(user_id)

    # Knowledge Base (websites, documents)
    @app.get("/api/knowledge")
    def knowledge_list(source_type: Optional[str] = None):
        return {"sources": analytics.list_knowledge_sources(source_type)}

    @app.post("/api/knowledge")
    def knowledge_add(body: dict = Body(None)):
        body = body or {}
        st = (body.get("source_type") or "website").lower()
        url = (body.get("url") or "").strip()
        title = (body.get("title") or "").strip()
        try:
            src = analytics.add_knowledge_source(st, url=url or None, title=title or None)
            return src
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.delete("/api/knowledge/{source_id:int}")
    def knowledge_delete(source_id: int):
        if not analytics.delete_knowledge_source(source_id):
            raise HTTPException(status_code=404, detail="Source not found")
        return {"status": "ok"}

    return app


def _cloud_heartbeat_loop(analytics, running_flag, logger, interval_seconds=3600):
    """
    Background loop: every interval_seconds POST to cloud heartbeat endpoint with
    goal + today's work minutes so the cloud can send goal-reminder nudges.
    """
    config_path = _get_config_path()
    next_run = time.time()
    while getattr(running_flag, 'running', True):
        now = time.time()
        if now < next_run:
            time.sleep(min(1.0, next_run - now))
            continue
        next_run = now + interval_seconds
        if not config_path.exists():
            continue
        try:
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        cloud_cfg = config.get('cloud', {})
        telegram_cfg = config.get('telegram', {})
        if not cloud_cfg.get('enabled'):
            continue
        endpoint = (cloud_cfg.get('heartbeat_endpoint') or '').strip()
        chat_id = (telegram_cfg.get('chat_id') or '').strip()
        if not endpoint or not chat_id:
            continue
        try:
            today = analytics.get_daily_summary()
            today_work = int((today or {}).get('total_work_minutes') or 0)
            goals = analytics.get_active_goals()
            stats = {
                'today_work_minutes': today_work,
            }
            if goals:
                stats['goals'] = []
                for g in goals:
                    target = int(g.get('target_minutes_per_day') or 0)
                    if target <= 0:
                        continue
                    label = (g.get('label') or g.get('raw_text') or '').strip() or None
                    stats['goals'].append({
                        'goal_minutes': target,
                        'goal_label': (label[:64] if label else None),
                    })
                # Backward compat: single goal_minutes / goal_label for workers that expect one
                if len(stats['goals']) == 1:
                    stats['goal_minutes'] = stats['goals'][0]['goal_minutes']
                    stats['goal_label'] = stats['goals'][0].get('goal_label')
            if not REQUESTS_AVAILABLE:
                continue
            resp = requests.post(
                endpoint,
                json={'chat_id': chat_id, 'stats': stats},
                timeout=10,
                headers={'Content-Type': 'application/json'},
            )
            if resp.status_code == 200:
                logger.debug("Cloud heartbeat sent (goals=%s, today=%s)", len(goals) if goals else 0, today_work)
            else:
                logger.warning("Cloud heartbeat failed: %s %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Cloud heartbeat error: %s", e)


class HariServices:
    """Main service coordinator"""

    def __init__(self):
        self.logger = logging.getLogger("main")
        self.running = True

        # Initialize LLM provider from config, then handlers
        provider = create_llm_provider() if LLM_PROVIDERS_AVAILABLE else None
        self.notifier = TelegramNotifier()
        self.analytics = AnalyticsHandler(llm_provider=provider)
        self.llm_handler = LLMHandler(provider=provider)

        # Queue for SSE subscribers (thread-safe)
        self.sse_event_queue = queue.Queue()

        # Pomodoro engine (replaces C daemon): emits events to log and callback
        def on_pomodoro_event(event):
            self.analytics.process_event(event)
            self.notifier.handle_event(event)
            try:
                self.sse_event_queue.put_nowait(event)
            except Exception:
                pass

        self.pomodoro_engine = PomodoroEngine(on_event_cb=on_pomodoro_event)
        self.pomodoro_engine.start_background_thread()

        self.llm_server = LLMServer(
            self.llm_handler, self.analytics, pomodoro_engine=self.pomodoro_engine
        )
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.llm_server.stop()
    
    def run(self):
        """Start all services"""
        self.logger.info("=" * 60)
        self.logger.info("Hari Services - Unified Python Service (with Analytics)")
        self.logger.info("=" * 60)
        
        if self.llm_handler.use_ollama and self.llm_handler.ollama_available:
            p = self.llm_handler.provider
            name = getattr(p, "model", None) or getattr(p, "model_id", None) or "unknown"
            self.logger.info(f"LLM: {p.__class__.__name__.replace('Provider', '')} ({name})")
        else:
            self.logger.info("LLM: Pattern matching fallback")
        
        if self.notifier.enabled:
            self.logger.info(f"Notifications: Telegram enabled")
        else:
            self.logger.info("Notifications: Disabled")
        
        self.logger.info("Analytics: Real-time processing enabled")

        api_port = _get_api_port()
        if WEBAPI_AVAILABLE:
            self.logger.info(f"Web API: http://127.0.0.1:{api_port} (docs: http://127.0.0.1:{api_port}/docs)")
            web_app = create_web_app(self.llm_server, self.analytics, self.sse_event_queue)
            if web_app is not None:
                def run_api():
                    uvicorn.run(web_app, host="127.0.0.1", port=api_port, log_level="warning")
                api_thread = threading.Thread(target=run_api, daemon=True)
                api_thread.start()
        else:
            self.logger.info("Web API: disabled (pip install fastapi uvicorn)")

        # Cloud heartbeat (goal + today's minutes for self-hosted goal reminders)
        cloud_thread = threading.Thread(
            target=_cloud_heartbeat_loop,
            args=(self.analytics, self, self.logger),
            kwargs={'interval_seconds': 3600},
            daemon=True,
        )
        cloud_thread.start()
        
        self.logger.info("=" * 60)
        
        llm_thread = threading.Thread(target=self.llm_server.start, daemon=True)
        llm_thread.start()
        
        try:
            while self.running:
                llm_thread.join(timeout=1.0)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        
        self.logger.info("All services stopped")


def main():
    services = HariServices()
    try:
        services.run()
    except Exception as e:
        logging.error(f"FATAL: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
