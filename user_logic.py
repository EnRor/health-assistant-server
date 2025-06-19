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
    try:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        response = requests.post(f"{TELEGRAM_API_URL}/answerCallbackQuery", json=payload)
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

def handle_callback_query_data(callback_query):
    try:
        chat_id = callback_query["message"]["chat"]["id"]
        callback_query_id = callback_query["id"]
        data_key = callback_query["data"]

        answer_callback_query(callback_query_id)

        if data_key == "memory_view":
            thread_id = user_threads.get(chat_id)
            if not thread_id:
                thread = openai.beta.threads.create()
                thread_id = thread.id
                user_threads[chat_id] = thread_id

            openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content="Что ты обо мне помнишь?"
            )
            run = openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)
            while True:
                run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run_status.status == "completed":
                    break
                elif run_status.status == "failed":
                    send_telegram_message(chat_id, "❌ Ошибка выполнения запроса.")
                    return
                time.sleep(1)

            messages = openai.beta.threads.messages.list(thread_id=thread_id)
            assistant_messages = [m for m in messages.data if m.role == "assistant"]
            if assistant_messages:
                latest = assistant_messages[-1]
                text_parts = [b.text.value for b in latest.content if b.type == "text"]
                send_telegram_message(chat_id, "\n".join(text_parts).strip())
            else:
                send_telegram_message(chat_id, "⚠️ Не удалось получить ответ от ассистента.")

        elif data_key == "memory_clear":
            if chat_id in user_threads:
                del user_threads[chat_id]
            send_telegram_message(chat_id, "🗑 Память очищена.")

        elif data_key == "training_plan":
            send_telegram_message(chat_id, "🏋️‍♀ Ваш план тренировок будет здесь.")

        elif data_key == "reminders_list":
            send_telegram_message(chat_id, "🗓 Здесь будет список ваших напоминаний.")

        else:
            send_telegram_message(chat_id, "⚠️ Неизвестная команда меню.")

    except Exception as e:
        print("❌ Ошибка обработки callback_query:", e)

def handle_message_data(message):
    try:
        chat_id = message["chat"]["id"]
        user_message = message.get("text", "").strip()

        if user_message.lower() == "/menu":
            send_telegram_message(chat_id, "📍 Главное меню:", reply_markup=build_main_menu())
            return

        if "через" in user_message.lower() and "напомни" in user_message.lower():
            try:
                parts = user_message.lower().split("через")
                minutes_part = parts[1].strip().split(" ")[0]
                reminder_text = " ".join(parts[1].strip().split(" ")[1:]) or "Напоминание"
                minutes = int(minutes_part)

                def reminder():
                    time.sleep(minutes * 60)
                    send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")

                threading.Thread(target=reminder, daemon=True).start()
                send_telegram_message(chat_id, f"⏳ Напоминание установлено через {minutes} мин: {reminder_text}")
                return
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Ошибка при установке напоминания: {e}")
                return

        # Обращение к OpenAI ассистенту
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
            elif run_status.status == "failed":
                send_telegram_message(chat_id, "❌ Ошибка выполнения запроса.")
                return
            time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_messages = [m for m in messages.data if m.role == "assistant"]
        if assistant_messages:
            latest = assistant_messages[-1]
            text_parts = [b.text.value for b in latest.content if b.type == "text"]
            final_text = "\n".join(text_parts).strip()
            send_telegram_message(chat_id, final_text if final_text else "⚠️ Ассистент не вернул текст.")
        else:
            send_telegram_message(chat_id, "⚠️ Ответ от ассистента не получен.")

    except Exception as e:
        print("❌ Ошибка обработки message:", e)
        send_telegram_message(chat_id, "❌ Произошла ошибка при обращении к ассистенту.")
