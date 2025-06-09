import os
import time
import openai
from flask import Flask, request
import requests

# Настройки
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID")

openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Получение/создание Thread ID для каждого пользователя
user_threads = {}  # В реальной среде используйте базу данных

def get_thread_id(user_id):
    if user_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[user_id] = thread.id
    return user_threads[user_id]

# Отправка сообщения в Telegram
def send_telegram_message(chat_id, text):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

# Обработка запроса Telegram
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

        # Отправка сообщения в Thread
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

        # Ожидание завершения выполнения
        while True:
            run_status = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == "completed":
                break
            time.sleep(1)  # пауза для предотвращения чрезмерного опроса

        # Получение всех сообщений и извлечение последнего ответа ассистента
        messages = openai.beta.threads.messages.list(thread_id=thread_id)

        assistant_messages = [
            msg for msg in messages.data if msg.role == "assistant"
        ]

        if assistant_messages:
            latest_message = assistant_messages[0]  # первое = самое новое
            text_parts = [
                block.text.value for block in latest_message.content if block.type == "text"
            ]
            final_text = "\n".join(text_parts).strip()
            if final_text:
                send_telegram_message(chat_id, final_text)
            else:
                send_telegram_message(chat_id, "⚠️ Ассистент не вернул текстовый ответ.")
        else:
            send_telegram_message(chat_id, "⚠️ Не удалось получить ответ от ассистента.")

    return {"ok": True}

# Точка входа
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
