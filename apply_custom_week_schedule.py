import sqlite3
import sys
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

def apply_schedule():
    week_start = date(2026, 10, 11)
    week_start_str = week_start.isoformat()

    conn = sqlite3.connect("liveops.db")
    c = conn.cursor()

    # Agent ID mapping
    # 1: RN-101 (Rana) -> Off: Mon (2026-10-12), Fri (2026-10-16)
    # 2: BR-102 (Bassant) -> Off: Wed (2026-10-14), Fri (2026-10-16)
    # 3: SM-103 (Sama) -> Off: Tue (2026-10-13), Fri (2026-10-16)
    # 4: TB-104 (Tooba) -> Off: Sat (2026-10-17), Fri (2026-10-16) [Sunday 10-11 is WORK from office]
    # 5: RA-105 (Rahma) -> Off: Thu (2026-10-15), Fri (2026-10-16)
    # 6: NI-106 (Nesma) -> Off: Sat (2026-10-17), Fri (2026-10-16)

    off_days_map = {
        1: [1, 5],       # Rana: Mon, Fri
        2: [3, 5],       # Bassant: Wed, Fri
        3: [2, 5],       # Sama: Tue, Fri
        4: [6, 5],       # Tooba: Sat, Fri (Sunday is WORK from office)
        5: [4, 5],       # Rahma: Thu, Fri
        6: [6, 5],       # Nesma: Sat, Fri
    }

    print(f"Applying custom schedule for week starting {week_start_str}...")

    # Delete existing entries for this week
    c.execute("DELETE FROM schedules WHERE week_start_date = ?;", (week_start_str,))

    for agent_id, offs in off_days_map.items():
        for day_idx in range(7):
            cur_date = week_start + timedelta(days=day_idx)
            cur_date_str = cur_date.isoformat()

            if day_idx == 5:
                # Friday fixed
                shift_type = "off"
                shift_hours = "OFF (الجمعة)"
            elif day_idx in offs:
                shift_type = "off"
                shift_hours = "OFF (إجازة دورية)"
            else:
                shift_type = "work"
                shift_hours = "10:00 - 19:00"

            c.execute("""
            INSERT INTO schedules (
                week_start_date, agent_id, day_of_week, date,
                shift_type, shift_hours, is_holiday, holiday_name, pay_multiplier
            ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, 1);
            """, (week_start_str, agent_id, day_idx, cur_date_str, shift_type, shift_hours))

    conn.commit()

    # Query and display table
    c.execute("""
    SELECT s.date, s.day_of_week, a.code, a.name, s.shift_type, s.shift_hours
    FROM schedules s
    JOIN agents a ON s.agent_id = a.id
    WHERE s.week_start_date = ?
    ORDER BY s.date ASC, a.id ASC;
    """, (week_start_str,))
    rows = c.fetchall()

    day_names = ["الأحد (Sun)", "الإثنين (Mon)", "الثلاثاء (Tue)", "الأربعاء (Wed)", "الخميس (Thu)", "الجمعة (Fri)", "السبت (Sat)"]

    print("\n=== SCHEDULE FOR WEEK 2026-10-11 TO 2026-10-17 ===")
    current_d = None
    for r in rows:
        dt, dow, code, name, st, sh = r
        if dt != current_d:
            current_d = dt
            print(f"\n[{dt} - {day_names[dow]}]:")
        status_icon = "🏖️ OFF " if st == "off" else "💼 WORK"
        print(f"  {code:8s} {name:16s} : {status_icon} ({sh})")

    # Daily coverage counts
    print("\n=== DAILY WORKING QUEUE COVERAGE ===")
    for day_idx in range(7):
        cur_date = week_start + timedelta(days=day_idx)
        cur_date_str = cur_date.isoformat()
        c.execute("""
        SELECT COUNT(*) FROM schedules 
        WHERE date = ? AND shift_type = 'work';
        """, (cur_date_str,))
        work_cnt = c.fetchone()[0]
        c.execute("""
        SELECT COUNT(*) FROM schedules 
        WHERE date = ? AND shift_type = 'off';
        """, (cur_date_str,))
        off_cnt = c.fetchone()[0]
        c.execute("""
        SELECT a.name FROM schedules s
        JOIN agents a ON s.agent_id = a.id
        WHERE s.date = ? AND s.shift_type = 'off' AND s.day_of_week != 5;
        """, (cur_date_str,))
        off_names = [x[0] for x in c.fetchall()]
        off_desc = f"Off: {', '.join(off_names)}" if off_names else "Full Team in Office"
        if day_idx == 5:
            off_desc = "All Agents Off (Fixed Friday)"
        print(f"  {cur_date_str} ({day_names[day_idx]:15s}): Working: {work_cnt} | Off: {off_cnt} -> {off_desc}")

    conn.close()
    print("\nCustom schedule applied and verified successfully in liveops.db!")

if __name__ == "__main__":
    apply_schedule()
