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

user_threads = {}

user_reminders = {}

def send_telegram_message(chat_id, text):

    # Отправка сообщения в Telegram

    try:

        payload = {"chat_id": chat_id, "text": text}

        response = requests.post(TELEGRAM_API_URL, json=payload)

        print("[send_telegram_message]", response.status_code, response.text)

    except Exception as e:

        print(f"[send_telegram_message] Error: {e}")

def schedule_reminder_delay(chat_id, delay_seconds, reminder_text):

    # Установка напоминания через заданное время

    def reminder_job():

        time.sleep(delay_seconds)

        send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")

    threading.Thread(target=reminder_job).start()

def schedule_reminder_time(chat_id, reminder_time_absolute, reminder_text, user_local_time):

  # Установка напоминания на конкретное время

    try:

        current_time = datetime.now()

        reminder_datetime = datetime.strptime(reminder_time_absolute, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day)

        if reminder_datetime < current_time:

            reminder_datetime += timedelta(days=1)

        delay_seconds = (reminder_datetime - current_time).total_seconds()

        def reminder_job():

            time.sleep(delay_seconds)

            send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")

        threading.Thread(target=reminder_job).start()

    except ValueError as e:

      send_telegram_message(chat_id, f"❌ Некорректный формат времени. Используйте HH:MM. Ошибка: {e}")

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

        if chat_id not in user_threads:

            thread = openai.beta.threads.create()

            user_threads[chat_id] = thread.id

        thread_id = user_threads[chat_id]

        existing_runs = openai.beta.threads.runs.list(thread_id=thread_id, limit=1)

        if existing_runs.data and existing_runs.data[0].status in ["queued", "in_progress"]:

            send_telegram_message(chat_id, "⚠️ Пожалуйста, подождите, я ещё обрабатываю предыдущий запрос.")

            return jsonify({"ok": True})

        openai.beta.threads.messages.create(

            thread_id=thread_id,

            role="user",

            content=user_message

        )

        run = openai.beta.threads.runs.create(

            thread_id=thread_id,

            assistant_id=ASSISTANT_ID

        )

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

                    if function_name == "set_reminder_delay":

                        delay_minutes = arguments.get("delay_minutes")

                        reminder_text = arguments.get("reminder_text")

                        schedule_reminder_delay(chat_id, delay_minutes * 60, reminder_text)

                        outputs.append({

                            "tool_call_id": tool_call.id,

                            "output": f"Напоминание установлено через {delay_minutes} минут."

                        })

                    elif function_name == "set_reminder_time":

                        reminder_text = arguments.get("reminder_text")

                        reminder_time_absolute = arguments.get("reminder_time_absolute")

                        user_local_time = arguments.get("user_local_time")

                        schedule_reminder_time(chat_id, reminder_time_absolute, reminder_text, user_local_time)

                        outputs.append({

                            "tool_call_id": tool_call.id,

                            "output": f"Напоминание установлено на {reminder_time_absolute}."

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

        messages = openai.beta.threads.messages.list(thread_id=thread_id)

        assistant_messages = [

            msg for msg in messages.data if msg.role == "assistant"

        ]

        if assistant_messages:

            latest_message = assistant_messages[0]

            text_parts = [

                block.text.value for block in latest_message.content if block.type == "text"

            ]

            final_text = "\n".join(text_parts).strip()

            if final_text:

                send_telegram_message(chat_id, final_text)

            else:

                send_telegram_message(chat_id, "⚠️ Ассистент не вернул текстовый ответ.")

        else:

            send_telegram_message(chat_id, "⚠️ Не удалось получить ответ от ассистента.")

    except Exception as e:

        print("❌ Общая ошибка:", e)

        send_telegram_message(chat_id, "❌ Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)

