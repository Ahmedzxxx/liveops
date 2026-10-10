from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import sqlite3
from database import get_connection
from egypt_holidays import get_holiday_info

# Day of week mapping:
# 0 = Sunday (الأحد)
# 1 = Monday (الاثنين)
# 2 = Tuesday (الثلاثاء)
# 3 = Wednesday (الأربعاء)
# 4 = Thursday (الخميس)
# 5 = Friday (الجمعة) -> Fixed OFF for all
# 6 = Saturday (السبت)

DAY_NAMES_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
DAY_NAMES_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

# The 6-Week rotation of second off-days:
# Guarantees:
# 1. No agent has Thu (Thu+Fri) or Sat (Fri+Sat) two weeks in a row.
# 2. An agent who ends Week N with Saturday off NEVER starts Week N+1 with Sunday off!
# 3. Exactly 1 agent off per working day -> exactly 5 agents working on queue every day.
CYCLE_OFF_DAYS = [
    1,  # Week 0: Monday (الاثنين)
    3,  # Week 1: Wednesday (الأربعاء)
    4,  # Week 2: Thursday (الخميس - Long weekend 1)
    0,  # Week 3: Sunday (الأحد - Follows work Saturday)
    2,  # Week 4: Tuesday (الثلاثاء)
    6   # Week 5: Saturday (السبت - Long weekend 2)
]

def get_sunday_of_week(dt: date) -> date:
    """Return the Sunday of the week for any given date (Sunday-Saturday week)."""
    # In Python: Monday is 0, Sunday is 6.
    # If dt is Sunday (weekday=6), delta is 0.
    # Otherwise, Sunday was (dt.weekday() + 1) days ago.
    if dt.weekday() == 6:
        return dt
    return dt - timedelta(days=dt.weekday() + 1)

def get_week_index_from_anchor(week_sunday: date, anchor_sunday: date) -> int:
    """Calculate the 6-week cycle index (0 to 5) given week Sunday and anchor Sunday."""
    diff_days = (week_sunday - anchor_sunday).days
    weeks_diff = diff_days // 7
    return weeks_diff % 6

def generate_week_schedule(week_sunday_str: str, force_regenerate: bool = False) -> List[Dict[str, Any]]:
    """
    Generate or retrieve the weekly schedule for all active agents.
    week_sunday_str: 'YYYY-MM-DD' representing Sunday.
    """
    week_sunday = datetime.strptime(week_sunday_str, "%Y-%m-%d").date()
    # Ensure it's Sunday
    week_sunday = get_sunday_of_week(week_sunday)
    clean_week_sunday_str = week_sunday.isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    # Get settings
    cursor.execute("SELECT value FROM settings WHERE key = 'rotation_anchor_date';")
    row = cursor.fetchone()
    anchor_str = row["value"] if row else "2026-10-11"
    anchor_date = datetime.strptime(anchor_str, "%Y-%m-%d").date()
    anchor_sunday = get_sunday_of_week(anchor_date)

    # Get active agents
    cursor.execute("SELECT id, name, code, role FROM agents WHERE is_active = 1 AND role = 'agent' ORDER BY id ASC;")
    agents = cursor.fetchall()
    agent_count = len(agents)

    if agent_count == 0:
        conn.close()
        return []

    # Check if schedule already exists for this week
    cursor.execute("SELECT COUNT(*) as cnt FROM schedules WHERE week_start_date = ?;", (clean_week_sunday_str,))
    existing_count = cursor.fetchone()["cnt"]

    if existing_count > 0 and not force_regenerate:
        # Schedule already generated, fetch and return
        schedules = fetch_week_schedule(clean_week_sunday_str)
        conn.close()
        return schedules

    # Calculate 6-week cycle index for this week
    cycle_week_idx = get_week_index_from_anchor(week_sunday, anchor_sunday)

    # If force_regenerate, delete existing non-swapped entries for this week
    if force_regenerate and existing_count > 0:
        cursor.execute("DELETE FROM schedules WHERE week_start_date = ?;", (clean_week_sunday_str,))

    # Build schedules for the 7 days (Sunday=0 to Saturday=6)
    for agent_idx, agent in enumerate(agents):
        agent_id = agent["id"]

        # Determine agent's rotating second off-day for this week
        if agent_count == 6:
            # Mathematical 6-week permutation with distinct offsets
            second_off_day = CYCLE_OFF_DAYS[(cycle_week_idx + agent_idx) % 6]
        else:
            # Fallback for dynamic team size
            second_off_day = (cycle_week_idx + agent_idx) % 7
            if second_off_day == 5:  # Friday is already off
                second_off_day = (second_off_day + 1) % 7

        for day_idx in range(7):
            current_date = week_sunday + timedelta(days=day_idx)
            current_date_str = current_date.isoformat()

            # Friday (day_idx = 5) is ALWAYS OFF
            if day_idx == 5:
                shift_type = "off"
                shift_hours = "OFF (الجمعة إجازة)"
            elif day_idx == second_off_day:
                shift_type = "off"
                shift_hours = "OFF (إجازة أسبوعية)"
            else:
                shift_type = "work"
                shift_hours = "10:00 - 19:00"

            # Check if date is an Egyptian Public Holiday
            holiday_info = get_holiday_info(current_date_str)
            is_holiday = 1 if holiday_info else 0
            holiday_name = holiday_info["name"] if holiday_info else None
            pay_multiplier = holiday_info["multiplier"] if holiday_info else 1

            cursor.execute("""
            INSERT OR REPLACE INTO schedules 
            (week_start_date, agent_id, day_of_week, date, shift_type, shift_hours, is_holiday, holiday_name, pay_multiplier)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (clean_week_sunday_str, agent_id, day_idx, current_date_str, shift_type, shift_hours, is_holiday, holiday_name, pay_multiplier))

    conn.commit()
    conn.close()

    return fetch_week_schedule(clean_week_sunday_str)

def fetch_week_schedule(week_sunday_str: str) -> List[Dict[str, Any]]:
    """Fetch complete week schedule with agent details and daily queue metrics."""
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        s.id, s.week_start_date, s.agent_id, s.day_of_week, s.date,
        s.shift_type, s.shift_hours, s.is_holiday, s.holiday_name, s.pay_multiplier,
        a.name as agent_name, a.code as agent_code
    FROM schedules s
    JOIN agents a ON s.agent_id = a.id
    WHERE s.week_start_date = ?
    ORDER BY a.id ASC, s.day_of_week ASC;
    """
    cursor.execute(query, (week_sunday_str,))
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "week_start_date": r["week_start_date"],
            "agent_id": r["agent_id"],
            "agent_name": r["agent_name"],
            "agent_code": r["agent_code"],
            "day_of_week": r["day_of_week"],
            "day_name_ar": DAY_NAMES_AR[r["day_of_week"]],
            "day_name_en": DAY_NAMES_EN[r["day_of_week"]],
            "date": r["date"],
            "shift_type": r["shift_type"],
            "shift_hours": r["shift_hours"],
            "is_holiday": bool(r["is_holiday"]),
            "holiday_name": r["holiday_name"],
            "pay_multiplier": r["pay_multiplier"]
        })
    return result

def get_daily_queue_coverage(date_str: str) -> Dict[str, Any]:
    """Calculate queue coverage for a specific day."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        COUNT(CASE WHEN shift_type = 'work' THEN 1 END) as working_count,
        COUNT(CASE WHEN shift_type = 'off' THEN 1 END) as off_count,
        COUNT(CASE WHEN shift_type = 'leave' THEN 1 END) as leave_count,
        COUNT(*) as total_agents
    FROM schedules
    WHERE date = ?;
    """, (date_str,))
    row = cursor.fetchone()
    conn.close()

    if row and row["total_agents"] > 0:
        return {
            "date": date_str,
            "working_count": row["working_count"],
            "off_count": row["off_count"],
            "leave_count": row["leave_count"],
            "total_agents": row["total_agents"],
            "is_target_met": (row["working_count"] >= 5)
        }
    return {"date": date_str, "working_count": 0, "off_count": 0, "leave_count": 0, "total_agents": 0, "is_target_met": False}

if __name__ == "__main__":
    # Test generation for current week
    today = date.today()
    sun = get_sunday_of_week(today)
    print("Generating schedule for week starting:", sun.isoformat())
    sched = generate_week_schedule(sun.isoformat(), force_regenerate=True)
    print(f"Generated {len(sched)} schedule slots.")
    for d in range(7):
        cur_d = sun + timedelta(days=d)
        cov = get_daily_queue_coverage(cur_d.isoformat())
        print(f"{DAY_NAMES_EN[d]} ({cur_d.isoformat()}): Working = {cov['working_count']}, Off = {cov['off_count']}")
