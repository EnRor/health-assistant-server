# app.py

from flask import Flask, request
import openai, os, json, logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import requests
import re

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

memory_file = "memory.json"
scheduler = BackgroundScheduler()
scheduler.start()

logging.basicConfig(level=logging.INFO)

# === Память ===
def load_memory():
    try:
        with open(memory_file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_memory(memory):
    with open(memory_file, "w") as f:
        json.dump(memory, f)

memory = load_memory()

def get_user_memory(user_id):
    return memory.get(str(user_id), {"context": {}, "timezone_offset": None})

def update_user_memory(user_id, data):
    memory[str(user_id)] = data
    save_memory(memory)

# === Отправка сообщений ===
def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": chat_id, "text": text})
        logging.info(f"Ответ Telegram: {res.status_code} {res.text}")
    except Exception as e:
        logging.exception("Ошибка при отправке сообщения Telegram")

# === Обработка времени ===
def extract_minutes(text):
    match = re.search(r"через (\d+)\s*(минут|час)", text)
    if match:
        num = int(match.group(1))
        return num * 60 if "час" in match.group(2) else num
    return None

def extract_absolute_time(text):
    match = re.search(r"в\s*(\d{1,2}):(\d{2})", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        now = datetime.utcnow()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < now:
            target += timedelta(days=1)
        return target
    return None

def extract_message(text):
    match = re.search(r"(?:напомни.*?)(?:через|в).*?(?:\d+|\d{1,2}:\d{2})(.*)", text)
    return match.group(1).strip() if match else None

# === Планирование ===
def schedule_reminder(user_id, dt, message, tz_offset=None):
    try:
        scheduler.add_job(
            send_message,
            'date',
            run_date=dt,
            args=[user_id, f"⏰ Напоминание: {message}"],
            id=f"reminder_{user_id}_{dt.timestamp()}",
            misfire_grace_time=30
        )
        logging.info(f"Запланировано напоминание на {dt}")
    except Exception as e:
        logging.exception("Ошибка планирования напоминания")

# === Основной маршрут ===
@app.route("/", methods=["GET"])
def index():
    return "HealthMate бот работает."

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logging.info(f"Получен запрос: {data}")

        if "message" not in data or "text" not in data["message"]:
            return "ok"

        user_id = str(data["message"]["from"]["id"])
        text = data["message"]["text"].strip().lower()
        now_utc = datetime.utcnow()

        user_mem = get_user_memory(user_id)
        context = user_mem.get("context", {})
        tz_offset = user_mem.get("timezone_offset")

        reply = "Извините, я не понял запрос."

        if "/start" in text:
            reply = "Привет! Рада, что ты снова здесь. Как тебя зовут?"
        elif "меня зовут" in text:
            name = text.replace("меня зовут", "").strip().capitalize()
            context["name"] = name
            reply = f"Приятно познакомиться, {name}!"
        elif "как меня зовут" in text:
            name = context.get("name")
            reply = f"Вас зовут {name}!" if name else "Я пока не знаю, как вас зовут."
        elif "сейчас у меня" in text:
            time_str = text.replace("сейчас у меня", "").strip()
            try:
                user_time = datetime.strptime(time_str, "%H:%M")
                offset = (user_time.hour * 60 + user_time.minute) - (now_utc.hour * 60 + now_utc.minute)
                user_mem["timezone_offset"] = offset
                reply = f"Хорошо, учту ваш часовой пояс."
            except:
                reply = "Пожалуйста, укажите время в формате ЧЧ:ММ"
        elif "через" in text:
            mins = extract_minutes(text)
            if mins:
                reminder_time = now_utc + timedelta(minutes=mins)
                msg = extract_message(text) or "что-то важное"
                schedule_reminder(user_id, reminder_time, msg, tz_offset)
                reply = f"Напоминание установлено через {mins} минут — {msg}"
        elif "в" in text:
            abs_time = extract_absolute_time(text)
            if abs_time:
                reminder_time = abs_time - timedelta(minutes=user_mem.get("timezone_offset", 0) or 0)
                msg = extract_message(text) or "что-то важное"
                schedule_reminder(user_id, reminder_time, msg, tz_offset)
                reply = f"Напоминание установлено на {abs_time.strftime('%H:%M')} — {msg}"

        user_mem["context"] = context
        update_user_memory(user_id, user_mem)

        send_message(user_id, reply)
        return "ok"

    except Exception as e:
        logging.exception("Ошибка в webhook:")
        return "error", 500
