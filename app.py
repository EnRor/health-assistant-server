import os
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from openai import OpenAI
import requests
import dateparser
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

openai = OpenAI(api_key=OPENAI_API_KEY)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

scheduler = BackgroundScheduler()
scheduler.start()

def send_telegram_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

def parse_reminder_time(reminder_time_str: str, run_time: datetime) -> datetime:
    """
    Парсит строку с временем напоминания.
    Поддерживает абсолютное время (например, 'сегодня в 15:00', 'завтра 10:30')
    и относительное ('10 минут', '1 час', '30 секунд').
    Возвращает datetime объекта UTC.
    """
    # Попытка распарсить как абсолютное время
    dt = dateparser.parse(reminder_time_str, settings={'RELATIVE_BASE': run_time, 'RETURN_AS_TIMEZONE_AWARE': False})
    if dt:
        return dt

    # Если не удалось распарсить, пробуем как относительное время (через regex)
    pattern = r"(\d+)\s*(секунд|сек|минут|мин|час|часов|ч)"
    match = re.search(pattern, reminder_time_str.lower())
    if match:
        value, unit = match.groups()
        value = int(value)
        if unit.startswith("сек"):
            delta = timedelta(seconds=value)
        elif unit.startswith("мин"):
            delta = timedelta(minutes=value)
        elif unit.startswith("час"):
            delta = timedelta(hours=value)
        else:
            delta = timedelta(minutes=10)  # дефолт
        return run_time + delta

    # Если всё плохо, ставим дефолт через 10 минут
    return run_time + timedelta(minutes=10)


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = data.get("message")
    if not message:
        return jsonify({"ok": True})

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_message = message.get("text")

    if message.get("from", {}).get("is_bot"):
        return jsonify({"ok": True})

    if not user_message:
        return jsonify({"ok": True})

    thread_id = str(user_id)

    try:
        response = openai.responses.create(
            assistant=ASSISTANT_ID,
            thread=thread_id,
            messages=[{"role": "user", "content": user_message}],
            tools=["set_reminder"],  # включаем функцию ассистента
        )

        # Если ассистент вызвал функцию set_reminder
        if "tool_calls" in response and response["tool_calls"]:
            for tool_call in response["tool_calls"]:
                if tool_call["tool"] == "set_reminder":
                    params = tool_call.get("parameters", {})
                    reminder_text = params.get("reminder_text")
                    reminder_time_str = params.get("reminder_time")

                    run_created_at = response.get("run", {}).get("created_at", None)
                    if run_created_at:
                        run_time = datetime.utcfromtimestamp(run_created_at)
                    else:
                        run_time = datetime.utcnow()

                    reminder_datetime = parse_reminder_time(reminder_time_str, run_time)

                    # Запланировать напоминание в указанное время
                    scheduler.add_job(
                        send_telegram_message,
                        trigger="date",
                        run_date=reminder_datetime,
                        args=[chat_id, f"🔔 Напоминание: {reminder_text}"],
                    )

                    send_telegram_message(chat_id,
                        f"Напоминание установлено на {reminder_datetime.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        else:
            # Стандартный ответ ассистента
            parts = response["message"]["content"].get("parts")
            if parts and len(parts) > 0:
                assistant_reply = parts[0]
                send_telegram_message(chat_id, assistant_reply)
            else:
                send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    except Exception as e:
        print(f"OpenAI API error: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
