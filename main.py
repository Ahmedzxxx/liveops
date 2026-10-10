import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

from database import get_connection, init_db
from scheduler_engine import generate_week_schedule, fetch_week_schedule, get_sunday_of_week, get_daily_queue_coverage
from egypt_holidays import get_all_holidays_for_year, get_holiday_info
from excel_export import generate_monthly_excel_report
from telegram_service import (
    start_telegram_listener, 
    notify_new_excuse, 
    notify_new_swap, 
    notify_new_leave,
    send_test_notification, 
    execute_swap_in_db, 
    format_date_with_day
)

app = FastAPI(title="LiveOps Workforce Management & Scheduling System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database and Telegram listener on startup
@app.on_event("startup")
def on_startup():
    init_db()
    # Auto-generate current week and next week schedules
    today = date.today()
    cur_sun = get_sunday_of_week(today)
    generate_week_schedule(cur_sun.isoformat())
    nxt_sun = cur_sun + timedelta(weeks=1)
    generate_week_schedule(nxt_sun.isoformat())
    start_telegram_listener()

# ==========================================
# Pydantic Schemas
# ==========================================
class LoginRequest(BaseModel):
    code: str
    password: str

class ChangePasswordRequest(BaseModel):
    agent_id: int
    old_password: str
    new_password: str

class AgentCreateRequest(BaseModel):
    name: str
    code: str
    password: str
    role: str = "agent"

class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[int] = None

class PunchRequest(BaseModel):
    agent_id: int
    action: str  # 'start_shift' or 'end_shift'

class BreakToggleRequest(BaseModel):
    agent_id: int
    action: str  # 'start_break' or 'end_break'

class PauseToggleRequest(BaseModel):
    agent_id: int
    action: str  # 'start_pause' or 'end_pause'
    pause_type: str  # 'meeting' or 'emergency'

class QueueModeRequest(BaseModel):
    mode: str  # 'normal' or 'meeting'

class SwapCreateRequest(BaseModel):
    requester_id: int
    target_agent_id: int
    requester_date: str
    target_date: str

class ActionRequest(BaseModel):
    status: str  # 'approved' or 'rejected'
    comment: Optional[str] = None

class ExcuseCreateRequest(BaseModel):
    agent_id: int
    date: str
    from_time: str
    to_time: str
    reason: str

class LeaveCreateRequest(BaseModel):
    agent_id: int
    date: str
    leave_type: str
    reason: str

class ScheduleOverrideRequest(BaseModel):
    agent_id: int
    date: str
    shift_type: str  # 'work', 'off', 'leave'
    shift_hours: Optional[str] = "10:00 - 19:00"

class DirectSwapRequest(BaseModel):
    agent1_id: int
    date1: str
    agent2_id: int
    date2: str

class SettingsUpdateRequest(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None
    break_limit_minutes: Optional[str] = None

# ==========================================
# Authentication & Agents
# ==========================================
@app.post("/api/login")
def login(req: LoginRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, code, role, is_active, password FROM agents 
    WHERE code = ? AND is_active = 1;
    """, (req.code.strip(),))
    agent = cursor.fetchone()
    conn.close()

    if not agent or agent["password"] != req.password.strip():
        raise HTTPException(status_code=401, detail="كود الموظف أو كلمة المرور غير صحيحة")

    return {
        "success": True,
        "agent": {
            "id": agent["id"],
            "name": agent["name"],
            "code": agent["code"],
            "role": agent["role"]
        }
    }

@app.post("/api/change-password")
def change_password(req: ChangePasswordRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM agents WHERE id = ?;", (req.agent_id,))
    row = cursor.fetchone()
    if not row or row["password"] != req.old_password.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")

    cursor.execute("UPDATE agents SET password = ? WHERE id = ?;", (req.new_password.strip(), req.agent_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "تم تغيير كلمة المرور بنجاح"}

@app.get("/api/agents")
def list_agents():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, code, password, role, is_active, created_at 
    FROM agents ORDER BY id ASC;
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/agents")
def create_agent(req: AgentCreateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        now_str = datetime.now().isoformat()
        cursor.execute("""
        INSERT INTO agents (name, code, password, role, is_active, created_at)
        VALUES (?, ?, ?, ?, 1, ?);
        """, (req.name.strip(), req.code.strip(), req.password.strip(), req.role, now_str))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return {"success": True, "id": new_id}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="كود الموظف مستخدم بالفعل")

@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, req: AgentUpdateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    fields = []
    params = []
    if req.name is not None:
        fields.append("name = ?")
        params.append(req.name.strip())
    if req.code is not None:
        fields.append("code = ?")
        params.append(req.code.strip())
    if req.password is not None:
        fields.append("password = ?")
        params.append(req.password.strip())
    if req.is_active is not None:
        fields.append("is_active = ?")
        params.append(req.is_active)

    if not fields:
        conn.close()
        return {"success": True}

    params.append(agent_id)
    cursor.execute(f"UPDATE agents SET {', '.join(fields)} WHERE id = ?;", tuple(params))
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE agents SET is_active = 0 WHERE id = ?;", (agent_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# ==========================================
# Schedules & Master Roster
# ==========================================
@app.get("/api/schedule/week")
def get_week_schedule_api(sunday: Optional[str] = None):
    if not sunday:
        target_sun = get_sunday_of_week(date.today())
        sunday = target_sun.isoformat()
    schedules = generate_week_schedule(sunday)
    return schedules

@app.post("/api/schedule/generate")
def force_generate_schedule(sunday: str):
    schedules = generate_week_schedule(sunday, force_regenerate=True)
    return {"success": True, "count": len(schedules)}

@app.get("/api/schedule/coverage")
def get_coverage(target_date: str):
    return get_daily_queue_coverage(target_date)

@app.get("/api/schedule/off-days/{agent_id}")
def get_agent_off_days(agent_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    # Find rotating off-days starting from today or future
    today_str = date.today().isoformat()
    cursor.execute("""
    SELECT date, day_of_week, shift_type, shift_hours
    FROM schedules
    WHERE agent_id = ? AND date >= ? AND shift_type = 'off' AND day_of_week != 5
    ORDER BY date ASC
    LIMIT 6;
    """, (agent_id, today_str))
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["formatted"] = format_date_with_day(d["date"])
        result.append(d)
    return result

@app.post("/api/schedule/override")
def override_schedule(req: ScheduleOverrideRequest):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Calculate week sunday and day of week
    dt = datetime.strptime(req.date, "%Y-%m-%d").date()
    week_sun = get_sunday_of_week(dt).isoformat()
    # 0=Sun, 1=Mon... in Python Monday is 0, Sunday is 6
    day_idx = 0 if dt.weekday() == 6 else dt.weekday() + 1
    
    # Check holiday info
    h_info = get_holiday_info(req.date)
    is_holiday = 1 if h_info else 0
    holiday_name = h_info["name"] if h_info else None
    multiplier = h_info["multiplier"] if h_info else 1
    
    hours = req.shift_hours or ("OFF (إجازة)" if req.shift_type == "off" else "10:00 - 19:00")
    if req.shift_type == "off":
        hours = "OFF (إجازة بتعديل المدير)"
    elif req.shift_type == "work":
        hours = "10:00 - 19:00"

    cursor.execute("""
    INSERT INTO schedules (week_start_date, agent_id, day_of_week, date, shift_type, shift_hours, is_holiday, holiday_name, pay_multiplier)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(agent_id, date) DO UPDATE SET
        shift_type = excluded.shift_type,
        shift_hours = excluded.shift_hours;
    """, (week_sun, req.agent_id, day_idx, req.date, req.shift_type, hours, is_holiday, holiday_name, multiplier))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Schedule updated successfully"}

@app.post("/api/schedule/direct-swap")
def direct_swap(req: DirectSwapRequest):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT shift_type, shift_hours FROM schedules WHERE agent_id = ? AND date = ?;", (req.agent1_id, req.date1))
    s1 = cursor.fetchone()
    cursor.execute("SELECT shift_type, shift_hours FROM schedules WHERE agent_id = ? AND date = ?;", (req.agent2_id, req.date2))
    s2 = cursor.fetchone()

    if s1 and s2:
        cursor.execute("UPDATE schedules SET shift_type = ?, shift_hours = ? WHERE agent_id = ? AND date = ?;", 
                       (s2["shift_type"], s2["shift_hours"], req.agent1_id, req.date1))
        cursor.execute("UPDATE schedules SET shift_type = ?, shift_hours = ? WHERE agent_id = ? AND date = ?;", 
                       (s1["shift_type"], s1["shift_hours"], req.agent2_id, req.date2))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Direct swap completed successfully"}
    conn.close()
    raise HTTPException(status_code=404, detail="Schedule slots not found for specified agents and dates")

# ==========================================
# Live Queue & Attendance Tracker
# ==========================================
@app.get("/api/live/status")
def get_live_status():
    now = datetime.now()
    today_str = now.date().isoformat()
    now_time_str = now.strftime("%H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()

    # Get system settings
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('queue_mode', 'shift_start', 'shift_end');")
    settings_dict = {r["key"]: r["value"] for r in cursor.fetchall()}
    queue_mode = settings_dict.get("queue_mode", "normal")

    # Get all active agents with today's schedule, attendance, breaks, and pauses
    query = """
    SELECT 
        a.id as agent_id, a.name, a.code,
        COALESCE(s.shift_type, 'work') as shift_type,
        COALESCE(s.shift_hours, '10:00 - 19:00') as shift_hours,
        COALESCE(s.is_holiday, 0) as is_holiday,
        s.holiday_name, s.pay_multiplier,
        t.clock_in, t.clock_out, t.total_work_minutes, t.late_minutes, t.is_compensated, t.overtime_minutes,
        COALESCE(t.status, 'off') as log_status,
        (SELECT SUM(duration_minutes) FROM break_logs WHERE agent_id = a.id AND date = ?) as total_break_min,
        (SELECT id FROM break_logs WHERE agent_id = a.id AND date = ? AND end_time IS NULL) as active_break_id,
        (SELECT start_time FROM break_logs WHERE agent_id = a.id AND date = ? AND end_time IS NULL) as active_break_start,
        (SELECT SUM(duration_minutes) FROM pause_logs WHERE agent_id = a.id AND date = ? AND pause_type = 'meeting') as total_meeting_min,
        (SELECT id FROM pause_logs WHERE agent_id = a.id AND date = ? AND pause_type = 'meeting' AND end_time IS NULL) as active_meeting_id,
        (SELECT start_time FROM pause_logs WHERE agent_id = a.id AND date = ? AND pause_type = 'meeting' AND end_time IS NULL) as active_meeting_start,
        (SELECT SUM(duration_minutes) FROM pause_logs WHERE agent_id = a.id AND date = ? AND pause_type = 'emergency') as total_emergency_min,
        (SELECT id FROM pause_logs WHERE agent_id = a.id AND date = ? AND pause_type = 'emergency' AND end_time IS NULL) as active_emergency_id,
        (SELECT start_time FROM pause_logs WHERE agent_id = a.id AND date = ? AND pause_type = 'emergency' AND end_time IS NULL) as active_emergency_start
    FROM agents a
    LEFT JOIN schedules s ON a.id = s.agent_id AND s.date = ?
    LEFT JOIN time_logs t ON a.id = t.agent_id AND t.date = ?
    WHERE a.is_active = 1 AND a.role = 'agent'
    ORDER BY a.id ASC;
    """
    cursor.execute(query, (today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str))
    rows = cursor.fetchall()
    conn.close()

    agents_status = []
    active_on_queue = 0
    active_on_break = 0

    for r in rows:
        st = r["shift_type"]
        clock_in = r["clock_in"]
        clock_out = r["clock_out"]
        active_break_id = r["active_break_id"]
        total_break = r["total_break_min"] or 0
        active_meeting_id = r["active_meeting_id"]
        total_meeting = r["total_meeting_min"] or 0
        active_emergency_id = r["active_emergency_id"]
        total_emergency = r["total_emergency_min"] or 0

        # Calculate current real-time state
        current_state = "off"
        if st == "off" and not clock_in:
            current_state = "off"
        elif active_break_id:
            current_state = "on_break"
            active_on_break += 1
        elif active_meeting_id:
            current_state = "in_meeting"
        elif r["log_status"] == "on_hold" and clock_in and not clock_out:
            current_state = "on_hold"
        elif active_emergency_id:
            current_state = "in_emergency"
        elif queue_mode == "meeting" and clock_in and not clock_out:
            current_state = "meeting"
            active_on_queue += 1
        elif clock_in and not clock_out:
            current_state = "on_shift"
            active_on_queue += 1
        elif clock_out:
            current_state = "completed"
        elif st == "work":
            current_state = "scheduled"

        # Calculate live net work minutes if clocked in and not clocked out
        live_net_work_minutes = r["total_work_minutes"] or 0
        if clock_in and not clock_out:
            try:
                c_in_dt = datetime.strptime(f"{today_str} {clock_in}", "%Y-%m-%d %H:%M:%S")
                gross_elapsed_sec = max(0, int((now - c_in_dt).total_seconds()))

                # Add active in-progress break/meeting/emergency seconds
                cur_break_sec = (total_break * 60)
                if active_break_id and r["active_break_start"]:
                    b_dt = datetime.strptime(f"{today_str} {r['active_break_start']}", "%Y-%m-%d %H:%M:%S")
                    cur_break_sec += max(0, int((now - b_dt).total_seconds()))

                cur_meeting_sec = (total_meeting * 60)
                if active_meeting_id and r["active_meeting_start"]:
                    m_dt = datetime.strptime(f"{today_str} {r['active_meeting_start']}", "%Y-%m-%d %H:%M:%S")
                    cur_meeting_sec += max(0, int((now - m_dt).total_seconds()))

                cur_emergency_sec = (total_emergency * 60)
                if active_emergency_id and r["active_emergency_start"]:
                    e_dt = datetime.strptime(f"{today_str} {r['active_emergency_start']}", "%Y-%m-%d %H:%M:%S")
                    cur_emergency_sec += max(0, int((now - e_dt).total_seconds()))

                net_sec = max(0, gross_elapsed_sec - cur_break_sec - cur_meeting_sec - cur_emergency_sec)
                live_net_work_minutes = net_sec // 60
            except Exception:
                live_net_work_minutes = r["total_work_minutes"] or 0

        agents_status.append({
            "agent_id": r["agent_id"],
            "name": r["name"],
            "code": r["code"],
            "shift_type": st,
            "shift_hours": r["shift_hours"],
            "is_holiday": bool(r["is_holiday"]),
            "holiday_name": r["holiday_name"],
            "pay_multiplier": r["pay_multiplier"],
            "clock_in": clock_in,
            "clock_out": clock_out,
            "current_state": current_state,
            "total_break_minutes": total_break,
            "is_on_break": bool(active_break_id),
            "active_break_start": r["active_break_start"],
            "total_meeting_minutes": total_meeting,
            "is_in_meeting": bool(active_meeting_id),
            "active_meeting_start": r["active_meeting_start"],
            "total_emergency_minutes": total_emergency,
            "is_in_emergency": bool(active_emergency_id),
            "active_emergency_start": r["active_emergency_start"],
            "late_minutes": r["late_minutes"] or 0,
            "is_compensated": bool(r["is_compensated"]),
            "total_work_minutes": live_net_work_minutes,
            "server_now": now_time_str
        })

    return {
        "date": today_str,
        "queue_mode": queue_mode,
        "active_on_queue": active_on_queue,
        "active_on_break": active_on_break,
        "target_queue_size": 5,
        "agents": agents_status
    }

@app.post("/api/attendance/punch")
def punch_attendance(req: PunchRequest):
    now = datetime.now()
    today_str = now.date().isoformat()
    now_time_str = now.strftime("%H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    if req.action == "start_shift":
        # Calculate late minutes based on 10:00 AM shift start
        shift_start_time = datetime.strptime(f"{today_str} 10:00:00", "%Y-%m-%d %H:%M:%S")
        late_minutes = 0
        if now > shift_start_time:
            late_minutes = int((now - shift_start_time).total_seconds() // 60)

        # Check if there is an approved excuse covering this morning
        cursor.execute("""
        SELECT COUNT(*) as exc_cnt FROM excuse_requests 
        WHERE agent_id = ? AND date = ? AND status = 'approved' AND from_time <= '10:15';
        """, (req.agent_id, today_str))
        if cursor.fetchone()["exc_cnt"] > 0:
            late_minutes = 0  # Excused!

        cursor.execute("""
        INSERT INTO time_logs (agent_id, date, clock_in, late_minutes, status)
        VALUES (?, ?, ?, ?, 'on_shift')
        ON CONFLICT(agent_id, date) DO UPDATE SET 
            clock_in = excluded.clock_in,
            clock_out = NULL,
            late_minutes = excluded.late_minutes,
            status = 'on_shift';
        """, (req.agent_id, today_str, now_time_str, late_minutes))

    elif req.action == "end_shift":
        # Close any active break
        cursor.execute("""
        SELECT id, start_time FROM break_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL;
        """, (req.agent_id, today_str))
        b_open = cursor.fetchone()
        if b_open:
            b_start = datetime.strptime(f"{today_str} {b_open['start_time']}", "%Y-%m-%d %H:%M:%S")
            b_dur = max(0, int((now - b_start).total_seconds() // 60))
            cursor.execute("UPDATE break_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;", (now_time_str, b_dur, b_open["id"]))

        # Close any active pause (meeting or emergency)
        cursor.execute("""
        SELECT id, start_time FROM pause_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL;
        """, (req.agent_id, today_str))
        p_open = cursor.fetchone()
        if p_open:
            p_start = datetime.strptime(f"{today_str} {p_open['start_time']}", "%Y-%m-%d %H:%M:%S")
            p_dur = max(0, int((now - p_start).total_seconds() // 60))
            cursor.execute("UPDATE pause_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;", (now_time_str, p_dur, p_open["id"]))

        # Get clock_in to compute total minutes worked
        cursor.execute("SELECT clock_in, late_minutes FROM time_logs WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))
        row = cursor.fetchone()
        if not row or not row["clock_in"]:
            conn.close()
            raise HTTPException(status_code=400, detail="لم يتم تسجيل الحضور أولاً!")

        cin = datetime.strptime(f"{today_str} {row['clock_in']}", "%Y-%m-%d %H:%M:%S")
        gross_work_minutes = int((now - cin).total_seconds() // 60)

        # Sum break minutes
        cursor.execute("SELECT COALESCE(SUM(duration_minutes), 0) as s FROM break_logs WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))
        total_break_min = cursor.fetchone()["s"]

        # Sum meeting minutes
        cursor.execute("SELECT COALESCE(SUM(duration_minutes), 0) as s FROM pause_logs WHERE agent_id = ? AND date = ? AND pause_type = 'meeting';", (req.agent_id, today_str))
        total_meeting_min = cursor.fetchone()["s"]

        # Sum emergency minutes
        cursor.execute("SELECT COALESCE(SUM(duration_minutes), 0) as s FROM pause_logs WHERE agent_id = ? AND date = ? AND pause_type = 'emergency';", (req.agent_id, today_str))
        total_emergency_min = cursor.fetchone()["s"]

        # Net actual work minutes on queue
        net_work_minutes = max(0, gross_work_minutes - total_break_min - total_meeting_min - total_emergency_min)

        late_minutes = row["late_minutes"] or 0
        is_compensated = 0
        overtime_minutes = 0

        # Smart compensation check: 9 hours = 540 gross shift minutes
        if late_minutes > 0:
            if gross_work_minutes >= 540:
                is_compensated = 1
                overtime_minutes = max(0, gross_work_minutes - 540)
        else:
            if gross_work_minutes > 540:
                overtime_minutes = gross_work_minutes - 540

        cursor.execute("""
        UPDATE time_logs SET 
            clock_out = ?, 
            total_work_minutes = ?,
            is_compensated = ?,
            overtime_minutes = ?,
            status = 'completed'
        WHERE agent_id = ? AND date = ?;
        """, (now_time_str, net_work_minutes, is_compensated, overtime_minutes, req.agent_id, today_str))

    elif req.action == "start_hold":
        # Create an emergency pause log
        cursor.execute("""
        INSERT INTO pause_logs (agent_id, date, pause_type, start_time)
        VALUES (?, ?, 'emergency', ?);
        """, (req.agent_id, today_str, now_time_str))
        cursor.execute("UPDATE time_logs SET status = 'on_hold' WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))

    elif req.action == "end_hold":
        cursor.execute("""
        SELECT id, start_time FROM pause_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL 
        ORDER BY id DESC LIMIT 1;
        """, (req.agent_id, today_str))
        p_row = cursor.fetchone()
        if p_row:
            p_start = datetime.strptime(f"{today_str} {p_row['start_time']}", "%Y-%m-%d %H:%M:%S")
            p_dur = max(0, int((now - p_start).total_seconds() // 60))
            cursor.execute("UPDATE pause_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;", (now_time_str, p_dur, p_row["id"]))
        cursor.execute("UPDATE time_logs SET status = 'on_shift' WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))

    conn.commit()
    conn.close()
    return {"success": True, "time": now_time_str}

@app.post("/api/break/toggle")
def toggle_break(req: BreakToggleRequest):
    now = datetime.now()
    today_str = now.date().isoformat()
    now_time_str = now.strftime("%H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    if req.action == "start_break":
        # Close any open pause first
        cursor.execute("""
        SELECT id, start_time FROM pause_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL;
        """, (req.agent_id, today_str))
        p_row = cursor.fetchone()
        if p_row:
            p_start = datetime.strptime(f"{today_str} {p_row['start_time']}", "%Y-%m-%d %H:%M:%S")
            p_dur = max(0, int((now - p_start).total_seconds() // 60))
            cursor.execute("UPDATE pause_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;", (now_time_str, p_dur, p_row["id"]))

        # Insert new active break
        cursor.execute("""
        INSERT INTO break_logs (agent_id, date, start_time)
        VALUES (?, ?, ?);
        """, (req.agent_id, today_str, now_time_str))
        cursor.execute("UPDATE time_logs SET status = 'on_break' WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))

    elif req.action == "end_break":
        # Find active break log
        cursor.execute("""
        SELECT id, start_time FROM break_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL 
        ORDER BY id DESC LIMIT 1;
        """, (req.agent_id, today_str))
        b_row = cursor.fetchone()
        if b_row:
            b_start = datetime.strptime(f"{today_str} {b_row['start_time']}", "%Y-%m-%d %H:%M:%S")
            duration = max(0, int((now - b_start).total_seconds() // 60))
            cursor.execute("""
            UPDATE break_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;
            """, (now_time_str, duration, b_row["id"]))
            cursor.execute("UPDATE time_logs SET status = 'on_shift' WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))

    conn.commit()
    conn.close()
    return {"success": True, "time": now_time_str}

@app.post("/api/pause/toggle")
def toggle_pause(req: PauseToggleRequest):
    now = datetime.now()
    today_str = now.date().isoformat()
    now_time_str = now.strftime("%H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    if req.action == "start_pause":
        # Close any open break
        cursor.execute("""
        SELECT id, start_time FROM break_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL;
        """, (req.agent_id, today_str))
        b_row = cursor.fetchone()
        if b_row:
            b_start = datetime.strptime(f"{today_str} {b_row['start_time']}", "%Y-%m-%d %H:%M:%S")
            b_dur = max(0, int((now - b_start).total_seconds() // 60))
            cursor.execute("UPDATE break_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;", (now_time_str, b_dur, b_row["id"]))

        # Close any existing open pause
        cursor.execute("""
        SELECT id, start_time FROM pause_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL;
        """, (req.agent_id, today_str))
        p_row = cursor.fetchone()
        if p_row:
            p_start = datetime.strptime(f"{today_str} {p_row['start_time']}", "%Y-%m-%d %H:%M:%S")
            p_dur = max(0, int((now - p_start).total_seconds() // 60))
            cursor.execute("UPDATE pause_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;", (now_time_str, p_dur, p_row["id"]))

        # Insert new active pause
        cursor.execute("""
        INSERT INTO pause_logs (agent_id, date, pause_type, start_time)
        VALUES (?, ?, ?, ?);
        """, (req.agent_id, today_str, req.pause_type, now_time_str))

        status_val = "in_meeting" if req.pause_type == "meeting" else "in_emergency"
        cursor.execute("UPDATE time_logs SET status = ? WHERE agent_id = ? AND date = ?;", (status_val, req.agent_id, today_str))

    elif req.action == "end_pause":
        cursor.execute("""
        SELECT id, start_time FROM pause_logs 
        WHERE agent_id = ? AND date = ? AND end_time IS NULL 
        ORDER BY id DESC LIMIT 1;
        """, (req.agent_id, today_str))
        p_row = cursor.fetchone()
        if p_row:
            p_start = datetime.strptime(f"{today_str} {p_row['start_time']}", "%Y-%m-%d %H:%M:%S")
            duration = max(0, int((now - p_start).total_seconds() // 60))
            cursor.execute("""
            UPDATE pause_logs SET end_time = ?, duration_minutes = ? WHERE id = ?;
            """, (now_time_str, duration, p_row["id"]))
            cursor.execute("UPDATE time_logs SET status = 'on_shift' WHERE agent_id = ? AND date = ?;", (req.agent_id, today_str))

    conn.commit()
    conn.close()
    return {"success": True, "time": now_time_str}

@app.post("/api/queue/mode")
def set_queue_mode(req: QueueModeRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'queue_mode';", (req.mode,))
    conn.commit()
    conn.close()
    return {"success": True, "mode": req.mode}

# ==========================================
# Requests (Swaps, Excuses, Leaves)
# ==========================================
@app.post("/api/swaps/request")
def create_swap(req: SwapCreateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO swap_requests (requester_id, target_agent_id, requester_date, target_date, status, created_at)
    VALUES (?, ?, ?, ?, 'pending_peer', ?);
    """, (req.requester_id, req.target_agent_id, req.requester_date, req.target_date, now_str))
    swap_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"success": True, "id": swap_id}

@app.get("/api/swaps")
def list_swaps():
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        sw.id, sw.requester_id, a1.name as requester_name, a1.code as requester_code,
        sw.target_agent_id, a2.name as target_name, a2.code as target_code,
        sw.requester_date, sw.target_date, sw.status, sw.peer_comment, sw.manager_comment,
        sw.created_at
    FROM swap_requests sw
    JOIN agents a1 ON sw.requester_id = a1.id
    JOIN agents a2 ON sw.target_agent_id = a2.id
    ORDER BY sw.id DESC;
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["requester_date_formatted"] = format_date_with_day(d["requester_date"])
        d["target_date_formatted"] = format_date_with_day(d["target_date"])
        result.append(d)
    return result

@app.post("/api/swaps/{swap_id}/peer-action")
def peer_swap_action(swap_id: int, req: ActionRequest):
    conn = get_connection()
    cursor = conn.cursor()
    new_status = "pending_manager" if req.status == "approved" else "rejected"
    cursor.execute("""
    UPDATE swap_requests SET status = ?, peer_comment = ?, updated_at = datetime('now') WHERE id = ?;
    """, (new_status, req.comment, swap_id))
    conn.commit()

    if new_status == "pending_manager":
        # Notify manager via Telegram
        cursor.execute("""
        SELECT a1.name as req_name, a2.name as tgt_name, sw.requester_date, sw.target_date
        FROM swap_requests sw
        JOIN agents a1 ON sw.requester_id = a1.id
        JOIN agents a2 ON sw.target_agent_id = a2.id
        WHERE sw.id = ?;
        """, (swap_id,))
        sw_info = cursor.fetchone()
        if sw_info:
            notify_new_swap(swap_id, sw_info["req_name"], sw_info["tgt_name"], sw_info["requester_date"], sw_info["target_date"])

    conn.close()
    return {"success": True}

@app.post("/api/swaps/{swap_id}/manager-action")
def manager_swap_action(swap_id: int, req: ActionRequest):
    conn = get_connection()
    cursor = conn.cursor()
    new_status = "approved" if req.status == "approved" else "rejected"

    if new_status == "approved":
        # Execute schedule swap
        cursor.execute("SELECT requester_id, target_agent_id, requester_date, target_date FROM swap_requests WHERE id = ?;", (swap_id,))
        swap = cursor.fetchone()
        if swap:
            execute_swap_in_db(cursor, swap["requester_id"], swap["target_agent_id"], swap["requester_date"], swap["target_date"])

    cursor.execute("""
    UPDATE swap_requests SET status = ?, manager_comment = ?, updated_at = datetime('now') WHERE id = ?;
    """, (new_status, req.comment, swap_id))
    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/excuses/request")
def create_excuse(req: ExcuseCreateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO excuse_requests (agent_id, date, from_time, to_time, reason, status, created_at)
    VALUES (?, ?, ?, ?, ?, 'pending', ?);
    """, (req.agent_id, req.date, req.from_time, req.to_time, req.reason, now_str))
    excuse_id = cursor.lastrowid
    conn.commit()

    # Get agent name for Telegram alert
    cursor.execute("SELECT name FROM agents WHERE id = ?;", (req.agent_id,))
    agent = cursor.fetchone()
    agent_name = agent["name"] if agent else "Agent"
    conn.close()

    notify_new_excuse(excuse_id, agent_name, req.date, req.from_time, req.to_time, req.reason)
    return {"success": True, "id": excuse_id}

@app.get("/api/excuses")
def list_excuses():
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        e.id, e.agent_id, a.name as agent_name, a.code as agent_code,
        e.date, e.from_time, e.to_time, e.reason, e.status, e.manager_comment, e.created_at
    FROM excuse_requests e
    JOIN agents a ON e.agent_id = a.id
    ORDER BY e.id DESC;
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["date_formatted"] = format_date_with_day(d["date"])
        result.append(d)
    return result


@app.post("/api/excuses/{excuse_id}/manager-action")
def manager_excuse_action(excuse_id: int, req: ActionRequest):
    conn = get_connection()
    cursor = conn.cursor()
    new_status = "approved" if req.status == "approved" else "rejected"
    cursor.execute("""
    UPDATE excuse_requests SET status = ?, manager_comment = ?, updated_at = datetime('now') WHERE id = ?;
    """, (new_status, req.comment, excuse_id))
    
    # If approved, clear late minutes if on same date
    if new_status == "approved":
        cursor.execute("SELECT agent_id, date FROM excuse_requests WHERE id = ?;", (excuse_id,))
        exc = cursor.fetchone()
        if exc:
            cursor.execute("UPDATE time_logs SET late_minutes = 0 WHERE agent_id = ? AND date = ?;", (exc["agent_id"], exc["date"]))

    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/leaves/request")
def create_leave(req: LeaveCreateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO leave_requests (agent_id, date, leave_type, reason, status, created_at)
    VALUES (?, ?, ?, ?, 'pending', ?);
    """, (req.agent_id, req.date, req.leave_type, req.reason, now_str))
    leave_id = cursor.lastrowid
    conn.commit()

    # Get agent name for Telegram alert
    cursor.execute("SELECT name FROM agents WHERE id = ?;", (req.agent_id,))
    agent = cursor.fetchone()
    agent_name = agent["name"] if agent else "Agent"
    conn.close()

    notify_new_leave(leave_id, agent_name, req.date, req.leave_type, req.reason)
    return {"success": True, "id": leave_id}

@app.get("/api/leaves")
def list_leaves():
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        l.id, l.agent_id, a.name as agent_name, a.code as agent_code,
        l.date, l.leave_type, l.reason, l.status, l.created_at
    FROM leave_requests l
    JOIN agents a ON l.agent_id = a.id
    ORDER BY l.id DESC;
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["date_formatted"] = format_date_with_day(d["date"])
        result.append(d)
    return result


@app.post("/api/leaves/{leave_id}/manager-action")
def manager_leave_action(leave_id: int, req: ActionRequest):
    conn = get_connection()
    cursor = conn.cursor()
    new_status = "approved" if req.status == "approved" else "rejected"
    cursor.execute("""
    UPDATE leave_requests SET status = ?, updated_at = datetime('now') WHERE id = ?;
    """, (new_status, leave_id))

    if new_status == "approved":
        cursor.execute("SELECT agent_id, date, leave_type FROM leave_requests WHERE id = ?;", (leave_id,))
        l_info = cursor.fetchone()
        if l_info:
            cursor.execute("""
            UPDATE schedules SET shift_type = 'leave', shift_hours = 'إجازة معتمدة'
            WHERE agent_id = ? AND date = ?;
            """, (l_info["agent_id"], l_info["date"]))

    conn.commit()
    conn.close()
    return {"success": True}

# ==========================================
# Reports & Egypt Holidays
# ==========================================
@app.get("/api/reports/monthly-excel")
def download_monthly_excel(year: int = Query(...), month: int = Query(...)):
    report_path = generate_monthly_excel_report(year, month)
    filename = os.path.basename(report_path)
    return FileResponse(
        report_path, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        filename=filename
    )

@app.get("/api/holidays")
def list_holidays(year: int = 2026):
    return get_all_holidays_for_year(year)

# ==========================================
# System Settings
# ==========================================
@app.get("/api/settings")
def get_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings;")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

@app.post("/api/settings")
def update_settings(req: SettingsUpdateRequest):
    conn = get_connection()
    cursor = conn.cursor()
    if req.telegram_bot_token is not None:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'telegram_bot_token';", (req.telegram_bot_token.strip(),))
    if req.telegram_chat_id is not None:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'telegram_chat_id';", (req.telegram_chat_id.strip(),))
    if req.shift_start is not None:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'shift_start';", (req.shift_start.strip(),))
    if req.shift_end is not None:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'shift_end';", (req.shift_end.strip(),))
    if req.break_limit_minutes is not None:
        cursor.execute("UPDATE settings SET value = ? WHERE key = 'break_limit_minutes';", (req.break_limit_minutes.strip(),))

    conn.commit()
    conn.close()
    return {"success": True}

@app.post("/api/telegram/test")
def test_telegram_endpoint():
    res = send_test_notification()
    return res

# ==========================================
# Serve Frontend HTML
# ==========================================
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>LiveOps Management App Loading...</h1>"
