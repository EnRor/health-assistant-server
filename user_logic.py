import os
import json
import time
import threading
from datetime import datetime, timedelta

import openai
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

openai.api_key = os.getenv("OPENAI_API_KEY")

user_threads = {}


def send_telegram_message(chat_id, text, reply_markup=None):
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
        print("[send_telegram_message]", response.status_code, response.text)
    except Exception as e:
        print(f"[send_telegram_message] Error: {e}")


def build_main_menu():
    keyboard = [
        [{"text": "\ud83d\udccb \u041f\u0430\u043c\u044f\u0442\u044c", "callback_data": "memory_view"}],
        [{"text": "\ud83d\uddd1 \u041e\u0447\u0438\u0441\u0442\u0438\u0442\u044c \u043f\u0430\u043c\u044f\u0442\u044c", "callback_data": "memory_clear"}],
        [{"text": "\ud83c\udfcb\ufe0f \u041f\u043b\u0430\u043d \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043e\u043a", "callback_data": "training_plan"}],
        [{"text": "\ud83d\uddd3 \u041c\u043e\u0438 \u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f", "callback_data": "reminders_list"}]
    ]
    return {"inline_keyboard": keyboard}


def schedule_reminder_delay(chat_id, delay_seconds, reminder_text):
    def reminder_job():
        time.sleep(delay_seconds)
        send_telegram_message(chat_id, f"\u23f0 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435: {reminder_text}")
    threading.Thread(target=reminder_job, daemon=True).start()


def schedule_reminder_time(chat_id, reminder_time_absolute, reminder_text, user_local_time):
    try:
        user_now = datetime.strptime(user_local_time, "%H:%M").replace(year=2000, month=1, day=1)
        reminder_time = datetime.strptime(reminder_time_absolute, "%H:%M").replace(year=2000, month=1, day=1)
        delta = (reminder_time - user_now).total_seconds()
        if delta < 0:
            delta += 24 * 3600
        threading.Thread(target=lambda: (time.sleep(delta), send_telegram_message(chat_id, f"\u23f0 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435: {reminder_text}")), daemon=True).start()
    except ValueError as e:
        send_telegram_message(chat_id, f"\u274c \u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0432\u0440\u0435\u043c\u0435\u043d\u0438: {e}")


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
        items = response.json().get("items", [])
        if not items:
            return "\u26a0\ufe0f \u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e."
        return "\n\n".join([f"*{item['title']}*\n{item['snippet']}\n{item['link']}" for item in items])
    except Exception as e:
        print(f"[google_search] Error: {e}")
        return "\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u043f\u043e\u0438\u0441\u043a\u0430."


def handle_callback_query_data(callback_query):
    try:
        chat_id = callback_query["message"]["chat"]["id"]
        data_key = callback_query["data"]

        assistant_input = {
            "memory_view": "Что ты обо мне помнишь?",
            "reminders_list": "Покажи список моих напоминаний",
            "training_plan": "Покажи план тренировок"
        }.get(data_key, None)

        if data_key == "memory_clear":
            if chat_id in user_threads:
                del user_threads[chat_id]
            send_telegram_message(chat_id, "\ud83d\uddd1 \u041f\u0430\u043c\u044f\u0442\u044c \u043e\u0447\u0438\u0449\u0435\u043d\u0430.")
            return

        if assistant_input:
            handle_message_data({"chat": {"id": chat_id}, "text": assistant_input})
        else:
            send_telegram_message(chat_id, "\u26a0\ufe0f \u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u0430\u044f \u043a\u043e\u043c\u0430\u043d\u0434\u0430.")

    except Exception as e:
        print("[handle_callback_query_data] Error:", e)


def handle_message_data(message):
    try:
        chat_id = message["chat"]["id"]
        user_message = message.get("text", "").strip()

        print(f"[handle_message_data] {chat_id}: {user_message}")

        if user_message.lower() == "/menu":
            send_telegram_message(chat_id, "\ud83d\udccd \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e:", reply_markup=build_main_menu())
            return

        if user_message.lower().startswith("/search"):
            query = user_message[len("/search"):].strip()
            result = google_search(query)
            send_telegram_message(chat_id, result)
            return

        if "\u0447\u0435\u0440\u0435\u0437" in user_message.lower() and "\u043d\u0430\u043f\u043e\u043c\u043d\u0438" in user_message.lower():
            try:
                parts = user_message.lower().split("через")
                minutes_part = parts[1].strip().split(" ")[0]
                reminder_text = " ".join(parts[1].strip().split(" ")[1:]) or "Напоминание"
                minutes = int(minutes_part)
                schedule_reminder_delay(chat_id, minutes * 60, reminder_text)
                send_telegram_message(chat_id, f"\u23f3 \u041d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0447\u0435\u0440\u0435\u0437 {minutes} \u043c\u0438\u043d: {reminder_text}")
                return
            except Exception as e:
                send_telegram_message(chat_id, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}")
                return

        if chat_id not in user_threads:
            thread = openai.beta.threads.create()
            user_threads[chat_id] = thread.id

        thread_id = user_threads[chat_id]

        openai.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)

        run = openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)

        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "requires_action":
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                outputs = []
                for tool_call in tool_calls:
                    args = json.loads(tool_call.function.arguments)
                    fname = tool_call.function.name
                    if fname == "set_reminder_delay":
                        schedule_reminder_delay(chat_id, args["delay_minutes"] * 60, args["reminder_text"])
                        outputs.append({"tool_call_id": tool_call.id, "output": f"Напоминание установлено через {args['delay_minutes']} мин."})
                    elif fname == "set_reminder_time":
                        schedule_reminder_time(chat_id, args["reminder_time_absolute"], args["reminder_text"], args["user_local_time"])
                        outputs.append({"tool_call_id": tool_call.id, "output": f"Напоминание установлено на {args['reminder_time_absolute']}."})
                    elif fname == "google_search":
                        outputs.append({"tool_call_id": tool_call.id, "output": google_search(args["query"])})
                    else:
                        outputs.append({"tool_call_id": tool_call.id, "output": "\ud83d\udd2e Команда выполнена."})
                openai.beta.threads.runs.submit_tool_outputs(thread_id=thread_id, run_id=run.id, tool_outputs=outputs)
                continue
            time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_messages = [msg for msg in messages.data if msg.role == "assistant"]
        if assistant_messages:
            final = "\n".join([block.text.value for block in assistant_messages[-1].content if block.type == "text"])
            send_telegram_message(chat_id, final.strip() if final else "\u26a0\ufe0f \u041f\u0443\u0441\u0442\u043e")
        else:
            send_telegram_message(chat_id, "\u26a0\ufe0f \u041d\u0435 \u043f\u043e\u043b\u0443\u0447\u0435\u043d \u043e\u0442\u0432\u0435\u0442.")

    except Exception as e:
        print("[handle_message_data] Error:", e)
        send_telegram_message(chat_id, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430: {e}")
