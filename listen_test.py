import requests
import time

TOKEN = "8947096598:AAFNWrxNqq_lZFP9_nhd6tgm2D3GYwIVmbk"

print("=" * 60)
print("Listening for Telegram messages on @Liveop_bot for 60 seconds...")
print("=" * 60)

start_time = time.time()
while time.time() - start_time < 60:
    try:
        res = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"timeout": 5}, timeout=10).json()
        updates = res.get("result", [])
        if updates:
            print(f"FOUND UPDATE: {updates}")
            for u in updates:
                chat_id = u.get("message", {}).get("chat", {}).get("id")
                text = u.get("message", {}).get("text", "")
                print(f"Chat ID: {chat_id}, Text: {text}")
                # Reply to user
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": "Hello! Received your message on LiveOps Commander."
                })
            break
        else:
            time.sleep(1)
    except Exception as e:
        print("Error:", e)
        time.sleep(2)

print("Listener finished.")
