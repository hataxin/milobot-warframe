"""Plugin-owned SQLite response cache without process-global connections."""

import json
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachedResponse:
    """A decoded response and the time it was successfully retrieved."""

    body: Any
    fetched_at: float


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create plugin cache, subscription rule, and delivery tables if absent."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS responses "
        "(key TEXT PRIMARY KEY, body TEXT NOT NULL, fetched_at REAL NOT NULL)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS subscriptions "
        "(stream_id TEXT NOT NULL, event_type TEXT NOT NULL, "
        "filter_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, "
        "PRIMARY KEY (stream_id, event_type))"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS subscription_deliveries "
        "(stream_id TEXT NOT NULL, event_key TEXT NOT NULL, delivered_at REAL NOT NULL, "
        "PRIMARY KEY (stream_id, event_key))"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_deliveries_at ON subscription_deliveries (delivered_at)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS foundry_reminders "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, stream_id TEXT NOT NULL, "
        "user_id TEXT NOT NULL, item_name TEXT NOT NULL, due_at REAL NOT NULL)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_foundry_due ON foundry_reminders (due_at)")
    connection.commit()


class ResponseCache:
    """Persist responses under the plugin data directory.

    Every operation owns its connection. Call these methods with asyncio.to_thread
    so SQLite disk operations do not block the shared third-party Runner loop.
    """

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "milobot.sqlite3"

    def initialize(self) -> None:
        """Create the plugin directory and cache/subscription tables."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5.0)) as connection:
            ensure_schema(connection)

    def get(self, key: str) -> CachedResponse | None:
        """Return the last successful response, removing corrupt cached JSON."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as connection:
            row = connection.execute(
                "SELECT body, fetched_at FROM responses WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            try:
                return CachedResponse(json.loads(row[0]), float(row[1]))
            except (ValueError, TypeError):
                connection.execute("DELETE FROM responses WHERE key = ?", (key,))
                connection.commit()
                return None

    def put(self, key: str, body: Any, *, fetched_at: float | None = None) -> None:
        """Atomically replace a successfully validated response."""
        timestamp = time.time() if fetched_at is None else fetched_at
        encoded = json.dumps(body, ensure_ascii=False)
        with closing(sqlite3.connect(self.path, timeout=5.0)) as connection:
            connection.execute(
                "INSERT INTO responses (key, body, fetched_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET body=excluded.body, fetched_at=excluded.fetched_at",
                (key, encoded, timestamp),
            )
            connection.commit()
