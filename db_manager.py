import sqlite3
from datetime import datetime
import json

DB_FILE = "agent.db"
STATE_FILE = "agent_state.json"

def get_connection():
    """
    Opens a connection to the SQLite database.
    """

    conn = sqlite3.connect(DB_FILE)
    
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    """
    Creates the emails table if it doesn't exist.
    """

    conn = get_connection()

    # cursor is like a pen . to read and write in db.
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            category TEXT,
            processed_at TEXT)
            """)

    conn.commit()
    conn.close()

def insert_email_ids(email_ids: list):
    """
    Bulk inserts all email IDs as 'pending'.
    Uses INSERT OR IGNORE so duplicate IDs are skipped safely — no crashes on re-run.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executemany("""
            INSERT OR IGNORE INTO emails (id, status)
            VALUES (? , 'pending')
            """, [(email_id,) for email_id in email_ids])
    
    conn.commit()
    conn.close()

def get_pending_emails(batch_size: int = 50) -> list:
    """
    Fetches next batch of unprocessed emails.
    Returns list of email Ids with status 'pending'
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM emails
        WHERE status = 'pending'
        LIMIT ?
    """,(batch_size,))

    rows = cursor.fetchall()
    conn.close()

    return [row["id"] for row in rows]

def mark_processed(email_id: str, category: str):
    """
    Updates a single email's status to 'processed' and saves its category and timestamp.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE emails
        SET status = 'processed',
        category = ?,
        processed_at = ?
        WHERE id = ?
    """, (category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), email_id))
    
    conn.commit()
    conn.close()

def mark_dry_run(email_id: str, category: str):
    """Marks email as classified during dry run — not yet acted on."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE emails
        SET status = 'dry_run',
        category = ?,
        processed_at = ?
        WHERE id = ?
    """, (category, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), email_id))
    conn.commit()
    conn.close()


def reset_dry_run_emails() -> int:
    """Resets dry_run emails back to pending for re-processing. Returns count."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE emails
        SET status = 'pending',
        category = NULL,
        processed_at = NULL
        WHERE status = 'dry_run'
    """)
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def mark_failed(email_id: str):
    """
    Marks email as failed if AI classification crashes.
    We can retry these later instead of losing track.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE emails
        SET status = 'failed'
        WHERE id = ?
    """, (email_id,))

    conn.commit()
    conn.close()


def get_stats() -> dict:
    """
    Returns a summary of how many emails are in each status.
    Useful to print progress during first run.
    """

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*) AS count
        FROM emails
        GROUP BY status
    """)

    rows = cursor.fetchall()
    conn.close()

    return {row["status"]: row["count"] for row in rows}


def load_state() -> dict:
    """Load historyId and first run flag from JSON."""
    import os
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "is_first_run": True,
        "last_history_id": None,
        "last_run": None
    }


def save_state(state: dict):
    """Save historyId and first run flag to JSON."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def complete_first_run(history_id: str):
    """Called once after ALL emails processed on first run."""
    state = {
        "is_first_run": False,
        "last_history_id": history_id,
        "last_run": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_state(state)


def update_after_cron(history_id: str):
    """Called after every weekly cron run."""
    state = load_state()
    state["last_history_id"] = history_id
    state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_state(state)
