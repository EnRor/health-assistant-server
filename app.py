import os
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

openai = OpenAI(api_key=OPENAI_API_KEY)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def send_telegram_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = data.get("message")
    if not message:
        return jsonify({"ok": True})

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_message = message.get("text")

    if message.get("from", {}).get("is_bot"):
        return jsonify({"ok": True})

    if not user_message:
        return jsonify({"ok": True})

    thread_id = str(user_id)  # Используем user_id в качестве thread_id

    try:
        # Формируем список сообщений для передачи (историю можно сохранять отдельно)
        # Здесь отправляем только последнее сообщение пользователя
        response = openai.responses.create(
            assistant=ASSISTANT_ID,
            thread=thread_id,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        # Ответ ассистента в формате: response["message"]["content"]["parts"]
        assistant_reply = None
        if response and "message" in response and "content" in response["message"]:
            parts = response["message"]["content"].get("parts")
            if parts and len(parts) > 0:
                assistant_reply = parts[0]

        if assistant_reply:
            send_telegram_message(chat_id, assistant_reply)
        else:
            send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    except Exception as e:
        # Логируем ошибку, отправляем уведомление
        print(f"OpenAI API error: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
