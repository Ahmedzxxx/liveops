import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('liveops.db')
c = conn.cursor()

# 1. Purge operational log tables
tables_to_clear = ['time_logs', 'break_logs', 'pause_logs', 'swap_requests', 'excuse_requests', 'leave_requests']
for t in tables_to_clear:
    c.execute(f"DELETE FROM {t}")
    print(f"Cleared {t}")

# 2. Delete test agents if any
c.execute("DELETE FROM agents WHERE code LIKE 'TEST-%'")

# 3. Reset sqlite_sequence for wiped tables
placeholders = ','.join('?' for _ in tables_to_clear)
c.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})", tables_to_clear)

# 4. Reset settings queue_mode to normal
c.execute("UPDATE settings SET value='normal' WHERE key='queue_mode'")

conn.commit()

# Verification
print("\n--- Table Counts After Clean ---")
for t in tables_to_clear:
    count = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"{t}: {count}")

agents = c.execute("SELECT code, name, role FROM agents ORDER BY code").fetchall()
print(f"\nAgents in DB ({len(agents)}):")
for a in agents:
    print(f"  {a[0]}: {a[1]} ({a[2]})")

settings = c.execute("SELECT key, value FROM settings").fetchall()
print(f"\nSettings: {settings}")

# Check next week schedule (2026-10-11 to 2026-10-17)
print("\n--- Schedule 2026-10-11 to 2026-10-17 ---")
sched = c.execute("""
    SELECT date, agent_code, is_off, shift_start, shift_end 
    FROM schedules 
    WHERE date BETWEEN '2026-10-11' AND '2026-10-17' 
    ORDER BY date, agent_code
""").fetchall()

day_map = {}
for s in sched:
    d, code, is_off, start, end = s
    if d not in day_map:
        day_map[d] = []
    day_map[d].append((code, "OFF" if is_off else f"{start}-{end}"))

for d, entries in day_map.items():
    print(f"Date {d}:")
    for code, st in entries:
        print(f"  {code}: {st}")

conn.close()
