import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('liveops.db')
c = conn.cursor()

# Get agent IDs
agents = dict(c.execute("SELECT code, id FROM agents").fetchall())
print("Agent IDs:", agents)

# Expected off-days for week 2026-10-11 to 2026-10-17
# Dates:
# 2026-10-11 (Sun, day 0): ALL WORK
# 2026-10-12 (Mon, day 1): RN-101, TB-104 OFF
# 2026-10-13 (Tue, day 2): SM-103 OFF
# 2026-10-14 (Wed, day 3): BR-102 OFF
# 2026-10-15 (Thu, day 4): RA-105 OFF
# 2026-10-16 (Fri, day 5): ALL OFF (الجمعة إجازة)
# 2026-10-17 (Sat, day 6): NI-106 OFF

dates = [
    ('2026-10-11', 0),
    ('2026-10-12', 1),
    ('2026-10-13', 2),
    ('2026-10-14', 3),
    ('2026-10-15', 4),
    ('2026-10-16', 5),
    ('2026-10-17', 6)
]

off_map = {
    '2026-10-11': set(),
    '2026-10-12': {'RN-101', 'TB-104'},
    '2026-10-13': {'SM-103'},
    '2026-10-14': {'BR-102'},
    '2026-10-15': {'RA-105'},
    '2026-10-16': {'RN-101', 'BR-102', 'SM-103', 'TB-104', 'RA-105', 'NI-106'},
    '2026-10-17': {'NI-106'}
}

# Update or insert for each agent and each date
for dt, dow in dates:
    for code, aid in agents.items():
        if code == 'ADMIN-01':
            continue
        is_off = code in off_map[dt]
        if dt == '2026-10-16':
            shift_type = 'off'
            shift_hours = 'OFF (الجمعة إجازة)'
        elif is_off:
            shift_type = 'off'
            shift_hours = 'OFF (إجازة أسبوعية)'
        else:
            shift_type = 'work'
            shift_hours = '10:00 - 19:00'
        
        # Check if record exists
        row = c.execute("SELECT id FROM schedules WHERE agent_id = ? AND date = ?", (aid, dt)).fetchone()
        if row:
            c.execute("""
                UPDATE schedules 
                SET shift_type = ?, shift_hours = ?, day_of_week = ?, week_start_date = '2026-10-11'
                WHERE id = ?
            """, (shift_type, shift_hours, dow, row[0]))
        else:
            c.execute("""
                INSERT INTO schedules (week_start_date, agent_id, day_of_week, date, shift_type, shift_hours, is_holiday, holiday_name, pay_multiplier)
                VALUES ('2026-10-11', ?, ?, ?, ?, ?, 0, '', 1.0)
            """, (aid, dow, dt, shift_type, shift_hours))

conn.commit()

# Verify
print("\n--- Verified Schedule 2026-10-11 to 2026-10-17 ---")
sched = c.execute("""
    SELECT s.date, s.day_of_week, a.code, a.name, s.shift_type, s.shift_hours
    FROM schedules s
    JOIN agents a ON s.agent_id = a.id
    WHERE s.date BETWEEN '2026-10-11' AND '2026-10-17'
    ORDER BY s.date, a.code
""").fetchall()

for r in sched:
    print(r)

conn.close()
