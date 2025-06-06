from flask import Flask, request
import openai, json, os, logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import requests

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

memory_file = "memory.json"
scheduler = BackgroundScheduler()
scheduler.start()

logging.basicConfig(level=logging.INFO)

def load_memory():
    try:
        with open(memory_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
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

@app.route("/", methods=["GET"])
def index():
    return "HealthMate бот работает."

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
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
                user_dt = now_utc.replace(hour=user_time.hour, minute=user_time.minute, second=0, microsecond=0)
                if user_dt < now_utc:
                    user_dt += timedelta(days=1)
                offset = int((user_dt - now_utc).total_seconds() // 60)
                user_mem["timezone_offset"] = offset
                reply = f"Поняла, часовой пояс учтён. Смещение: {offset} мин."
            except:
                reply = "Пожалуйста, укажите текущее время в формате ЧЧ:ММ"

        elif "через" in text:
            mins = extract_minutes(text)
            if mins:
                reminder_time = now_utc + timedelta(minutes=mins)
                msg = extract_message(text) or "что-то важное"
                schedule_reminder(user_id, reminder_time, msg)
                reply = f"Напоминание установлено через {mins} минут — {msg}"

        elif "в" in text:
            abs_time = extract_absolute_time(text)
            if abs_time:
                offset = tz_offset or 0
                reminder_time = abs_time - timedelta(minutes=offset)
                msg = extract_message(text) or "что-то важное"
                schedule_reminder(user_id, reminder_time, msg)
                reply = f"Напоминание установлено на {abs_time.strftime('%H:%M')} — {msg}"

        user_mem["context"] = context
        update_user_memory(user_id, user_mem)

        send_message(user_id, reply)
        return "ok"

    except Exception as e:
        logging.exception("Ошибка в webhook:")
        return "error", 500

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text})
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения: {e}")

def extract_minutes(text):
    import re
    match = re.search(r"через (\d+)\s*(минут|час|часа|часов)?", text)
    if match:
        num = int(match.group(1))
        return num * 60 if match.group(2) and "час" in match.group(2) else num
    return None

def extract_absolute_time(text):
    import re
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
    import re
    match = re.search(r"(?:напомни.*?)(?:через|в).*?(?:\d+|\d{1,2}:\d{2})(.*)", text)
    return match.group(1).strip() if match else None

def schedule_reminder(user_id, dt, message):
    scheduler.add_job(
        send_message,
        'date',
        run_date=dt,
        args=[user_id, f"⏰ Напоминание: {message}"],
        id=f"reminder_{user_id}_{int(dt.timestamp())}",
        misfire_grace_time=30,
        replace_existing=True
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
