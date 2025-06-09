import os
import time
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

openai = OpenAI(api_key=OPENAI_API_KEY)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# В Responses API нет необходимости хранить thread_id отдельно, используем user_id
def get_thread_id(user_id: int) -> str:
    # Можно дополнительно реализовать свою логику генерации thread_id
    return str(user_id)

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

    # Игнорируем сообщения от ботов, чтобы не зациклиться
    if message.get("from", {}).get("is_bot"):
        return jsonify({"ok": True})

    if not user_message:
        return jsonify({"ok": True})

    thread_id = get_thread_id(user_id)

    # Отправляем сообщение пользователя в Responses API
    openai.responses.message.create(
        assistant=ASSISTANT_ID,
        thread=thread_id,
        content={
            "content_type": "text",
            "parts": [user_message]
        },
        role="user"
    )

    # Запускаем ассистента
    run = openai.responses.run.create(
        assistant=ASSISTANT_ID,
        thread=thread_id
    )

    # Ожидаем завершения run (polling)
    while True:
        run_status = openai.responses.run.retrieve(
            run_id=run["id"]
        )
        if run_status["status"] == "completed":
            break
        time.sleep(0.5)

    # Получаем все сообщения в треде
    messages = openai.responses.message.list(
        assistant=ASSISTANT_ID,
        thread=thread_id
    )

    # Ищем последнее сообщение от ассистента
    assistant_reply = None
    for msg in reversed(messages["data"]):
        if msg["role"] == "assistant":
            assistant_reply = msg["content"]["parts"][0]

            # Обработка function_call (если есть)
            if "function_call" in msg:
                # Здесь можно добавить логику вызова функций
                pass

            break

    if assistant_reply:
        send_telegram_message(chat_id, assistant_reply)
    else:
        send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
