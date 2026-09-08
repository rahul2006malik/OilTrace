"""
backend/app/db.py — Centralized SQLite Concurrency & WAL Management (SIH26143)

Enforces WAL mode, busy timeouts, and connection isolation to eliminate
sqlite3.OperationalError: database is locked across async FastAPI workers,
background threads, and live telemetry feeds.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Union

logger = logging.getLogger("oiltrace_db")

SQLITE_BUSY_TIMEOUT_MS = 15000
SQLITE_CONNECT_TIMEOUT_S = 15.0


def configure_sqlite_pragmas(con: sqlite3.Connection) -> sqlite3.Connection:
    """
    Applies production-grade concurrency pragmas on SQLite connections:
    - WAL mode: Readers do not block writers, and writers do not block readers.
    - busy_timeout: 10 seconds wait instead of raising database is locked immediately.
    - synchronous=NORMAL: Optimal durability and maximum write throughput in WAL mode.
    - foreign_keys=ON: Relational integrity enforcement.
    """
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA foreign_keys=ON;")
    except Exception as e:
        logger.debug("[db] Error setting pragmas: %s", e)
    return con


def get_sqlite_connection(
    db_path: Union[str, Path],
    timeout: float = SQLITE_CONNECT_TIMEOUT_S,
) -> sqlite3.Connection:
    """Returns a newly opened, pragma-configured SQLite connection."""
    path = Path(db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=timeout)
    return configure_sqlite_pragmas(con)


@contextmanager
def sqlite_connection(
    db_path: Union[str, Path],
    timeout: float = SQLITE_CONNECT_TIMEOUT_S,
) -> Generator[sqlite3.Connection, None, None]:
    """Safe context manager that guarantees closing the connection even on exceptions."""
    con = get_sqlite_connection(db_path, timeout=timeout)
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass


def ensure_db_wal(db_path: Union[str, Path]) -> None:
    """Helper to ensure an existing SQLite database file has WAL mode and indexes initialized."""
    path = Path(db_path).resolve()
    if path.exists():
        with sqlite_connection(path) as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")
            con.commit()
