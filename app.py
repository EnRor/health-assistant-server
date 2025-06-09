import os
import json
import traceback
from datetime import datetime
from time import sleep

import requests
import dateparser
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from openai import OpenAI

app = Flask(__name__)

# Инициализация переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

openai = OpenAI(api_key=OPENAI_API_KEY)
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

scheduler = BackgroundScheduler()
scheduler.start()

# Память: user_id -> thread_id
memory = {}

def send_telegram_message(chat_id: int, text: str):
    print(f"[send_telegram_message] To {chat_id}: {text}", flush=True)
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

    if message.get("from", {}).get("is_bot") or not user_message:
        return jsonify({"ok": True})

    thread_id = memory.get(user_id)
    if not thread_id:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        memory[user_id] = thread_id

    try:
        # Добавляем сообщение пользователя в тред
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Запускаем ассистента
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Ожидание выполнения
        while True:
            run_status = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status in ["completed", "failed"]:
                break
            sleep(1)

        if run_status.status == "completed":
            messages = openai.beta.threads.messages.list(thread_id=thread_id)

            for msg in reversed(messages.data):
                if msg.role == "assistant":
                    parts = msg.content

                    for part in parts:
                        if part.type == "text":
                            send_telegram_message(chat_id, part.text.value)

                        elif part.type == "function_call":
                            if part.function_call.name == "set_reminder":
                                try:
                                    raw_args = part.function_call.arguments
                                    print("[set_reminder] Raw arguments:", raw_args, flush=True)

                                    # Попытка десериализации
                                    if isinstance(raw_args, str):
                                        params = json.loads(raw_args)
                                    else:
                                        params = raw_args  # fallback

                                    print("[set_reminder] Parsed params:", params, flush=True)

                                    reminder_text = params.get("reminder_text", "🔔 Напоминание")
                                    reminder_time_str = params.get("reminder_time")

                                    if not reminder_time_str:
                                        send_telegram_message(chat_id, "⚠️ Не указано время для напоминания.")
                                        continue

                                    reminder_datetime = dateparser.parse(
                                        reminder_time_str,
                                        settings={'RELATIVE_BASE': datetime.now(), 'PREFER_DATES_FROM': 'future'}
                                    )

                                    print(f"[set_reminder] Parsed datetime: {reminder_datetime}", flush=True)

                                    if not reminder_datetime:
                                        send_telegram_message(chat_id, f"⚠️ Не удалось распознать время из: '{reminder_time_str}'")
                                    else:
                                        delay_seconds = (reminder_datetime - datetime.now()).total_seconds()
                                        if delay_seconds <= 0:
                                            send_telegram_message(chat_id, "⚠️ Время напоминания должно быть в будущем.")
                                        else:
                                            scheduler.add_job(
                                                send_telegram_message,
                                                'date',
                                                run_date=reminder_datetime,
                                                args=[chat_id, f"🔔 Напоминание: {reminder_text}"]
                                            )
                                            send_telegram_message(chat_id, f"✅ Напоминание установлено на {reminder_datetime.strftime('%d.%m.%Y %H:%M')}")

                                except Exception as e:
                                    error_text = f"❌ Ошибка при установке напоминания: {str(e)}\n{traceback.format_exc()}"
                                    print(error_text, flush=True)
                                    send_telegram_message(chat_id, error_text)
                    break
        else:
            send_telegram_message(chat_id, "⚠️ Ассистент не смог обработать запрос.")

    except Exception as e:
        error_text = f"❌ Общая ошибка: {str(e)}\n{traceback.format_exc()}"
        print(error_text, flush=True)
        send_telegram_message(chat_id, "❌ Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
