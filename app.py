import os
import json
from datetime import datetime
import dateparser
import requests
from flask import Flask, request, jsonify
from openai import OpenAI
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# Инициализация переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

openai = OpenAI(api_key=OPENAI_API_KEY)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# Инициализация APScheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Память в формате словаря: thread_id -> список сообщений
memory = {}

def send_telegram_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

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

    # Инициализация истории сообщений для пользователя
    if thread_id not in memory:
        memory[thread_id] = []

    # Добавляем сообщение пользователя в память
    memory[thread_id].append({"role": "user", "content": user_message})

    try:
        response = openai.responses.create(
            assistant=ASSISTANT_ID,
            thread=thread_id,
            messages=memory[thread_id]
        )

        response_message = response["message"]
        content = response_message["content"]["parts"][0] if "content" in response_message else None

        # Проверка на вызов функции
        if "function_call" in response_message:
            func_name = response_message["function_call"]["name"]
            if func_name == "set_reminder":
                params_raw = response_message["function_call"].get("parameters")
                if isinstance(params_raw, str):
                    params = json.loads(params_raw)
                else:
                    params = params_raw

                reminder_text = params.get("reminder_text")
                reminder_time_str = params.get("reminder_time")

                reminder_datetime = dateparser.parse(
                    reminder_time_str,
                    settings={'RELATIVE_BASE': datetime.now(), 'PREFER_DATES_FROM': 'future'}
                )

                if not reminder_datetime:
                    send_telegram_message(chat_id, "Не удалось распознать время напоминания. Пожалуйста, попробуйте еще раз.")
                else:
                    delay_seconds = (reminder_datetime - datetime.now()).total_seconds()
                    if delay_seconds <= 0:
                        send_telegram_message(chat_id, "Время напоминания должно быть в будущем.")
                    else:
                        # Планируем напоминание
                        scheduler.add_job(
                            send_telegram_message,
                            'date',
                            run_date=reminder_datetime,
                            args=[chat_id, f"Напоминание: {reminder_text}"]
                        )
                        send_telegram_message(chat_id, f"Напоминание установлено на {reminder_datetime.strftime('%d.%m.%Y %H:%M')}")

                # Добавляем ответ ассистента с информацией об установке напоминания
                memory[thread_id].append({"role": "assistant", "content": content})
                return jsonify({"ok": True})

        # Если функции не вызываются, просто отправляем ответ ассистента
        if content:
            send_telegram_message(chat_id, content)
            memory[thread_id].append({"role": "assistant", "content": content})
        else:
            send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    except Exception as e:
        print(f"OpenAI API error: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
