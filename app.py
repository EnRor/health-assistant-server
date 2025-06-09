import os
import openai
from flask import Flask, request
import requests
import time

# Настройки окружения
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID")

# Установка API-ключа
openai.api_key = OPENAI_API_KEY

# Инициализация Flask
app = Flask(__name__)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Хранилище потоков пользователей (можно заменить на БД)
user_threads = {}

def get_thread_id(user_id):
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
    return user_threads[user_id]

def send_telegram_message(chat_id, text):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

def handle_function_call(function_call, chat_id):
    name = function_call.get("name")
    arguments = function_call.get("arguments")

    if name == "set_reminder":
        reminder_text = arguments.get("reminder_text")
        reminder_time = arguments.get("reminder_time")

        send_telegram_message(chat_id, f"Напоминание установлено: '{reminder_text}' через {reminder_time}")
        # Здесь можно добавить логику планирования напоминания (например, APScheduler)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = data.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_message = message.get("text")

    if user_message:
        thread_id = get_thread_id(user_id)

        # Отправка пользовательского сообщения в Thread
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Запуск ассистента
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Ожидание завершения run
        while True:
            run_status = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == "completed":
                break
            time.sleep(1)

        # Получение сообщений
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in reversed(messages.data):
            if msg.role == "assistant":
                if msg.content:
                    response_text = msg.content[0].text.value
                    send_telegram_message(chat_id, response_text)
                if msg.function_call:
                    handle_function_call(msg.function_call, chat_id)
                break

    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
