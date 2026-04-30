import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "app_state.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    return conn


def load_state(key: str, default: Any):
    with _connect() as conn:
        row = conn.execute("SELECT payload FROM app_state WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return default


def save_state(key: str, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO app_state(key, payload, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
            """,
            (key, payload),
        )
