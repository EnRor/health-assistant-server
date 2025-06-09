import os
import json
import time
import threading
from datetime import datetime, timedelta

import openai
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# Храним данные пользователей в памяти
user_threads = {}
user_reminders = {}

def send_telegram_message(chat_id, text):
    try:
        payload = {"chat_id": chat_id, "text": text}
        response = requests.post(TELEGRAM_API_URL, json=payload)
        print("[send_telegram_message]", response.status_code, response.text)
    except Exception as e:
        print(f"[send_telegram_message] Error: {e}")

def schedule_reminder(chat_id, delay_seconds, reminder_text):
    def reminder_job():
        time.sleep(delay_seconds)
        send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")
    threading.Thread(target=reminder_job).start()

@app.route("/", methods=["GET"])
def root():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("[webhook] Incoming:", json.dumps(data))

        if "message" not in data or "text" not in data["message"]:
            return jsonify({"ok": True})

        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"]

        # Получаем или создаём thread для пользователя
        if chat_id not in user_threads:
            thread = openai.beta.threads.create()
            user_threads[chat_id] = thread.id
        thread_id = user_threads[chat_id]

        # Проверяем: нет ли активного run
        existing_runs = openai.beta.threads.runs.list(thread_id=thread_id, limit=1)
        if existing_runs.data and existing_runs.data[0].status in ["queued", "in_progress"]:
            send_telegram_message(chat_id, "⚠️ Пожалуйста, подождите, я ещё обрабатываю предыдущий запрос.")
            return jsonify({"ok": True})

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

        # Ожидаем завершения run
        while True:
            run_status = openai.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            if run_status.status == "completed":
                break
            elif run_status.status == "requires_action":
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                outputs = []

                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)

                    if function_name == "set_reminder":
                        delay_minutes = arguments.get("delay_minutes", 1)
                        reminder_text = arguments.get("reminder_text", "Напоминание")

                        schedule_reminder(chat_id, delay_minutes * 60, reminder_text)

                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": f"Напоминание установлено через {delay_minutes} минут."
                        })

                openai.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=outputs
                )
                continue
            elif run_status.status in ["failed", "cancelled", "expired"]:
                send_telegram_message(chat_id, "❌ Ошибка выполнения запроса.")
                return jsonify({"ok": True})

            time.sleep(1)

        # Получаем финальное сообщение от ассистента
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in reversed(messages.data):
            if msg.role == "assistant":
                response_text = msg.content[0].text.value
                send_telegram_message(chat_id, response_text)
                break

    except Exception as e:
        print("❌ Общая ошибка:", e)
        send_telegram_message(chat_id, "❌ Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})
