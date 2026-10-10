import threading
import time
import sys
from datetime import datetime, date, timedelta
import requests
from typing import Optional, Dict, Any
from database import get_connection

DEFAULT_BOT_TOKEN = "8947096598:AAFNWrxNqq_lZFP9_nhd6tgm2D3GYwIVmbk"
DEFAULT_CHAT_ID = "6155717959"

def safe_log(msg: str):
    """Safely log messages to stdout without UnicodeEncodeError crashes on Windows."""
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(msg.encode('ascii', 'backslashreplace').decode('ascii'), flush=True)
        except Exception:
            pass

def format_date_with_day(date_str: str) -> str:
    """Format date string as 'DayName / اسم_اليوم (YYYY-MM-DD)'."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        days_map = {
            "Monday": "الإثنين",
            "Tuesday": "الثلاثاء",
            "Wednesday": "الأربعاء",
            "Thursday": "الخميس",
            "Friday": "الجمعة",
            "Saturday": "السبت",
            "Sunday": "الأحد"
        }
        en_day = dt.strftime("%A")
        ar_day = days_map.get(en_day, en_day)
        return f"{en_day} / {ar_day} ({date_str})"
    except Exception:
        return date_str

def execute_swap_in_db(cursor, req_id: int, tgt_id: int, d1: str, d2: str) -> bool:
    """
    Executes a swap between requester (req_id) giving up day d1 (off -> work)
    and target (tgt_id) giving up day d2 (off -> work).
    """
    cursor.execute("SELECT shift_type, shift_hours FROM schedules WHERE agent_id = ? AND date = ?;", (req_id, d1))
    s_req_d1 = cursor.fetchone()
    cursor.execute("SELECT shift_type, shift_hours FROM schedules WHERE agent_id = ? AND date = ?;", (tgt_id, d1))
    s_tgt_d1 = cursor.fetchone()

    cursor.execute("SELECT shift_type, shift_hours FROM schedules WHERE agent_id = ? AND date = ?;", (req_id, d2))
    s_req_d2 = cursor.fetchone()
    cursor.execute("SELECT shift_type, shift_hours FROM schedules WHERE agent_id = ? AND date = ?;", (tgt_id, d2))
    s_tgt_d2 = cursor.fetchone()

    # Determine shifts on d1:
    # Target was working on d1, now gets the off day; Requester was off, now works.
    req_d1_type = s_tgt_d1["shift_type"] if s_tgt_d1 else "work"
    req_d1_hours = s_tgt_d1["shift_hours"] if s_tgt_d1 else "10:00 - 19:00"
    tgt_d1_type = s_req_d1["shift_type"] if s_req_d1 else "off"
    tgt_d1_hours = s_req_d1["shift_hours"] if s_req_d1 else "Day Off"

    # Determine shifts on d2:
    # Requester was working on d2, now gets the off day; Target was off, now works.
    req_d2_type = s_tgt_d2["shift_type"] if s_tgt_d2 else "off"
    req_d2_hours = s_tgt_d2["shift_hours"] if s_tgt_d2 else "Day Off"
    tgt_d2_type = s_req_d2["shift_type"] if s_req_d2 else "work"
    tgt_d2_hours = s_req_d2["shift_hours"] if s_req_d2 else "10:00 - 19:00"

    cursor.execute("UPDATE schedules SET shift_type = ?, shift_hours = ? WHERE agent_id = ? AND date = ?;",
                   (req_d1_type, req_d1_hours, req_id, d1))
    cursor.execute("UPDATE schedules SET shift_type = ?, shift_hours = ? WHERE agent_id = ? AND date = ?;",
                   (tgt_d1_type, tgt_d1_hours, tgt_id, d1))

    cursor.execute("UPDATE schedules SET shift_type = ?, shift_hours = ? WHERE agent_id = ? AND date = ?;",
                   (req_d2_type, req_d2_hours, req_id, d2))
    cursor.execute("UPDATE schedules SET shift_type = ?, shift_hours = ? WHERE agent_id = ? AND date = ?;",
                   (tgt_d2_type, tgt_d2_hours, tgt_id, d2))
    return True

def get_telegram_config():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('telegram_bot_token', 'telegram_chat_id');")
    rows = cursor.fetchall()
    conn.close()
    cfg = {r["key"]: r["value"] for r in rows}
    token = cfg.get("telegram_bot_token", "").strip() or DEFAULT_BOT_TOKEN
    chat_id = cfg.get("telegram_chat_id", "").strip() or DEFAULT_CHAT_ID
    return token, chat_id

def send_telegram_message(text: str, reply_markup: Optional[Dict[str, Any]] = None, custom_chat_id: Optional[str] = None) -> bool:
    token, chat_id = get_telegram_config()
    target_chat = custom_chat_id or chat_id
    if not token or not target_chat:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = requests.post(url, json=payload, timeout=8)
        return resp.status_code == 200
    except Exception as e:
        safe_log(f"[Telegram] Failed to send message: {e}")
        return False

def notify_new_excuse(excuse_id: int, agent_name: str, date_str: str, from_time: str, to_time: str, reason: str):
    formatted_date = format_date_with_day(date_str)
    text = (
        f"🔔 <b>New Excuse Request</b>\n\n"
        f"👤 <b>Agent:</b> {agent_name}\n"
        f"📅 <b>Date:</b> {formatted_date}\n"
        f"⏰ <b>Hours:</b> {from_time} to {to_time}\n"
        f"📝 <b>Reason:</b> {reason}\n\n"
        f"<i>Select an action below to update live roster:</i>"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve Excuse", "callback_data": f"approve_excuse:{excuse_id}"},
                {"text": "❌ Reject", "callback_data": f"reject_excuse:{excuse_id}"}
            ]
        ]
    }
    return send_telegram_message(text, markup)

def notify_new_swap(swap_id: int, requester_name: str, target_name: str, req_date: str, target_date: str):
    f_req_date = format_date_with_day(req_date)
    f_tgt_date = format_date_with_day(target_date)
    text = (
        f"🔄 <b>Shift Swap Request (Peer Approved)</b>\n\n"
        f"👤 <b>Requester:</b> {requester_name}\n"
        f"📅 <b>Off-Day Given Up:</b> {f_req_date}\n\n"
        f"🤝 <b>Colleague:</b> {target_name} (Agreed ✔️)\n"
        f"📅 <b>Off-Day Given Up:</b> {f_tgt_date}\n\n"
        f"<i>Both colleagues agreed. Do you approve applying this swap to the Master Roster?</i>"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve Swap", "callback_data": f"approve_swap:{swap_id}"},
                {"text": "❌ Decline", "callback_data": f"reject_swap:{swap_id}"}
            ]
        ]
    }
    return send_telegram_message(text, markup)

def notify_new_leave(leave_id: int, agent_name: str, date_str: str, leave_type: str, reason: str):
    f_date = format_date_with_day(date_str)
    type_labels = {
        "annual": "Annual Leave (إجازة سنوية)",
        "sick": "Sick Leave (إجازة مرضية)",
        "emergency": "Emergency Leave (إجازة عارضة)",
        "comp_off": "Compensatory Off (بدل راحة)"
    }
    t_label = type_labels.get(leave_type, leave_type)
    text = (
        f"🌴 <b>New Official Leave Request</b>\n\n"
        f"👤 <b>Agent:</b> {agent_name}\n"
        f"📅 <b>Date:</b> {f_date}\n"
        f"🏷️ <b>Type:</b> {t_label}\n"
        f"📝 <b>Reason:</b> {reason}\n\n"
        f"<i>Select an action below to update live roster:</i>"
    )
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve Leave", "callback_data": f"approve_leave:{leave_id}"},
                {"text": "❌ Reject", "callback_data": f"reject_leave:{leave_id}"}
            ]
        ]
    }
    return send_telegram_message(text, markup)

def send_test_notification() -> Dict[str, Any]:
    token, chat_id = get_telegram_config()
    if not token:
        return {"success": False, "message": "Bot token is missing."}
    if not chat_id:
        return {
            "success": False, 
            "message": "Chat ID not linked yet. Please open Telegram, search for @Liveop_bot and click Start, then test again."
        }

    conn = get_connection()
    cursor = conn.cursor()

    # Create a real test Swap request between Rana (ID 1) and Bassant (ID 2)
    # Using 2026-10-12 (Monday - Rana off) and 2026-10-14 (Wednesday - Bassant off)
    req_date = "2026-10-12"
    target_date = "2026-10-14"
    now_str = datetime.now().isoformat()

    cursor.execute("""
    INSERT INTO swap_requests (requester_id, target_agent_id, requester_date, target_date, status, created_at)
    VALUES (1, 2, ?, ?, 'pending_manager', ?);
    """, (req_date, target_date, now_str))
    swap_id = cursor.lastrowid
    conn.commit()
    conn.close()

    ok = notify_new_swap(swap_id, "Rana", "Bassant ragab", req_date, target_date)
    if ok:
        return {
            "success": True, 
            "message": f"Test Swap Request #{swap_id} sent to Telegram with Day Names! Check your phone and tap [Approve Swap] or [Decline]."
        }
    else:
        return {"success": False, "message": "Failed to send message via Telegram API."}

# Background Polling Worker for auto-pairing and inline approvals
class TelegramPollingWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.last_update_id = 0
        self.running = True

    def run(self):
        safe_log("[Telegram] Background listener initiated.")
        while self.running:
            token, chat_id = get_telegram_config()
            if not token:
                time.sleep(10)
                continue

            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates"
                params = {
                    "timeout": 10,
                    "allowed_updates": ["message", "callback_query"]
                }
                if self.last_update_id > 0:
                    params["offset"] = self.last_update_id + 1
                resp = requests.get(url, params=params, timeout=25)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        try:
                            # 1. Handle incoming message (Auto-pairing with Manager!)
                            if "message" in update:
                                msg = update["message"]
                                sender_chat_id = str(msg.get("chat", {}).get("id"))
                                user_first_name = msg.get("from", {}).get("first_name", "Manager")
                                safe_log(f"[Telegram] Processing message from Chat ID: {sender_chat_id}")

                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("UPDATE settings SET value = ? WHERE key = 'telegram_chat_id';", (sender_chat_id,))
                                cursor.execute("UPDATE settings SET value = ? WHERE key = 'telegram_bot_token';", (token,))
                                conn.commit()
                                conn.close()

                                welcome_msg = (
                                    f"👋 <b>Welcome, {user_first_name}!</b>\n\n"
                                    f"✅ <b>LiveOps Commander is now connected.</b>\n\n"
                                    f"Your Chat ID <code>{sender_chat_id}</code> is linked.\n"
                                    f"You will receive instant actionable notifications here for:\n"
                                    f"• Shift & Off-Day Swaps\n"
                                    f"• Official Excuse & Lateness Requests\n\n"
                                    f"All actions taken here update the Live Dashboard in real-time."
                                )
                                send_telegram_message(welcome_msg, custom_chat_id=sender_chat_id)
                                safe_log(f"[Telegram] Auto-paired successfully with Chat ID: {sender_chat_id}")

                            # 2. Handle callback queries (inline buttons)
                            if "callback_query" in update:
                                self.handle_callback(update["callback_query"], token)
                        except Exception as update_err:
                            safe_log(f"[Telegram] Error processing update: {update_err}")
                else:
                    safe_log(f"[Telegram] getUpdates returned HTTP {resp.status_code}")
                    time.sleep(2)
            except Exception as e:
                safe_log(f"[Telegram] Polling loop error: {e}")
                time.sleep(3)

    def handle_callback(self, cq: Dict[str, Any], token: str):
        cq_id = cq["id"]
        cb_data = cq.get("data", "")
        message = cq.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")

        safe_log(f"[Telegram] Callback received: {cb_data} on msg {msg_id}")

        # 1. Immediately acknowledge callback query to stop Telegram client loading spinner
        try:
            ans_url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
            requests.post(ans_url, json={"callback_query_id": cq_id, "text": "Updating Live Dashboard..."}, timeout=5)
        except Exception as e:
            safe_log(f"[Telegram] Error in answerCallbackQuery: {e}")

        parts = cb_data.split(":")
        if len(parts) == 2:
            action, item_id = parts[0], int(parts[1])
            conn = get_connection()
            cursor = conn.cursor()

            ack_text = "Action processed successfully"
            if action == "approve_excuse":
                cursor.execute("UPDATE excuse_requests SET status = 'approved', updated_at = datetime('now') WHERE id = ?;", (item_id,))
                cursor.execute("SELECT agent_id, date FROM excuse_requests WHERE id = ?;", (item_id,))
                exc = cursor.fetchone()
                if exc:
                    cursor.execute("UPDATE time_logs SET late_minutes = 0 WHERE agent_id = ? AND date = ?;", (exc["agent_id"], exc["date"]))
                ack_text = "Excuse Approved ✔️ (Late penalty cleared on Live Board)"
            elif action == "reject_excuse":
                cursor.execute("UPDATE excuse_requests SET status = 'rejected', updated_at = datetime('now') WHERE id = ?;", (item_id,))
                ack_text = "Excuse Rejected ❌"
            elif action == "approve_swap":
                cursor.execute("SELECT requester_id, target_agent_id, requester_date, target_date FROM swap_requests WHERE id = ?;", (item_id,))
                swap = cursor.fetchone()
                if swap:
                    execute_swap_in_db(cursor, swap["requester_id"], swap["target_agent_id"], swap["requester_date"], swap["target_date"])
                    cursor.execute("UPDATE swap_requests SET status = 'approved', updated_at = datetime('now') WHERE id = ?;", (item_id,))
                    ack_text = "Swap Approved ✔️ (Master Roster updated live)"
                    safe_log(f"[Telegram] Swap #{item_id} successfully executed in database.")
                else:
                    ack_text = "Swap record not found"
            elif action == "reject_swap":
                cursor.execute("UPDATE swap_requests SET status = 'rejected', updated_at = datetime('now') WHERE id = ?;", (item_id,))
                ack_text = "Swap Declined ❌"
            elif action == "approve_leave":
                cursor.execute("UPDATE leave_requests SET status = 'approved', updated_at = datetime('now') WHERE id = ?;", (item_id,))
                cursor.execute("SELECT agent_id, date, leave_type FROM leave_requests WHERE id = ?;", (item_id,))
                l_info = cursor.fetchone()
                if l_info:
                    cursor.execute("UPDATE schedules SET shift_type = 'leave', shift_hours = 'إجازة معتمدة' WHERE agent_id = ? AND date = ?;", (l_info["agent_id"], l_info["date"]))
                ack_text = "Leave Approved ✔️ (Master Roster updated live)"
                safe_log(f"[Telegram] Leave #{item_id} successfully approved in database.")
            elif action == "reject_leave":
                cursor.execute("UPDATE leave_requests SET status = 'rejected', updated_at = datetime('now') WHERE id = ?;", (item_id,))
                ack_text = "Leave Declined ❌"

            conn.commit()
            conn.close()

            # 2. Update Telegram message to reflect decision and remove action buttons
            try:
                edit_url = f"https://api.telegram.org/bot{token}/editMessageText"
                orig_text = message.get("text", "")
                requests.post(edit_url, json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": f"{orig_text}\n\n<b>📌 Decision:</b> {ack_text}",
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": []}
                }, timeout=5)
                safe_log(f"[Telegram] Message #{msg_id} edited with final decision.")
            except Exception as e:
                safe_log(f"[Telegram] Failed to editMessageText: {e}")

_worker = None

def start_telegram_listener():
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = TelegramPollingWorker()
        _worker.start()
        safe_log("[Telegram] Background listener worker started.")
