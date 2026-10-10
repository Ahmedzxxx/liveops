import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "liveops.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Agents table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        code TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'agent', -- 'agent' or 'manager'
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Master Schedules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_start_date TEXT NOT NULL, -- YYYY-MM-DD (Always Sunday)
        agent_id INTEGER NOT NULL,
        day_of_week INTEGER NOT NULL, -- 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
        date TEXT NOT NULL, -- YYYY-MM-DD
        shift_type TEXT NOT NULL, -- 'work', 'off', 'leave'
        shift_hours TEXT NOT NULL DEFAULT '10:00 - 19:00',
        is_holiday INTEGER NOT NULL DEFAULT 0,
        holiday_name TEXT,
        pay_multiplier INTEGER NOT NULL DEFAULT 1, -- 1=Normal, 2=Double, 3=Triple
        FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE CASCADE,
        UNIQUE (agent_id, date)
    );
    """)

    # 3. Attendance & Time logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS time_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        clock_in TEXT, -- HH:MM:SS
        clock_out TEXT, -- HH:MM:SS
        total_work_minutes INTEGER NOT NULL DEFAULT 0,
        late_minutes INTEGER NOT NULL DEFAULT 0,
        is_compensated INTEGER NOT NULL DEFAULT 0, -- 1 if late was fully made up
        overtime_minutes INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'off', -- 'on_shift', 'on_break', 'completed', 'in_meeting', 'off'
        FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE CASCADE,
        UNIQUE (agent_id, date)
    );
    """)

    # 4. Break logs table (Cumulative break support)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS break_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        start_time TEXT NOT NULL, -- HH:MM:SS
        end_time TEXT, -- HH:MM:SS (NULL if currently active)
        duration_minutes INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE CASCADE
    );
    """)

    # 4.1. Pause logs table (Separate Meeting & Emergency Pause support)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pause_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        pause_type TEXT NOT NULL, -- 'meeting' or 'emergency'
        start_time TEXT NOT NULL, -- HH:MM:SS
        end_time TEXT, -- HH:MM:SS (NULL if currently active)
        duration_minutes INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE CASCADE
    );
    """)

    # 5. Swap requests table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS swap_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id INTEGER NOT NULL,
        target_agent_id INTEGER NOT NULL,
        requester_date TEXT NOT NULL, -- YYYY-MM-DD
        target_date TEXT NOT NULL, -- YYYY-MM-DD
        status TEXT NOT NULL DEFAULT 'pending_peer', -- 'pending_peer', 'pending_manager', 'approved', 'rejected'
        peer_comment TEXT,
        manager_comment TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (requester_id) REFERENCES agents (id) ON DELETE CASCADE,
        FOREIGN KEY (target_agent_id) REFERENCES agents (id) ON DELETE CASCADE
    );
    """)

    # 6. Excuse requests table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS excuse_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        from_time TEXT NOT NULL, -- HH:MM
        to_time TEXT NOT NULL, -- HH:MM
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
        manager_comment TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE CASCADE
    );
    """)

    # 7. Official Leaves table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id INTEGER NOT NULL,
        date TEXT NOT NULL, -- YYYY-MM-DD
        leave_type TEXT NOT NULL, -- 'annual', 'sick', 'emergency', 'comp_off'
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (agent_id) REFERENCES agents (id) ON DELETE CASCADE
    );
    """)

    # 8. System settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    # Default settings
    default_settings = [
        ("queue_mode", "normal"),  # 'normal' or 'meeting'
        ("shift_start", "10:00"),
        ("shift_end", "19:00"),
        ("break_limit_minutes", "60"),
        ("target_queue_size", "5"),
        ("telegram_bot_token", "8947096598:AAFNWrxNqq_lZFP9_nhd6tgm2D3GYwIVmbk"),
        ("telegram_chat_id", "6155717959"),
        ("rotation_anchor_date", "2026-10-11")  # Sunday anchor date for 6-week rotation
    ]
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (key, val))

    # Seed initial agents
    initial_agents = [
        ("Rana", "RN-101", "rana123", "agent"),
        ("Bassant ragab", "BR-102", "bassant123", "agent"),
        ("Sama", "SM-103", "sama123", "agent"),
        ("Tooba", "TB-104", "tooba123", "agent"),
        ("Rahma amr", "RA-105", "rahma123", "agent"),
        ("Nesma ibrahim", "NI-106", "nesma123", "agent"),
        ("مدير العمليات (Manager)", "ADMIN-01", "admin2026", "manager")
    ]
    now_str = datetime.now().isoformat()
    for name, code, password, role in initial_agents:
        cursor.execute("""
        INSERT OR IGNORE INTO agents (name, code, password, role, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?);
        """, (name, code, password, role, now_str))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
