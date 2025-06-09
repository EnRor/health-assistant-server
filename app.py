from flask import Flask, request
import os
import requests
import openai

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID")

openai.api_key = OPENAI_API_KEY

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

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

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = data.get("message")

    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_message = message.get("text")

    # Игнорируем сообщения от самого бота, чтобы избежать цикла
    if message.get("from", {}).get("is_bot"):
        return {"ok": True}

    if user_message:
        thread_id = get_thread_id(user_id)

        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Ожидаем завершения
        while True:
            run_status = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == "completed":
                break

        messages = openai.beta.threads.messages.list(thread_id=thread_id)

        # Ищем последнее сообщение ассистента
        for msg in reversed(messages.data):
            if msg.role == "assistant":
                # Безопасная проверка function_call
                func_call = getattr(msg, "function_call", None)
                if func_call:
                    # Логика обработки function_call здесь (если нужно)
                    pass
                send_telegram_message(chat_id, msg.content[0].text.value)
                break

    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
