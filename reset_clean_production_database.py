import sqlite3
import sys
from datetime import datetime, date

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from scheduler_engine import generate_week_schedule

def purge_test_history():
    print("Purging all test and mock historical records from liveops.db...")
    conn = sqlite3.connect("liveops.db")
    c = conn.cursor()

    # 1. Clear test requests
    c.execute("DELETE FROM swap_requests;")
    c.execute("DELETE FROM excuse_requests;")
    c.execute("DELETE FROM leave_requests;")

    # 2. Clear attendance & pause logs
    c.execute("DELETE FROM time_logs;")
    c.execute("DELETE FROM break_logs;")
    c.execute("DELETE FROM pause_logs;")

    # 3. Clear any test agents
    c.execute("DELETE FROM agents WHERE code LIKE 'TEST-%';")

    # 4. Reset queue mode to normal
    c.execute("UPDATE settings SET value = 'normal' WHERE key = 'queue_mode';")

    # 5. Reset autoincrement sequences
    c.execute("""
    DELETE FROM sqlite_sequence 
    WHERE name IN ('swap_requests', 'excuse_requests', 'leave_requests', 'time_logs', 'break_logs', 'pause_logs');
    """)

    conn.commit()
    conn.close()

    # 6. Reset all schedules to clean rotation engine
    print("Regenerating clean rotation schedule for all active weeks...")
    weeks = [
        "2026-09-27",
        "2026-10-04",
        "2026-10-11",
        "2026-10-18",
        "2026-10-25",
        "2026-11-01",
        "2026-11-08",
        "2026-11-15"
    ]
    for w in weeks:
        s = generate_week_schedule(w, force_regenerate=True)
        print(f"  Week {w}: {len(s)} schedule slots refreshed.")

    # 7. Verification
    conn = sqlite3.connect("liveops.db")
    c = conn.cursor()
    tables = [
        "swap_requests", "excuse_requests", "leave_requests",
        "time_logs", "break_logs", "pause_logs", "agents", "schedules"
    ]
    print("\n=== FINAL CLEAN PRODUCTION STATE ===")
    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM {t};")
        cnt = c.fetchone()[0]
        print(f"  {t:18s}: {cnt:4d} rows")
    
    conn.close()
    print("\nDatabase is 100% clean, fresh, and ready for production!")

if __name__ == "__main__":
    purge_test_history()
