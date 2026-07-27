import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "memory.sqlite")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turn_context (
                id TEXT PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
                sql_used TEXT,
                result_schema TEXT,
                result_summary TEXT,
                chart_spec TEXT
            )
        """)

# Initialize database on module import
init_db()

def create_session(user_id="default", title="New Chat"):
    session_id = str(uuid.uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)", (session_id, user_id, title))
    return session_id

def get_sessions(user_id="default"):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return [dict(row) for row in cur.fetchall()]

def add_message(session_id, role, content):
    message_id = str(uuid.uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)", 
                     (message_id, session_id, role, content))
    return message_id

def get_messages(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
        return [dict(row) for row in cur.fetchall()]

def save_turn_context(session_id, message_id, sql_used=None, result_schema=None, result_summary=None, chart_spec=None):
    context_id = str(uuid.uuid4())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO turn_context (id, session_id, message_id, sql_used, result_schema, result_summary, chart_spec)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (context_id, session_id, message_id, sql_used, result_schema, result_summary, chart_spec))

def get_recent_turn_contexts(session_id, limit=2):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("""
            SELECT tc.*, m.content as message_content 
            FROM turn_context tc
            JOIN messages m ON tc.message_id = m.id
            WHERE tc.session_id = ? 
            ORDER BY m.created_at DESC LIMIT ?
        """, (session_id, limit))
        return [dict(row) for row in cur.fetchall()]

def delete_session(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
