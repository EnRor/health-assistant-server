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
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

user_threads = {}
user_reminders = {}


def send_telegram_message(chat_id, text):
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        response = requests.post(TELEGRAM_API_URL, json=payload)
        print("[send_telegram_message]", response.status_code, response.text)
    except Exception as e:
        print(f"[send_telegram_message] Error: {e}")

def send_telegram_menu(chat_id):
    keyboard = [
        [{"text": "📋 Память", "callback_data": "memory_view"}],
        [{"text": "🗑 Очистить память", "callback_data": "memory_clear"}],
        [{"text": "🏋️‍♀ План тренировок", "callback_data": "training_plan"}],
        [{"text": "🗓 Мои напоминания", "callback_data": "reminders_list"}]
    ]
    payload = {
        "chat_id": chat_id,
        "text": "📍 Главное меню:",
        "reply_markup": {"inline_keyboard": keyboard}
    }
    response = requests.post(TELEGRAM_API_URL, json=payload)
    print("[send_telegram_menu]", response.status_code, response.text)

def schedule_reminder_delay(chat_id, delay_seconds, reminder_text):
    def reminder_job():
        time.sleep(delay_seconds)
        send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")
    threading.Thread(target=reminder_job).start()


def schedule_reminder_time(chat_id, reminder_time_absolute, reminder_text, user_local_time):
    try:
        user_now = datetime.strptime(user_local_time, "%H:%M").replace(year=2000, month=1, day=1)
        reminder_time = datetime.strptime(reminder_time_absolute, "%H:%M").replace(year=2000, month=1, day=1)
        delta = (reminder_time - user_now).total_seconds()
        if delta < 0:
            delta += 24 * 3600
        server_now = datetime.now()
        reminder_datetime_server = server_now + timedelta(seconds=delta)
        delay_seconds = (reminder_datetime_server - server_now).total_seconds()

        def reminder_job():
            time.sleep(delay_seconds)
            send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")

        threading.Thread(target=reminder_job).start()
    except ValueError as e:
        send_telegram_message(chat_id, f"❌ Некорректный формат времени. Используйте HH:MM. Ошибка: {e}")


def google_search(query):
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": GOOGLE_API_KEY,
            "cx": GOOGLE_CSE_ID,
            "q": query,
            "num": 3
        }
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()
        items = results.get("items", [])
        if not items:
            return "⚠️ По вашему запросу ничего не найдено."
        reply_lines = []
        for item in items:
            title = item.get("title")
            link = item.get("link")
            snippet = item.get("snippet")
            reply_lines.append(f"*{title}*\n{snippet}\n{link}")
        return "\n\n".join(reply_lines)
    except Exception as e:
        print(f"[google_search] Error: {e}")
        return "❌ Ошибка при поиске."


@app.route("/", methods=["GET"])
def root():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("[webhook] Incoming:", json.dumps(data))

        # Обработка callback-кнопок
        if "callback_query" in data:
            callback = data["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data_key = callback["data"]

            if data_key == "memory_view":
                memory = user_threads.get(chat_id, [])
                if memory:
                    send_telegram_message(chat_id, "🧠 В памяти ассистента:\n" + "\n".join(memory))
                else:
                    send_telegram_message(chat_id, "🧠 Память пуста.")

            elif data_key == "memory_clear":
                user_threads.pop(chat_id, None)
                send_telegram_message(chat_id, "🚮 Память очищена.")

            elif data_key == "training_plan":
                send_telegram_message(chat_id, "🏋️‍♀ План тренировок:\n1. Разминка\n2. Силовая\n3. Кардио")

            elif data_key == "reminders_list":
                reminders = user_reminders.get(chat_id, [])
                if reminders:
                    send_telegram_message(chat_id, "🗓 Ваши напоминания:\n" + "\n".join(reminders))
                else:
                    send_telegram_message(chat_id, "🗓 Напоминаний нет.")

            return jsonify({"ok": True})

        # Проверка наличия текста в сообщении
        if "message" not in data or "text" not in data["message"]:
            return jsonify({"ok": True})

        chat_id = data["message"]["chat"]["id"]
        user_message = data["message"]["text"].strip()

        # Меню
        if user_message.lower() == "/menu":
            send_telegram_menu(chat_id)
            return jsonify({"ok": True})

        # Простой поиск
        if user_message.lower().startswith("/search"):
            query = user_message[len("/search"):].strip()
            if not query:
                send_telegram_message(chat_id, "Пожалуйста, укажите запрос после команды /search")
                return jsonify({"ok": True})
            search_results = google_search(query)
            send_telegram_message(chat_id, search_results)
            return jsonify({"ok": True})

        # Установка простого напоминания через "через N минут"
        if "через" in user_message and "напомни" in user_message:
            try:
                parts = user_message.lower().split("через")
                minutes_part = parts[1].strip().split(" ")[0]
                reminder_text = " ".join(parts[1].strip().split(" ")[1:]) or "Напоминание"
                minutes = int(minutes_part)
                schedule_reminder_delay(chat_id, minutes * 60, reminder_text)
                send_telegram_message(chat_id, f"⏳ Напоминание установлено через {minutes} мин: {reminder_text}")
                return jsonify({"ok": True})
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Ошибка при установке напоминания: {e}")
                return jsonify({"ok": True})

        # Assistant API: память и контекст
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

                    elif function_name == "google_search":
                        query = arguments.get("query")
                        output_text = google_search(query) if query else "❌ Отсутствует параметр 'query'."
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": output_text
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
        assistant_messages = [msg for msg in messages.data if msg.role == "assistant"]

        if assistant_messages:
            latest_message = assistant_messages[0]
            text_parts = [block.text.value for block in latest_message.content if block.type == "text"]
            final_text = "\n".join(text_parts).strip()
            send_telegram_message(chat_id, final_text if final_text else "⚠️ Ассистент не вернул текстовый ответ.")
        else:
            send_telegram_message(chat_id, "⚠️ Не удалось получить ответ от ассистента.")

    except Exception as e:
        print("❌ Общая ошибка:", e)
        send_telegram_message(chat_id, "❌ Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})


@app.route("/cron", methods=["GET"])
def cron():
    print(f"[cron] Ping received at {datetime.utcnow().isoformat()} UTC")
    return "Cron OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
