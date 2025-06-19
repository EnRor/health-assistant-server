import os
import json
import time
import threading
from datetime import datetime, timedelta
import openai
import requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
openai.api_key = OPENAI_API_KEY

user_threads = {}

# Telegram message sender
def send_telegram_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        response = requests.post(f"{TELEGRAM_API_URL}/sendMessage", json=payload)
        print("[send_telegram_message]", response.status_code, response.text)
    except Exception as e:
        print(f"[send_telegram_message] Error: {e}")

# Меню

def build_main_menu():
    keyboard = [
        [{"text": "📋 Память", "callback_data": "memory_view"}],
        [{"text": "🗑 Очистить память", "callback_data": "memory_clear"}],
        [{"text": "🏋️ План тренировок", "callback_data": "training_plan"}],
        [{"text": "🗓 Мои напоминания", "callback_data": "reminders_list"}]
    ]
    return {"inline_keyboard": keyboard}

# Напоминания
def schedule_reminder_delay(chat_id, delay_seconds, reminder_text):
    def job():
        time.sleep(delay_seconds)
        send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")
    threading.Thread(target=job, daemon=True).start()

# Google Search
def google_search(query):
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CSE_ID, "q": query, "num": 3}
        res = requests.get(url, params=params).json()
        items = res.get("items", [])
        return "\n\n".join([f"*{i['title']}*\n{i['snippet']}\n{i['link']}" for i in items]) or "⚠️ Ничего не найдено."
    except Exception as e:
        return f"❌ Ошибка: {e}"

# Обработка callback

def handle_callback_query_data(chat_id, callback):
    try:
        callback_id = callback["id"]
        data_key = callback["data"]
        requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json={"callback_query_id": callback_id})

        if data_key == "memory_view":
            handle_user_query(chat_id, "Что ты обо мне помнишь?")
        elif data_key == "memory_clear":
            user_threads.pop(chat_id, None)
            send_telegram_message(chat_id, "🗑 Память очищена.")
        elif data_key == "training_plan":
            send_telegram_message(chat_id, "🏋️ Ваш план тренировок будет здесь.")
        elif data_key == "reminders_list":
            send_telegram_message(chat_id, "🗓 Здесь будет список ваших напоминаний.")
        else:
            send_telegram_message(chat_id, "⚠️ Неизвестная команда.")
    except Exception as e:
        print("[handle_callback_query_data] Error:", e)

# Обработка сообщений

def handle_message_data(chat_id, message):
    try:
        text = message.get("text", "").strip()

        if text.lower() == "/menu":
            send_telegram_message(chat_id, "📍 Главное меню:", reply_markup=build_main_menu())
            return

        if text.lower().startswith("/search"):
            query = text[len("/search"):].strip()
            send_telegram_message(chat_id, google_search(query) if query else "Введите запрос.")
            return

        if "через" in text.lower() and "напомни" in text.lower():
            try:
                parts = text.lower().split("через")
                minutes_part = parts[1].strip().split(" ")[0]
                minutes = int(minutes_part)
                reminder_text = " ".join(parts[1].strip().split(" ")[1:]) or "Напоминание"
                schedule_reminder_delay(chat_id, minutes * 60, reminder_text)
                send_telegram_message(chat_id, f"⏳ Напоминание установлено через {minutes} мин: {reminder_text}")
                return
            except:
                send_telegram_message(chat_id, "❌ Не удалось понять время.")
                return

        handle_user_query(chat_id, text)

    except Exception as e:
        print("[handle_message_data] Error:", e)

# OpenAI Run Logic

def handle_user_query(chat_id, user_text):
    try:
        if chat_id not in user_threads:
            thread = openai.beta.threads.create()
            user_threads[chat_id] = thread.id

        thread_id = user_threads[chat_id]

        openai.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_text)
        run = openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)

        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "requires_action":
                outputs = []
                for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
                    fn = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    out = ""

                    if fn == "set_reminder_delay":
                        mins = args.get("delay_minutes")
                        text = args.get("reminder_text", "Напоминание")
                        schedule_reminder_delay(chat_id, mins * 60, text)
                        out = f"⏳ Напоминание через {mins} минут: {text}"

                    elif fn == "google_search":
                        out = google_search(args.get("query", ""))

                    elif fn == "get_user_memory":
                        out = "🧠 Вот что я помню о тебе:"

                    elif fn == "get_reminders_list":
                        out = "📅 Вот список твоих напоминаний:"

                    outputs.append({"tool_call_id": tool_call.id, "output": out})

                openai.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=outputs
                )
                time.sleep(1)
            elif run_status.status in ["failed", "cancelled", "expired"]:
                send_telegram_message(chat_id, "❌ Ошибка выполнения запроса.")
                return
            else:
                time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_msgs = [m for m in messages.data if m.role == "assistant"]
        if assistant_msgs:
            content_blocks = assistant_msgs[-1].content
            response_text = "\n".join([b.text.value for b in content_blocks if b.type == "text"]).strip()
            send_telegram_message(chat_id, response_text or "⚠️ Пустой ответ от ИИ.")
        else:
            send_telegram_message(chat_id, "⚠️ Не удалось получить ответ.")

    except Exception as e:
        print("[handle_user_query] Error:", e)
        send_telegram_message(chat_id, "❌ Ошибка при обращении к ИИ.")