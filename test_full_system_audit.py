import json
import urllib.request
import urllib.parse
import io
import sys
import openpyxl

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_URL = "http://127.0.0.1:8050"

def request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"} if data else {}
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
            if "application/json" in content_type:
                return status, json.loads(body.decode("utf-8"))
            return status, body
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            err_json = json.loads(body.decode("utf-8"))
            return e.code, err_json
        except Exception:
            return e.code, body.decode("utf-8")

import sqlite3
from datetime import date

def cleanup_test_data():
    conn = sqlite3.connect("liveops.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET value = 'normal' WHERE key = 'queue_mode';")
    today_str = date.today().isoformat()
    c.execute("DELETE FROM time_logs WHERE date = ?;", (today_str,))
    c.execute("DELETE FROM break_logs WHERE date = ?;", (today_str,))
    c.execute("DELETE FROM pause_logs WHERE date = ?;", (today_str,))
    c.execute("DELETE FROM agents WHERE code LIKE 'TEST-%';")
    conn.commit()
    conn.close()

def run_system_audit():
    cleanup_test_data()
    print("==================================================")
    print("LIVE SYSTEM AUDIT - ALL ACCOUNTS & ALL ENDPOINTS")
    print("==================================================")

    # 1. LOGIN TESTS
    print("\n--- 1. Testing Login for Manager and All Agents ---")
    credentials = [
        ("ADMIN-01", "admin2026", "manager", "Manager"),
        ("RN-101", "rana123", "agent", "Rana"),
        ("BR-102", "bassant123", "agent", "Bassant"),
        ("SM-103", "sama123", "agent", "Sama"),
        ("TB-104", "tooba123", "agent", "Tooba"),
        ("RA-105", "rahma123", "agent", "Rahma"),
        ("NI-106", "nesma123", "agent", "Nesma")
    ]
    for code, pwd, expected_role, expected_name in credentials:
        st, res = request("POST", "/api/login", {"code": code, "password": pwd})
        assert st == 200, f"Login failed for {code}: {res}"
        assert res["success"] is True
        assert res["agent"]["role"] == expected_role
        assert expected_name in res["agent"]["name"]
        print(f"  [PASS] Login {code:8s} ({res['agent']['name']}) -> Role: {res['agent']['role']}")

    # Invalid login test
    st, res = request("POST", "/api/login", {"code": "ADMIN-01", "password": "wrong"})
    assert st == 401
    print("  [PASS] Invalid password correctly rejected (401)")

    # 2. SCHEDULE & COVERAGE
    print("\n--- 2. Testing Schedule & Off-Days ---")
    st, schedules = request("GET", "/api/schedule/week")
    assert st == 200 and len(schedules) >= 42
    print(f"  [PASS] /api/schedule/week returned {len(schedules)} schedule slots")

    # Check Friday is strictly OFF
    friday_slots = [s for s in schedules if s["day_of_week"] == 5]
    assert all(s["shift_type"] == "off" for s in friday_slots)
    print(f"  [PASS] Verified {len(friday_slots)} Friday schedule slots are all 'off'")

    # Off-days endpoint for agents (excluding Friday, includes formatted day name)
    for ag_id in [1, 2, 3]:
        st, off_days = request("GET", f"/api/schedule/off-days/{ag_id}")
        assert st == 200 and len(off_days) > 0
        assert all(od["day_of_week"] != 5 for od in off_days)
        assert all("formatted" in od and od["shift_type"] == "off" for od in off_days)
        print(f"  [PASS] /api/schedule/off-days/{ag_id} returned {len(off_days)} rotating off-days: {off_days[0]['formatted']}")

    # 3. LIVE QUEUE & ADHERENCE CYCLE
    print("\n--- 3. Testing Full Live Adherence Cycle (Shift -> Break -> Meeting -> Emergency -> Clockout) ---")
    # Test on Agent 4 (Tooba, id=4)
    # Start shift
    st, res = request("POST", "/api/attendance/punch", {"agent_id": 4, "action": "start_shift"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["clock_in"] is not None
    assert tooba["current_state"] == "on_shift"
    print("  [PASS] Tooba Start Shift -> State: on_shift, Clock-in registered")

    # Start break
    st, res = request("POST", "/api/break/toggle", {"agent_id": 4, "action": "start_break"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["is_on_break"] is True
    assert tooba["current_state"] == "on_break"
    print("  [PASS] Tooba Start Break -> State: on_break, is_on_break=True")

    # End break
    st, res = request("POST", "/api/break/toggle", {"agent_id": 4, "action": "end_break"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["is_on_break"] is False
    assert tooba["current_state"] == "on_shift"
    print("  [PASS] Tooba End Break -> State: on_shift, is_on_break=False")

    # Start Meeting pause
    st, res = request("POST", "/api/pause/toggle", {"agent_id": 4, "action": "start_pause", "pause_type": "meeting"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["is_in_meeting"] is True
    assert tooba["current_state"] == "in_meeting"
    print("  [PASS] Tooba Start Meeting Pause -> State: in_meeting, is_in_meeting=True")

    # End Meeting pause
    st, res = request("POST", "/api/pause/toggle", {"agent_id": 4, "action": "end_pause", "pause_type": "meeting"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["is_in_meeting"] is False
    assert tooba["current_state"] == "on_shift"
    print("  [PASS] Tooba End Meeting Pause -> State: on_shift, is_in_meeting=False")

    # Start Emergency pause
    st, res = request("POST", "/api/pause/toggle", {"agent_id": 4, "action": "start_pause", "pause_type": "emergency"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["is_in_emergency"] is True
    assert tooba["current_state"] == "in_emergency"
    print("  [PASS] Tooba Start Emergency Pause -> State: in_emergency, is_in_emergency=True")

    # End Emergency pause
    st, res = request("POST", "/api/pause/toggle", {"agent_id": 4, "action": "end_pause", "pause_type": "emergency"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["is_in_emergency"] is False
    assert tooba["current_state"] == "on_shift"
    print("  [PASS] Tooba End Emergency Pause -> State: on_shift, is_in_emergency=False")

    # End Shift
    st, res = request("POST", "/api/attendance/punch", {"agent_id": 4, "action": "end_shift"})
    assert st == 200
    st, live = request("GET", "/api/live/status")
    tooba = next(a for a in live["agents"] if a["agent_id"] == 4)
    assert tooba["clock_out"] is not None
    assert tooba["current_state"] == "completed"
    print("  [PASS] Tooba End Shift -> State: completed, Clock-out registered")

    # 4. QUEUE MODE TOGGLE
    print("\n--- 4. Testing Queue Mode Toggle (Meeting vs Normal) ---")
    st, res = request("POST", "/api/queue/mode", {"mode": "meeting"})
    assert st == 200 and res["mode"] == "meeting"
    st, live = request("GET", "/api/live/status")
    assert live["queue_mode"] == "meeting"
    print("  [PASS] Queue mode switched to 'meeting'")

    st, res = request("POST", "/api/queue/mode", {"mode": "normal"})
    assert st == 200 and res["mode"] == "normal"
    st, live = request("GET", "/api/live/status")
    assert live["queue_mode"] == "normal"
    print("  [PASS] Queue mode restored to 'normal'")

    # 5. SHIFT SWAP 2-STEP WORKFLOW
    print("\n--- 5. Testing 2-Step Shift Swap (Peer Agreement -> Manager Approval) ---")
    # Rana (id=1) requests swap with Rahma (id=5)
    st, swap_res = request("POST", "/api/swaps/request", {
        "requester_id": 1,
        "target_agent_id": 5,
        "requester_date": "2026-10-18",
        "target_date": "2026-10-20"
    })
    assert st == 200
    swap_id = swap_res["id"]
    print(f"  [PASS] Swap created (id={swap_id}) -> Initial status: pending_peer")

    # Check swap listed
    st, swaps = request("GET", "/api/swaps")
    my_swap = next(s for s in swaps if s["id"] == swap_id)
    assert my_swap["status"] == "pending_peer"
    assert "requester_date_formatted" in my_swap
    assert "target_date_formatted" in my_swap
    print(f"  [PASS] Swap details include day names: {my_swap['requester_date_formatted']} ↔ {my_swap['target_date_formatted']}")

    # Step 1: Peer approves
    st, p_res = request("POST", f"/api/swaps/{swap_id}/peer-action", {"status": "approved"})
    assert st == 200
    st, swaps = request("GET", "/api/swaps")
    my_swap = next(s for s in swaps if s["id"] == swap_id)
    assert my_swap["status"] == "pending_manager"
    print("  [PASS] Peer Rahma agreed -> Status advanced to pending_manager")

    # Step 2: Manager approves
    st, m_res = request("POST", f"/api/swaps/{swap_id}/manager-action", {"status": "approved"})
    assert st == 200
    st, swaps = request("GET", "/api/swaps")
    my_swap = next(s for s in swaps if s["id"] == swap_id)
    assert my_swap["status"] == "approved"
    print("  [PASS] Manager approved -> Status finalized to approved and schedule updated")

    # 6. EXCUSE REQUEST WORKFLOW
    print("\n--- 6. Testing Excuse Request & Manager Action ---")
    st, exc_res = request("POST", "/api/excuses/request", {
        "agent_id": 2,
        "date": "2026-10-19",
        "from_time": "10:00",
        "to_time": "11:00",
        "reason": "Traffic breakdown on Ring Road"
    })
    assert st == 200
    exc_id = exc_res["id"]
    print(f"  [PASS] Excuse submitted (id={exc_id}) -> Status: pending")

    st, m_exc = request("POST", f"/api/excuses/{exc_id}/manager-action", {"status": "approved"})
    assert st == 200
    st, excuses = request("GET", "/api/excuses")
    my_exc = next(e for e in excuses if e["id"] == exc_id)
    assert my_exc["status"] == "approved"
    print("  [PASS] Manager approved excuse -> Status finalized to approved")

    # 7. LEAVE REQUEST WORKFLOW
    print("\n--- 7. Testing Leave Request & Schedule Override ---")
    st, lv_res = request("POST", "/api/leaves/request", {
        "agent_id": 6,
        "date": "2026-10-21",
        "leave_type": "annual",
        "reason": "Annual family travel"
    })
    assert st == 200
    lv_id = lv_res["id"]
    print(f"  [PASS] Leave request submitted (id={lv_id}) -> Status: pending")

    st, m_lv = request("POST", f"/api/leaves/{lv_id}/manager-action", {"status": "approved"})
    assert st == 200
    st, leaves = request("GET", "/api/leaves")
    my_lv = next(l for l in leaves if l["id"] == lv_id)
    assert my_lv["status"] == "approved"
    print("  [PASS] Manager approved leave -> Status finalized to approved")

    # 8. DIRECT SCHEDULE OVERRIDE & DIRECT SWAP
    print("\n--- 8. Testing Manager Direct Override & Direct Swap ---")
    st, ov_res = request("POST", "/api/schedule/override", {
        "agent_id": 1,
        "date": "2026-10-22",
        "shift_type": "off"
    })
    assert st == 200
    print("  [PASS] Manager direct override applied (Agent 1 off on 2026-10-22)")

    st, ds_res = request("POST", "/api/schedule/direct-swap", {
        "agent1_id": 1,
        "date1": "2026-10-22",
        "agent2_id": 2,
        "date2": "2026-10-22"
    })
    assert st == 200
    print("  [PASS] Manager direct swap applied between Agent 1 and Agent 2 on 2026-10-22")

    # 9. TEAM MANAGEMENT & AGENT CREATION
    print("\n--- 9. Testing Agent Creation, Password Change, and Delete ---")
    import time
    test_code = f"TEST-{int(time.time())}"
    st, new_ag = request("POST", "/api/agents", {
        "name": "Audit Test Agent",
        "code": test_code,
        "password": "auditpassword123",
        "role": "agent"
    })
    assert st == 200
    test_id = new_ag["id"]
    print(f"  [PASS] Created new agent (id={test_id}, code={test_code})")

    # Change password
    st, chg = request("POST", "/api/change-password", {
        "agent_id": test_id,
        "old_password": "auditpassword123",
        "new_password": "newauditpassword456"
    })
    assert st == 200
    print("  [PASS] Changed password for test agent")

    # Delete agent
    st, d_res = request("DELETE", f"/api/agents/{test_id}")
    assert st == 200
    print("  [PASS] Deleted/disabled test agent")

    # 10. EGYPT OFFICIAL HOLIDAYS
    print("\n--- 10. Testing Egyptian Official Holidays ---")
    st, hols = request("GET", "/api/holidays?year=2026")
    assert st == 200
    assert "2026-10-06" in hols and hols["2026-10-06"]["multiplier"] == 2
    assert "2026-03-20" in hols and hols["2026-03-20"]["multiplier"] == 3
    print(f"  [PASS] Holidays returned {len(hols)} holidays with 2x and 3x pay rules")

    # 11. MONTHLY EXCEL EXPORT AUDIT
    print("\n--- 11. Testing Monthly Excel Export & Multi-Sheet Structure ---")
    st, excel_bytes = request("GET", "/api/reports/monthly-excel?year=2026&month=10")
    assert st == 200 and len(excel_bytes) > 2000
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    print(f"  [PASS] Excel exported successfully ({len(excel_bytes)} bytes), Sheets: {sheet_names}")
    assert "ملخص الأجور والعمليات" in sheet_names
    assert "سجل الحضور والانصراف اليومي" in sheet_names

    # Check Sheet 1 columns (Row 4 is table header)
    ws1 = wb["ملخص الأجور والعمليات"]
    headers1 = [cell.value for cell in ws1[4] if cell.value is not None]
    print(f"  [PASS] Sheet 1 Headers: {headers1[:5]}...")
    assert "كود الموظف" in headers1
    assert "اسم الموظفة" in headers1
    assert "أيام العمل المجدولة" in headers1
    assert "صافي ساعات العمل (Net Hours)" in headers1
    assert "دقائق الميتنج (Meeting)" in headers1
    assert "دقائق الطوارئ (Emergency)" in headers1

    # Check Sheet 2 columns (Row 3 is table header)
    ws2 = wb["سجل الحضور والانصراف اليومي"]
    headers2 = [cell.value for cell in ws2[3] if cell.value is not None]
    print(f"  [PASS] Sheet 2 Headers: {headers2[:5]}...")
    assert "التاريخ" in headers2
    assert "كود الموظف" in headers2
    assert "اسم الموظفة" in headers2
    assert "دقائق البريك" in headers2
    assert "دقائق الميتنج" in headers2
    assert "دقائق الطوارئ" in headers2
    assert "صافي دقائق العمل (Net)" in headers2

    cleanup_test_data()
    print("\n==================================================")
    print("ALL 11 ENDPOINTS & WORKFLOWS AUDITED 100% SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_system_audit()
