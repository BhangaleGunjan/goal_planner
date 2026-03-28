import sqlite3
import json
from datetime import datetime, date

DB_PATH = "planner.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            goal TEXT NOT NULL,
            profile TEXT NOT NULL,
            plan_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            current_phase INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            phase_index INTEGER NOT NULL,
            task_index INTEGER NOT NULL,
            completed INTEGER DEFAULT 0,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            plan_id INTEGER NOT NULL REFERENCES plans(id),
            last_checkin TEXT,
            current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0,
            total_checkins INTEGER DEFAULT 0
        );
    """)

    conn.commit()
    conn.close()

# ===== USER QUERIES =====

def create_user(username: str, password_hash: str) -> int:
    conn = get_db()
    try:
        c = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, datetime.utcnow().isoformat())
        )
        conn.commit()
        return c.lastrowid
    finally:
        conn.close()

def get_user_by_username(username: str):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_user_by_id(user_id: int):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

# ===== PLAN QUERIES =====

def save_plan(user_id: int, goal: str, profile: dict, plan_data: dict) -> int:
    conn = get_db()
    try:
        c = conn.execute(
            "INSERT INTO plans (user_id, goal, profile, plan_data, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, goal, json.dumps(profile), json.dumps(plan_data), datetime.utcnow().isoformat())
        )
        plan_id = c.lastrowid

        # Pre-populate task rows for each phase/step
        plan = plan_data
        for pi, phase in enumerate(plan.get("phases", [])):
            for ti, _ in enumerate(phase.get("steps", [])):
                conn.execute(
                    "INSERT INTO tasks (plan_id, phase_index, task_index) VALUES (?, ?, ?)",
                    (plan_id, pi, ti)
                )

        # Create streak row
        conn.execute(
            "INSERT INTO streaks (user_id, plan_id) VALUES (?, ?)",
            (user_id, plan_id)
        )

        conn.commit()
        return plan_id
    finally:
        conn.close()

def get_user_plans(user_id: int) -> list:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM plans WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_plan(plan_id: int, user_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM plans WHERE id = ? AND user_id = ?",
            (plan_id, user_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def update_plan_data(plan_id: int, user_id: int, new_plan_data: dict, new_tasks_from_phase: int):
    """
    Overwrites plan_data and re-creates task rows for phases from new_tasks_from_phase onwards.
    Completed task rows before that phase are preserved.
    """
    conn = get_db()
    try:
        # Update plan JSON
        conn.execute(
            "UPDATE plans SET plan_data = ? WHERE id = ? AND user_id = ?",
            (json.dumps(new_plan_data), plan_id, user_id)
        )

        # Delete task rows only for the phases being replaced
        conn.execute(
            "DELETE FROM tasks WHERE plan_id = ? AND phase_index >= ?",
            (plan_id, new_tasks_from_phase)
        )

        # Re-insert task rows for the new phases
        for pi, phase in enumerate(new_plan_data.get("phases", [])):
            if pi < new_tasks_from_phase:
                continue
            for ti, _ in enumerate(phase.get("steps", [])):
                conn.execute(
                    "INSERT INTO tasks (plan_id, phase_index, task_index) VALUES (?, ?, ?)",
                    (plan_id, pi, ti)
                )

        conn.commit()
    finally:
        conn.close()

def delete_plan(plan_id: int, user_id: int):
    conn = get_db()
    try:
        conn.execute("DELETE FROM tasks WHERE plan_id = ?", (plan_id,))
        conn.execute("DELETE FROM streaks WHERE plan_id = ?", (plan_id,))
        conn.execute("DELETE FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
        conn.commit()
    finally:
        conn.close()

# ===== TASK QUERIES =====

def get_tasks(plan_id: int) -> list:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE plan_id = ?",
            (plan_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def toggle_task(plan_id: int, phase_index: int, task_index: int) -> bool:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT completed FROM tasks WHERE plan_id=? AND phase_index=? AND task_index=?",
            (plan_id, phase_index, task_index)
        ).fetchone()

        if not row:
            return False

        new_state = 0 if row["completed"] else 1
        completed_at = datetime.utcnow().isoformat() if new_state else None

        conn.execute(
            "UPDATE tasks SET completed=?, completed_at=? WHERE plan_id=? AND phase_index=? AND task_index=?",
            (new_state, completed_at, plan_id, phase_index, task_index)
        )
        conn.commit()
        return bool(new_state)
    finally:
        conn.close()

# ===== STREAK QUERIES =====

def get_streak(plan_id: int, user_id: int):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM streaks WHERE plan_id=? AND user_id=?",
            (plan_id, user_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def checkin(plan_id: int, user_id: int) -> dict:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM streaks WHERE plan_id=? AND user_id=?",
            (plan_id, user_id)
        ).fetchone()

        if not row:
            return {}

        today = date.today().isoformat()
        last = row["last_checkin"]

        current = row["current_streak"]
        longest = row["longest_streak"]
        total = row["total_checkins"]

        if last == today:
            # Already checked in today
            return {"streak": current, "longest": longest, "total": total, "already_done": True}

        from datetime import timedelta
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        if last == yesterday:
            current += 1
        else:
            current = 1  # streak broken

        longest = max(longest, current)
        total += 1

        conn.execute(
            """UPDATE streaks SET last_checkin=?, current_streak=?, longest_streak=?, total_checkins=?
               WHERE plan_id=? AND user_id=?""",
            (today, current, longest, total, plan_id, user_id)
        )
        conn.commit()

        return {"streak": current, "longest": longest, "total": total, "already_done": False}
    finally:
        conn.close()