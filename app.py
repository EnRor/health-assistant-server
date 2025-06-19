import os
import json
import threading
from flask import Flask, request, jsonify
from datetime import datetime
from user_logic import handle_message_data, handle_callback_query_data

app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return "OK", 200

@app.route("/cron", methods=["GET"])
def cron():
    print(f"[cron] Ping received at {datetime.utcnow().isoformat()} UTC")
    return "Cron OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("[webhook] Incoming:", json.dumps(data, ensure_ascii=False))

        # Немедленно отвечаем Telegram, чтобы избежать повторной отправки
        response = jsonify({"ok": True})

        if "callback_query" in data:
            callback_query = data["callback_query"]
            threading.Thread(
                target=handle_callback_query_data,
                args=(callback_query["message"]["chat"]["id"], callback_query),
                daemon=True
            ).start()

        elif "message" in data:
            message = data["message"]
            threading.Thread(
                target=handle_message_data,
                args=(message["chat"]["id"], message),
                daemon=True
            ).start()

        return response

    except Exception as e:
        print("❌ Ошибка во внешнем webhook:", e)
        return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
