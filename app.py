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

        # Немедленно отвечаем Telegram, чтобы избежать повторных запросов
        response = jsonify({"ok": True})

        # Обработка в отдельном потоке
        if "callback_query" in data:
            callback_data = data["callback_query"]
            threading.Thread(
                target=handle_callback_query_data,
                args=(callback_data, callback_data["message"]["chat"]["id"]),
                daemon=True
            ).start()
        elif "message" in data:
            message_data = data["message"]
            threading.Thread(
                target=handle_message_data,
                args=(message_data, message_data["chat"]["id"]),
                daemon=True
            ).start()

        return response

    except Exception as e:
        print("❌ Ошибка во внешнем webhook:", e)
        return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
