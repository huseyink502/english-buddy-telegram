"""Optional permanent progress storage via a free external PostgreSQL database.

Set DATABASE_URL (for example, a Neon pooled PostgreSQL connection string).
Without it, the existing SQLite storage remains available for local development.
"""
from datetime import date, timedelta

import psycopg


class PostgresProgressDB:
    def __init__(self, url: str) -> None:
        self.url = url
        self.path = url
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    day INTEGER NOT NULL DEFAULT 1,
                    quizzes INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vocabulary (
                    user_id BIGINT NOT NULL,
                    english TEXT NOT NULL,
                    turkish TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 0,
                    due TEXT NOT NULL,
                    PRIMARY KEY (user_id, english)
                )
            """)

    def _connect(self):
        return psycopg.connect(self.url, connect_timeout=15)

    def ensure_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users(user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                (user_id,),
            )

    def day(self, user_id: int) -> int:
        self.ensure_user(user_id)
        with self._connect() as conn:
            return int(conn.execute(
                "SELECT day FROM users WHERE user_id=%s", (user_id,)
            ).fetchone()[0])

    def next_day(self, user_id: int, max_day: int = 7) -> int:
        self.ensure_user(user_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET day=LEAST(day+1, %s) WHERE user_id=%s",
                (max_day, user_id),
            )
        return self.day(user_id)

    def learn_words(self, user_id: int, words: list[tuple[str, str]]) -> None:
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO vocabulary(user_id, english, turkish, due)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (user_id, english) DO NOTHING""",
                    [(user_id, en, tr, tomorrow) for en, tr in words],
                )

    def due_words(self, user_id: int, limit: int = 5) -> list[tuple[str, str]]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT english, turkish FROM vocabulary "
                "WHERE user_id=%s AND due<=%s "
                "ORDER BY due, english LIMIT %s",
                (user_id, date.today().isoformat(), limit),
            ).fetchall()

    def review_result(self, user_id: int, english: str, correct: bool) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT level FROM vocabulary WHERE user_id=%s AND english=%s",
                (user_id, english),
            ).fetchone()
            if row is None:
                return
            next_level = min(row[0] + 1, 4) if correct else 0
            days = [0, 3, 7, 14, 30][next_level]
            due = (date.today() + timedelta(days=days)).isoformat()
            conn.execute(
                "UPDATE vocabulary SET level=%s, due=%s "
                "WHERE user_id=%s AND english=%s",
                (next_level, due, user_id, english),
            )

    def log_quiz(self, user_id: int, correct: int, total: int) -> None:
        self.ensure_user(user_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET quizzes=quizzes+1, correct=correct+%s, total=total+%s "
                "WHERE user_id=%s", (correct, total, user_id),
            )

    def stats(self, user_id: int) -> dict:
        self.ensure_user(user_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT day, quizzes, correct, total FROM users WHERE user_id=%s",
                (user_id,),
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM vocabulary WHERE user_id=%s", (user_id,)
            ).fetchone()[0]
        return {
            "day": row[0], "quizzes": row[1], "correct": row[2],
            "total": row[3], "words": count,
        }
