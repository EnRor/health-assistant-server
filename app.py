from flask import Flask, request, jsonify
import openai
import os
import requests
import time
import json
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Постоянная память между сессиями
THREADS_FILE = "threads.json"
if os.path.exists(THREADS_FILE):
    with open(THREADS_FILE, "r") as f:
        session_threads = json.load(f)
else:
    session_threads = {}

# Сохранение в файл при изменении
def save_threads():
    with open(THREADS_FILE, "w") as f:
        json.dump(session_threads, f)


def send_telegram_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)


def set_webhook():
    webhook_url = os.getenv("RENDER_EXTERNAL_URL") + "/webhook"
    requests.get(f"{BASE_URL}/setWebhook?url={webhook_url}")


def schedule_reminder(chat_id, text, run_time):
    scheduler.add_job(send_telegram_message, 'date', run_date=run_time, args=[chat_id, text])


def parse_reminder_time(text):
    try:
        if "через" in text:
            parts = text.split("через")
            minutes = int(parts[1].split("минут")[0].strip())
            return datetime.now() + timedelta(minutes=minutes)
        elif "в" in text:
            parts = text.split("в")
            time_part = parts[1].strip()
            target_time = datetime.strptime(time_part, "%H:%M").time()
            now = datetime.now()
            reminder_dt = datetime.combine(now.date(), target_time)
            if reminder_dt < now:
                reminder_dt += timedelta(days=1)
            return reminder_dt
    except Exception as e:
        print(f"[ERROR parsing time] {e}")
    return None


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id"))
    user_input = message.get("text", "")

    if user_input.startswith("/start"):
        welcome_text = (
            "Привет! Я — твой персональный ассистент по здоровью, спорту и питанию.\n"
            "Я могу давать советы, отвечать на вопросы и даже напоминать тебе о важных действиях!"
        )
        send_telegram_message(chat_id, welcome_text)
        return jsonify({"status": "started"}), 200

    try:
        # Напоминания
        if "напомни" in user_input.lower():
            run_time = parse_reminder_time(user_input.lower())
            if run_time:
                text = "Напоминаю: " + user_input
                schedule_reminder(chat_id, text, run_time)
                send_telegram_message(chat_id, f"Хорошо, напомню {run_time.strftime('%H:%M')}.")
            else:
                send_telegram_message(chat_id, "Не смог разобрать время. Попробуй 'через 15 минут' или 'в 14:30'")
            return jsonify({"status": "reminder set"}), 200

        thread_id = session_threads.get(chat_id)
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            session_threads[chat_id] = thread_id
            save_threads()

        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_input
        )

        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        while True:
            status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_reply = messages.data[0].content[0].text.value
        send_telegram_message(chat_id, assistant_reply)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        send_telegram_message(chat_id, "Произошла ошибка при обработке запроса.")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
