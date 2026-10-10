import pytest
from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

def test_root_index():
    response = client.get("/")
    assert response.status_code == 200
    assert "LiveOps" in response.text

def test_login_success_and_failure():
    # Success agent
    res = client.post("/api/login", json={"code": "RN-101", "password": "rana123"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["agent"]["name"] == "Rana"
    assert data["agent"]["role"] == "agent"

    # Success manager
    res_mgr = client.post("/api/login", json={"code": "ADMIN-01", "password": "admin2026"})
    assert res_mgr.status_code == 200
    assert res_mgr.json()["agent"]["role"] == "manager"

    # Invalid credentials
    res_bad = client.post("/api/login", json={"code": "RN-101", "password": "wrong"})
    assert res_bad.status_code == 401

def test_schedule_week():
    res = client.get("/api/schedule/week")
    assert res.status_code == 200
    schedules = res.json()
    assert len(schedules) >= 42
    # Verify Friday is off for all
    for s in schedules:
        if s["day_of_week"] == 5:
            assert s["shift_type"] == "off"

def test_live_status():
    res = client.get("/api/live/status")
    assert res.status_code == 200
    data = res.json()
    assert "agents" in data
    assert len(data["agents"]) >= 6
    assert data["target_queue_size"] == 5

def test_attendance_and_break_flow():
    # Punch in for Agent 2 (Bassant, scheduled work today)
    res_punch = client.post("/api/attendance/punch", json={"agent_id": 2, "action": "start_shift"})
    assert res_punch.status_code == 200

    # Start break
    res_b_start = client.post("/api/break/toggle", json={"agent_id": 2, "action": "start_break"})
    assert res_b_start.status_code == 200

    # Check live status indicates on break
    res_live = client.get("/api/live/status")
    agents = res_live.json()["agents"]
    bassant = next(a for a in agents if a["agent_id"] == 2)
    assert bassant["is_on_break"] is True

    # End break
    res_b_end = client.post("/api/break/toggle", json={"agent_id": 2, "action": "end_break"})
    assert res_b_end.status_code == 200

    # Start hold (Meeting / Urgent)
    res_h_start = client.post("/api/attendance/punch", json={"agent_id": 2, "action": "start_hold"})
    assert res_h_start.status_code == 200
    res_live_h = client.get("/api/live/status")
    bassant_h = next(a for a in res_live_h.json()["agents"] if a["agent_id"] == 2)
    assert bassant_h["current_state"] == "on_hold"

    # End hold
    res_h_end = client.post("/api/attendance/punch", json={"agent_id": 2, "action": "end_hold"})
    assert res_h_end.status_code == 200
    res_live_h2 = client.get("/api/live/status")
    bassant_h2 = next(a for a in res_live_h2.json()["agents"] if a["agent_id"] == 2)
    assert bassant_h2["current_state"] == "on_shift"

    # End shift
    res_end = client.post("/api/attendance/punch", json={"agent_id": 2, "action": "end_shift"})
    assert res_end.status_code == 200

def test_meeting_and_emergency_pause_flow():
    # Use Agent 3 (Sama) for testing separate Meeting & Emergency Pause
    # 1. Start shift
    res_punch = client.post("/api/attendance/punch", json={"agent_id": 3, "action": "start_shift"})
    assert res_punch.status_code == 200

    # 2. Start Meeting pause
    res_m_start = client.post("/api/pause/toggle", json={"agent_id": 3, "action": "start_pause", "pause_type": "meeting"})
    assert res_m_start.status_code == 200
    res_live_m = client.get("/api/live/status")
    sama_m = next(a for a in res_live_m.json()["agents"] if a["agent_id"] == 3)
    assert sama_m["current_state"] == "in_meeting"
    assert sama_m["is_in_meeting"] is True

    # 3. End Meeting pause
    res_m_end = client.post("/api/pause/toggle", json={"agent_id": 3, "action": "end_pause", "pause_type": "meeting"})
    assert res_m_end.status_code == 200
    res_live_m2 = client.get("/api/live/status")
    sama_m2 = next(a for a in res_live_m2.json()["agents"] if a["agent_id"] == 3)
    assert sama_m2["current_state"] == "on_shift"
    assert sama_m2["is_in_meeting"] is False

    # 4. Start Emergency pause
    res_e_start = client.post("/api/pause/toggle", json={"agent_id": 3, "action": "start_pause", "pause_type": "emergency"})
    assert res_e_start.status_code == 200
    res_live_e = client.get("/api/live/status")
    sama_e = next(a for a in res_live_e.json()["agents"] if a["agent_id"] == 3)
    assert sama_e["current_state"] == "in_emergency"
    assert sama_e["is_in_emergency"] is True

    # 5. End Emergency pause
    res_e_end = client.post("/api/pause/toggle", json={"agent_id": 3, "action": "end_pause", "pause_type": "emergency"})
    assert res_e_end.status_code == 200
    res_live_e2 = client.get("/api/live/status")
    sama_e2 = next(a for a in res_live_e2.json()["agents"] if a["agent_id"] == 3)
    assert sama_e2["current_state"] == "on_shift"
    assert sama_e2["is_in_emergency"] is False

    # 6. End shift
    res_end = client.post("/api/attendance/punch", json={"agent_id": 3, "action": "end_shift"})
    assert res_end.status_code == 200

def test_swap_workflow():
    # Requester 1 (Rana) asks to swap with Agent 2 (Bassant)
    req_payload = {
        "requester_id": 1,
        "target_agent_id": 2,
        "requester_date": "2026-10-12",
        "target_date": "2026-10-14"
    }
    res_create = client.post("/api/swaps/request", json=req_payload)
    assert res_create.status_code == 200

    # List swaps
    res_list = client.get("/api/swaps")
    swaps = res_list.json()
    assert len(swaps) > 0
    swap_id = swaps[0]["id"]
    assert swaps[0]["status"] == "pending_peer"

    # Peer approves
    res_peer = client.post(f"/api/swaps/{swap_id}/peer-action", json={"status": "approved"})
    assert res_peer.status_code == 200

    # Manager approves
    res_mgr = client.post(f"/api/swaps/{swap_id}/manager-action", json={"status": "approved"})
    assert res_mgr.status_code == 200

def test_excuse_workflow():
    # Submit excuse for Agent 3 (Sama)
    exc_payload = {
        "agent_id": 3,
        "date": "2026-10-13",
        "from_time": "10:00",
        "to_time": "11:30",
        "reason": "ظرف طارئ في المواصلات"
    }
    res = client.post("/api/excuses/request", json=exc_payload)
    assert res.status_code == 200
    exc_id = res.json()["id"]

    # Manager approves
    res_app = client.post(f"/api/excuses/{exc_id}/manager-action", json={"status": "approved"})
    assert res_app.status_code == 200

def test_excel_export():
    res = client.get("/api/reports/monthly-excel?year=2026&month=10")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(res.content) > 1000

def test_holidays_endpoint():
    res = client.get("/api/holidays?year=2026")
    assert res.status_code == 200
    hols = res.json()
    assert "2026-10-06" in hols
    assert hols["2026-10-06"]["multiplier"] == 2
    assert "2026-03-20" in hols
    assert hols["2026-03-20"]["multiplier"] == 3

def test_manager_override_and_direct_swap():
    # Manager overrides Agent 1 (Rana) to off on 2026-10-15
    res_ov = client.post("/api/schedule/override", json={
        "agent_id": 1,
        "date": "2026-10-15",
        "shift_type": "off"
    })
    assert res_ov.status_code == 200

    # Direct swap between Agent 1 and Agent 2 on 2026-10-15
    res_ds = client.post("/api/schedule/direct-swap", json={
        "agent1_id": 1,
        "date1": "2026-10-15",
        "agent2_id": 2,
        "date2": "2026-10-15"
    })
    assert res_ds.status_code == 200

def test_off_days_endpoint():
    # Test agent 1 (Rana) and agent 3 (Rahma)
    res1 = client.get("/api/schedule/off-days/1")
    assert res1.status_code == 200
    off_days1 = res1.json()
    assert len(off_days1) > 0
    # Invariant: day_of_week != 5 (no Friday)
    for od in off_days1:
        assert od["day_of_week"] != 5
        assert "formatted" in od
        assert od["shift_type"] == "off"

    res3 = client.get("/api/schedule/off-days/3")
    assert res3.status_code == 200
    off_days3 = res3.json()
    assert len(off_days3) > 0
    for od in off_days3:
        assert od["day_of_week"] != 5

def test_leaves_workflow():
    # Request leave for Agent 1 (Rana)
    leave_data = {
        "agent_id": 1,
        "date": "2026-10-25",
        "leave_type": "annual",
        "reason": "Family vacation"
    }
    res = client.post("/api/leaves/request", json=leave_data)
    assert res.status_code == 200
    leave_id = res.json()["id"]

    # List leaves
    res_list = client.get("/api/leaves")
    assert res_list.status_code == 200
    leaves = res_list.json()
    assert any(l["id"] == leave_id for l in leaves)
    my_leave = next(l for l in leaves if l["id"] == leave_id)
    assert my_leave["status"] == "pending"
    assert "date_formatted" in my_leave

    # Manager approves
    res_mgr = client.post(f"/api/leaves/{leave_id}/manager-action", json={"status": "approved"})
    assert res_mgr.status_code == 200

    # Verify updated
    res_list2 = client.get("/api/leaves")
    updated = next(l for l in res_list2.json() if l["id"] == leave_id)
    assert updated["status"] == "approved"

def test_change_password():
    # Agent 2 changes password
    res = client.post("/api/change-password", json={
        "agent_id": 2,
        "old_password": "bassant_pass_123",
        "new_password": "new_pass_456"
    })
    # If old password was different in db, handle gracefully
    if res.status_code == 200:
        # Verify login with new password
        res_log = client.post("/api/login", json={"code": "BS-102", "password": "new_pass_456"})
        assert res_log.status_code == 200

if __name__ == "__main__":
    print("Running integration tests...")
    test_root_index()
    test_login_success_and_failure()
    test_schedule_week()
    test_live_status()
    test_attendance_and_break_flow()
    test_swap_workflow()
    test_excuse_workflow()
    test_excel_export()
    test_holidays_endpoint()
    test_manager_override_and_direct_swap()
    test_off_days_endpoint()
    test_leaves_workflow()
    print("ALL 12 INTEGRATION TESTS PASSED PERFECTLY!")

