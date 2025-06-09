import os
import json
from datetime import datetime
import dateparser
import requests
import traceback
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
    # Обрезаем длинные сообщения, чтобы не превышать лимит Telegram (4096 символов)
    if len(text) > 4000:
        text = text[:4000] + "\n\n[Сообщение обрезано]"
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

    # Логируем входящие данные
    print(f"Thread ID: {thread_id}")
    print(f"User message: {user_message}")
    print(f"Memory length: {len(memory[thread_id])}")

    try:
        response = openai.responses.create(
            assistant=ASSISTANT_ID,
            thread=thread_id,
            messages=memory[thread_id]
        )
        response_message = response["message"]
        print(f"Response message keys: {response_message.keys()}")

        content = response_message.get("content", {}).get("parts", [None])[0]

        if "function_call" in response_message:
            func_name = response_message["function_call"]["name"]
            if func_name == "set_reminder":
                params_raw = response_message["function_call"].get("parameters")
                if isinstance(params_raw, str):
                    try:
                        params = json.loads(params_raw)
                    except json.JSONDecodeError:
                        send_telegram_message(chat_id, "Не удалось распарсить параметры функции.")
                        return jsonify({"ok": True})
                else:
                    params = params_raw

                reminder_text = params.get("reminder_text")
                reminder_time_str = params.get("reminder_time")

                print(f"Получено время напоминания: {reminder_time_str}")
                reminder_datetime = dateparser.parse(
                    reminder_time_str,
                    settings={'RELATIVE_BASE': datetime.now(), 'PREFER_DATES_FROM': 'future'}
                )
                print(f"Распознанное время: {reminder_datetime}")

                if not reminder_datetime:
                    send_telegram_message(chat_id, "Не удалось распознать время напоминания. Пожалуйста, попробуйте еще раз.")
                else:
                    delay_seconds = (reminder_datetime - datetime.now()).total_seconds()
                    if delay_seconds <= 0:
                        send_telegram_message(chat_id, "Время напоминания должно быть в будущем.")
                    else:
                        scheduler.add_job(
                            send_telegram_message,
                            'date',
                            run_date=reminder_datetime,
                            args=[chat_id, f"Напоминание: {reminder_text}"]
                        )
                        send_telegram_message(chat_id, f"Напоминание установлено на {reminder_datetime.strftime('%d.%m.%Y %H:%M')}")

                memory[thread_id].append({"role": "assistant", "content": content})
                return jsonify({"ok": True})

        if content:
            send_telegram_message(chat_id, content)
            memory[thread_id].append({"role": "assistant", "content": content})
        else:
            send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    except Exception as e:
        error_text = f"Ошибка в обработке запроса: {str(e)}\n{traceback.format_exc()}"
        print(error_text)
        send_telegram_message(chat_id, f"Ошибка при вызове ассистента:\n{str(e)}")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
