# app.py
from flask import Flask, request, jsonify
import openai
import os
from dotenv import load_dotenv
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import json

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Memory file
MEMORY_FILE = "memory.json"
REMINDERS_FILE = "reminders.json"

# Ensure memory persistence
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {}

def save_memory(memory):
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f)

memory = load_memory()

# Send message to Telegram
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# Schedule reminders
def schedule_reminder(chat_id, message, run_time):
    scheduler.add_job(
        func=send_telegram_message,
        trigger='date',
        run_date=run_time,
        args=[chat_id, message],
        id=f"{chat_id}-{run_time}-{message}"
    )
    persist_reminder(chat_id, message, run_time)

# Save reminders for recovery
def persist_reminder(chat_id, message, run_time):
    reminders = []
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r") as f:
            reminders = json.load(f)
    reminders.append({"chat_id": chat_id, "message": message, "run_time": run_time.isoformat()})
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f)

# Reload reminders
@app.before_first_request
def restore_reminders():
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r") as f:
            reminders = json.load(f)
            for r in reminders:
                run_time = datetime.fromisoformat(r["run_time"])
                if run_time > datetime.now():
                    schedule_reminder(r["chat_id"], r["message"], run_time)

@app.route("/ping")
def ping():
    return jsonify({"status": "alive"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id"))
    user_input = message.get("text")

    if not user_input:
        return jsonify({"error": "No input"}), 400

    if user_input == "/start":
        reply = "Здравствуйте! Я ваш персональный ассистент по здоровью, спорту и питанию. Представьтесь, пожалуйста."
        send_telegram_message(chat_id, reply)
        return jsonify({"status": "started"})

    if chat_id not in memory:
        memory[chat_id] = []

    memory[chat_id].append({"role": "user", "content": user_input})
    save_memory(memory)

    # Assistant API interaction
    try:
        thread = openai.beta.threads.create()
        for msg in memory[chat_id]:
            openai.beta.threads.messages.create(
                thread_id=thread.id,
                role=msg["role"],
                content=msg["content"]
            )

        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        import time
        while True:
            status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        assistant_reply = messages.data[0].content[0].text.value

        memory[chat_id].append({"role": "assistant", "content": assistant_reply})
        save_memory(memory)

        # Parse reminders (simplified detection)
        import re
        match = re.search(r"напомни.*в (\d{1,2}:\d{2})", user_input.lower())
        if match:
            time_str = match.group(1)
            reminder_time = datetime.strptime(time_str, "%H:%M").replace(
                year=datetime.now().year,
                month=datetime.now().month,
                day=datetime.now().day
            )
            if reminder_time < datetime.now():
                reminder_time += timedelta(days=1)
            schedule_reminder(chat_id, "Напоминаю: " + user_input, reminder_time)

        send_telegram_message(chat_id, assistant_reply)
        return jsonify({"status": "success"})

    except Exception as e:
        send_telegram_message(chat_id, "Произошла ошибка: " + str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
