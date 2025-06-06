from flask import Flask, request, jsonify
import openai
import os
import requests
import json
import re
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

MEMORY_FILE = "memory.json"

if not os.path.exists(MEMORY_FILE):
    with open(MEMORY_FILE, "w") as f:
        json.dump({}, f)

def load_memory():
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f)

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def schedule_reminder(chat_id, text, remind_time):
    scheduler.add_job(
        func=send_telegram_message,
        trigger='date',
        run_date=remind_time,
        args=[chat_id, f"⏰ Напоминание: {text}"],
        id=f"reminder-{chat_id}-{int(time.time())}"
    )

def parse_reminder(text):
    match_relative = re.search(r"через (\d+) (минут[уы]?|час[аов]?)", text)
    match_absolute = re.search(r"в (\d{1,2}):(\d{2})", text)
    task_match = re.search(r"напомни(?:ть)? (.*?) (?:через|в)", text)
    task = task_match.group(1) if task_match else "что-то важное"

    now = datetime.now()
    if match_relative:
        qty = int(match_relative.group(1))
        unit = match_relative.group(2)
        if "мин" in unit:
            return now + timedelta(minutes=qty), task
        elif "час" in unit:
            return now + timedelta(hours=qty), task
    elif match_absolute:
        hour = int(match_absolute.group(1))
        minute = int(match_absolute.group(2))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return target, task
    return None, None

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    chat_id = str(message.get("chat", {}).get("id"))
    user_input = message.get("text")

    if not user_input:
        return jsonify({"error": "No user input"}), 400

    memory = load_memory()
    user_data = memory.get(chat_id, {})

    # Обработка напоминаний
    if "напомни" in user_input.lower():
        remind_time, task = parse_reminder(user_input)
        if remind_time:
            schedule_reminder(chat_id, task, remind_time)
            send_telegram_message(chat_id, f"Напоминание установлено на {remind_time.strftime('%H:%M')} — {task}.")
            return jsonify({"status": "reminder set"}), 200
        else:
            send_telegram_message(chat_id, "Не удалось распознать время напоминания. Попробуйте, например: 'напомни через 5 минут' или 'в 15:30'")
            return jsonify({"status": "reminder failed"}), 200

    # Сохраняем имя, если представились
    if re.match(r"меня зовут (.+)", user_input.lower()):
        name = re.match(r"меня зовут (.+)", user_input.lower()).group(1).strip().capitalize()
        user_data["name"] = name
        memory[chat_id] = user_data
        save_memory(memory)
        send_telegram_message(chat_id, f"Приятно познакомиться, {name}!")
        return jsonify({"status": "name saved"}), 200

    # Ответ на вопрос "Как меня зовут"
    if "как меня зовут" in user_input.lower():
        name = user_data.get("name")
        if name:
            send_telegram_message(chat_id, f"Вас зовут {name}!")
        else:
            send_telegram_message(chat_id, f"Я пока не знаю, как вас зовут. Представьтесь фразой 'меня зовут ...'")
        return jsonify({"status": "name recall"}), 200

    # Получение/создание thread_id
    thread_id = user_data.get("thread_id")
    if not thread_id:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        user_data["thread_id"] = thread_id
        memory[chat_id] = user_data
        save_memory(memory)

    try:
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
        import traceback
        error_text = f"⚠️ Ошибка:\n{str(e)}\n\nТрассировка:\n{traceback.format_exc()}"
        send_telegram_message(chat_id, error_text[:4000])  # Telegram ограничен 4096 символами
        return jsonify({"error": str(e)}), 500


@app.route('/', methods=['GET'])
def home():
    return "Health Assistant is running."

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
