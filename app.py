import os
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
from openai.types.beta.threads import Run

app = Flask(__name__)

# Переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# Инициализация OpenAI клиента
openai = OpenAI(api_key=OPENAI_API_KEY)

# Telegram API URL
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Память: соответствие user_id -> thread_id
user_threads = {}

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
    user_id = str(message["from"]["id"])
    user_message = message.get("text")

    if not user_message:
        return jsonify({"ok": True})

    # Получаем или создаём thread_id для пользователя
    thread_id = user_threads.get(user_id)
    if not thread_id:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        user_threads[user_id] = thread_id

    try:
        # Добавляем сообщение пользователя в тред
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Запускаем ассистента
        run: Run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Ожидаем завершения выполнения
        while run.status in ["queued", "in_progress"]:
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

        # Получаем последнее сообщение от ассистента, связанное с текущим run
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_reply = None
        for msg in messages.data:
            if msg.run_id == run.id and msg.role == "assistant":
                assistant_reply = msg.content[0].text.value
                break

        # Отправляем ответ в Telegram
        if assistant_reply:
            send_telegram_message(chat_id, assistant_reply)
        else:
            send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    except Exception as e:
        print(f"OpenAI API error: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def root():
    return "Assistant is running", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
