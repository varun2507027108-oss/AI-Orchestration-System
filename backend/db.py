import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_PATH = "founder_os.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                session_id TEXT,
                stage_name TEXT,
                payload_json TEXT,
                version INTEGER,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_log (
                session_id TEXT,
                stage_name TEXT,
                reasoning TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()

def save_artifact(session_id: str, stage_name: str, payload: Dict[str, Any]) -> int:
    init_db()
    conn = get_db_connection()
    try:
        # Find the maximum version for this session and stage
        cursor = conn.execute(
            "SELECT MAX(version) FROM artifacts WHERE session_id = ? AND stage_name = ?",
            (session_id, stage_name)
        )
        row = cursor.fetchone()
        max_version = row[0] if row and row[0] is not None else 0
        new_version = max_version + 1
        
        conn.execute(
            "INSERT INTO artifacts (session_id, stage_name, payload_json, version, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, stage_name, json.dumps(payload), new_version, datetime.now().isoformat())
        )
        conn.commit()
        return new_version
    finally:
        conn.close()

def get_latest_artifact(session_id: str, stage_name: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT payload_json FROM artifacts WHERE session_id = ? AND stage_name = ? ORDER BY version DESC LIMIT 1",
            (session_id, stage_name)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row["payload_json"])
        return None
    finally:
        conn.close()

def get_latest_artifact_version(session_id: str, stage_name: str) -> int:
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT MAX(version) FROM artifacts WHERE session_id = ? AND stage_name = ?",
            (session_id, stage_name)
        )
        row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
        return 0
    finally:
        conn.close()

def add_decision_log(session_id: str, stage_name: str, reasoning: str):
    init_db()
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO decision_log (session_id, stage_name, reasoning, created_at) VALUES (?, ?, ?, ?)",
            (session_id, stage_name, reasoning, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def get_decision_log(session_id: str) -> List[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT stage_name, reasoning, created_at FROM decision_log WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
