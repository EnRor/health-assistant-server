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

        # Немедленный ответ Telegram для избежания таймаута и повторов
        response = jsonify({"ok": True})

        # Обработка callback_query (нажатие кнопок меню)
        if "callback_query" in data:
            callback = data["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            callback_query_id = callback["id"]
            callback_data = callback["data"]

            # Подтверждаем callback_query сразу (чтобы Telegram не думал, что мы игнорируем)
            from user_logic import answer_callback_query
            answer_callback_query(callback_query_id)

            # Запускаем обработку callback в отдельном потоке
            threading.Thread(target=handle_callback_query_data, args=(chat_id, callback_data), daemon=True).start()

        # Обработка обычных сообщений с текстом
        elif "message" in data and "text" in data["message"]:
            chat_id = data["message"]["chat"]["id"]
            user_message = data["message"]["text"]

            # Запускаем обработку сообщения в отдельном потоке
            threading.Thread(target=handle_message_data, args=(chat_id, user_message), daemon=True).start()

        return response
    except Exception as e:
        print("❌ Ошибка во внешнем webhook:", e)
        return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
