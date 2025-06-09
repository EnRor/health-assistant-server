import os
import time
import requests
from flask import Flask, request, jsonify
import openai

app = Flask(__name__)

# Ваши переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

openai.api_key = OPENAI_API_KEY
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Хранилище thread_id для каждого пользователя
user_threads = {}

def get_thread_id(user_id):
    if user_id not in user_threads:
        # Создаём новый thread в Responses API
        response = openai.responses.threads.create(
            assistant=ASSISTANT_ID
        )
        user_threads[user_id] = response["id"]
    return user_threads[user_id]

def send_telegram_message(chat_id, text):
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

    # Игнорируем сообщения от бота (чтобы не зациклиться)
    if message.get("from", {}).get("is_bot"):
        return jsonify({"ok": True})

    if not user_message:
        return jsonify({"ok": True})

    thread_id = get_thread_id(user_id)

    # Отправляем сообщение пользователя в thread
    openai.responses.threads.message.create(
        thread_id=thread_id,
        role="user",
        content=user_message
    )

    # Запускаем ассистента на выполнение
    run = openai.responses.threads.run.create(
        thread_id=thread_id,
        assistant=ASSISTANT_ID
    )

    # Ждем завершения run (polling)
    while True:
        run_status = openai.responses.threads.run.retrieve(
            thread_id=thread_id,
            run_id=run["id"]
        )
        if run_status["status"] == "completed":
            break
        time.sleep(0.5)

    # Получаем все сообщения в треде
    messages = openai.responses.threads.message.list(thread_id=thread_id)

    # Ищем последнее сообщение от ассистента
    assistant_reply = None
    for msg in reversed(messages["data"]):
        if msg["role"] == "assistant":
            assistant_reply = msg["content"]["parts"][0]
            # Обработка function_call, если есть
            if "function_call" in msg:
                # Логика вызова функций (если требуется)
                pass
            break

    if assistant_reply:
        send_telegram_message(chat_id, assistant_reply)
    else:
        send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
