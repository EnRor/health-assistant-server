import os
import json
import time
import threading
from datetime import datetime, timedelta

import openai
import requests

openai.api_key = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

user_threads = {}
user_reminders = {}

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

def answer_callback_query(callback_query_id, text=None):
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        response = requests.post(url, json=payload)
        print("[answer_callback_query]", response.status_code, response.text)
    except Exception as e:
        print(f"[answer_callback_query] Error: {e}")

def build_main_menu():
    keyboard = [
        [{"text": "📋 Память", "callback_data": "memory_view"}],
        [{"text": "🗑 Очистить память", "callback_data": "memory_clear"}],
        [{"text": "🏋️ План тренировок", "callback_data": "training_plan"}],
        [{"text": "🗓 Мои напоминания", "callback_data": "reminders_list"}]
    ]
    return {"inline_keyboard": keyboard}

def schedule_reminder_delay(chat_id, delay_seconds, reminder_text):
    def reminder_job():
        time.sleep(delay_seconds)
        send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")
    threading.Thread(target=reminder_job, daemon=True).start()

def schedule_reminder_time(chat_id, reminder_time_absolute, reminder_text, user_local_time):
    try:
        user_now = datetime.strptime(user_local_time, "%H:%M").replace(year=2000, month=1, day=1)
        reminder_time = datetime.strptime(reminder_time_absolute, "%H:%M").replace(year=2000, month=1, day=1)
        delta = (reminder_time - user_now).total_seconds()
        if delta < 0:
            delta += 24 * 3600
        delay_seconds = delta

        def reminder_job():
            time.sleep(delay_seconds)
            send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")

        threading.Thread(target=reminder_job, daemon=True).start()
    except ValueError as e:
        send_telegram_message(chat_id, f"❌ Некорректный формат времени. HH:MM. Ошибка: {e}")

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
            return "⚠️ Ничего не найдено."
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

def handle_user_message(message):
    threading.Thread(target=_process_user_message, args=(message,), daemon=True).start()

def process_callback(callback):
    threading.Thread(target=_process_callback_query, args=(callback,), daemon=True).start()

from .core_logic import _process_user_message, _process_callback_query
