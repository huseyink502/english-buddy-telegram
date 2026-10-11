"""Persistent progress and a lightweight spaced-repetition schedule (SQLite)."""

import sqlite3
from datetime import date, timedelta
from pathlib import Path


class ProgressDB:
    def __init__(self, path: str = "english_buddy.sqlite3") -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    day INTEGER NOT NULL DEFAULT 1,
                    quizzes INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS vocabulary (
                    user_id INTEGER NOT NULL,
                    english TEXT NOT NULL,
                    turkish TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 0,
                    due TEXT NOT NULL,
                    PRIMARY KEY (user_id, english)
                );
            """)

    def _connect(self):
        return sqlite3.connect(self.path)

    def ensure_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users(user_id) VALUES (?)", (user_id,))

    def day(self, user_id: int) -> int:
        self.ensure_user(user_id)
        with self._connect() as conn:
            return int(conn.execute("SELECT day FROM users WHERE user_id=?", (user_id,)).fetchone()[0])

    def next_day(self, user_id: int, max_day: int = 7) -> int:
        self.ensure_user(user_id)
        with self._connect() as conn:
            conn.execute("UPDATE users SET day=MIN(day+1, ?) WHERE user_id=?", (max_day, user_id))
        return self.day(user_id)

    def learn_words(self, user_id: int, words: list[tuple[str, str]]) -> None:
        """New cards first become due on the next day; repeating /lesson does not reset them."""
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO vocabulary(user_id, english, turkish, due) VALUES (?, ?, ?, ?)",
                [(user_id, en, tr, tomorrow) for en, tr in words],
            )

    def due_words(self, user_id: int, limit: int = 5) -> list[tuple[str, str]]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT english, turkish FROM vocabulary WHERE user_id=? AND due<=? "
                "ORDER BY due, english LIMIT ?", (user_id, date.today().isoformat(), limit),
            ).fetchall()

    def review_result(self, user_id: int, english: str, correct: bool) -> None:
        """Simple intervals: after successful reviews +3, +7, +14, +30 days; errors repeat today."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT level FROM vocabulary WHERE user_id=? AND english=?",
                (user_id, english),
            ).fetchone()
            if row is None:
                return
            next_level = min(row[0] + 1, 4) if correct else 0
            days = [0, 3, 7, 14, 30][next_level]
            due = (date.today() + timedelta(days=days)).isoformat()
            conn.execute(
                "UPDATE vocabulary SET level=?, due=? WHERE user_id=? AND english=?",
                (next_level, due, user_id, english),
            )

    def log_quiz(self, user_id: int, correct: int, total: int) -> None:
        self.ensure_user(user_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET quizzes=quizzes+1, correct=correct+?, total=total+? WHERE user_id=?",
                (correct, total, user_id),
            )

    def stats(self, user_id: int) -> dict:
        self.ensure_user(user_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT day, quizzes, correct, total FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM vocabulary WHERE user_id=?", (user_id,)
            ).fetchone()[0]
        return {"day": row[0], "quizzes": row[1], "correct": row[2],
                "total": row[3], "words": count}
