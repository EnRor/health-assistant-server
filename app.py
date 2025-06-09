import os
import time
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
from openai.types.beta.threads import Run

app = Flask(__name__)

# Переменные окружения
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

    if not message or message.get("from", {}).get("is_bot"):
        return jsonify({"ok": True})

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_message = message.get("text")

    if not user_message:
        return jsonify({"ok": True})

    try:
        # Используем user_id в качестве thread_id
        thread = openai.beta.threads.create()

        # Добавляем сообщение в thread
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        # Запускаем ассистента
        run: Run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Ожидаем завершения run
        while True:
            run = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run.status == "completed":
                break
            elif run.status in ["failed", "cancelled", "expired"]:
                send_telegram_message(chat_id, "Ассистент не смог завершить обработку запроса.")
                return jsonify({"ok": True})
            time.sleep(1)

        # Получаем ответ
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        assistant_reply = None

        for msg in reversed(messages.data):
            if msg.role == "assistant":
                assistant_reply = msg.content[0].text.value
                break

        if assistant_reply:
            send_telegram_message(chat_id, assistant_reply)
        else:
            send_telegram_message(chat_id, "Ассистент не дал ответа.")
    except Exception as e:
        print(f"Ошибка OpenAI: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})


@app.route("/", methods=["GET"])
def index():
    return "Ассистент работает.", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
