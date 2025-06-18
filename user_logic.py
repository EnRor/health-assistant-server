import json
import time
import threading
from datetime import datetime, timedelta
import requests
import openai
import os

# Инициализация переменных окружения (если нужно)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# Глобальные словари для сессий и напоминаний
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
            payload["reply_markup"] = json.dumps(reply_markup)  # сериализация
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
        [{"text": "🏋️‍♀ План тренировок", "callback_data": "training_plan"}],
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
        server_now = datetime.now()
        reminder_datetime_server = server_now + timedelta(seconds=delta)
        delay_seconds = (reminder_datetime_server - server_now).total_seconds()

        def reminder_job():
            time.sleep(delay_seconds)
            send_telegram_message(chat_id, f"⏰ Напоминание: {reminder_text}")

        threading.Thread(target=reminder_job, daemon=True).start()
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


def _process_callback_query(chat_id, callback_data):
    if callback_data == "memory_view":
        thread_id = user_threads.get(chat_id)
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            user_threads[chat_id] = thread_id

        existing_runs = openai.beta.threads.runs.list(thread_id=thread_id, limit=1)
        if existing_runs.data and existing_runs.data[0].status in ["queued", "in_progress"]:
            send_telegram_message(chat_id, "⚠️ Пожалуйста, подождите, я ещё обрабатываю предыдущий запрос.")
            return

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
        assistant_messages = [msg for msg in messages.data if msg.role == "assistant"]

        if assistant_messages:
            latest_message = assistant_messages[-1]
            text_parts = [block.text.value for block in latest_message.content if block.type == "text"]
            final_text = "\n".join(text_parts).strip()
            send_telegram_message(chat_id, final_text if final_text else "⚠️ Ассистент не вернул текст.")
        else:
            send_telegram_message(chat_id, "⚠️ Не удалось получить ответ от ассистента.")

    elif callback_data == "memory_clear":
        if chat_id in user_threads:
            del user_threads[chat_id]
        send_telegram_message(chat_id, "🗑 Память очищена.")

    elif callback_data == "training_plan":
        send_telegram_message(chat_id, "🏋️‍♀ Ваш план тренировок будет здесь.")

    elif callback_data == "reminders_list":
        send_telegram_message(chat_id, "🗓 Здесь будет список ваших напоминаний.")

    else:
        send_telegram_message(chat_id, "⚠️ Неизвестная команда меню.")


def _process_user_message(chat_id, user_message):
    # Обработка команды /menu
    if user_message.lower() == "/menu":
        send_telegram_message(chat_id, "📍 Главное меню:", reply_markup=build_main_menu())
        return

    # Обработка команды /search
    if user_message.lower().startswith("/search"):
        query = user_message[len("/search"):].strip()
        if not query:
            send_telegram_message(chat_id, "Пожалуйста, укажите запрос после команды /search")
            return
        search_results = google_search(query)
        send_telegram_message(chat_id, search_results)
        return

    # Установка напоминания через "через N минут"
    if "через" in user_message.lower() and "напомни" in user_message.lower():
        try:
            parts = user_message.lower().split("через")
            minutes_part = parts[1].strip().split(" ")[0]
            reminder_text = " ".join(parts[1].strip().split(" ")[1:]) or "Напоминание"
            minutes = int(minutes_part)
            schedule_reminder_delay(chat_id, minutes * 60, reminder_text)
            send_telegram_message(chat_id, f"⏳ Напоминание установлено через {minutes} мин: {reminder_text}")
            return
        except Exception as e:
            send_telegram_message(chat_id, f"❌ Ошибка при установке напоминания: {e}")
            return

    # Обработка запросов к OpenAI Assistant API с памятью и контекстом
    if chat_id not in user_threads:
        thread = openai.beta.threads.create()
        user_threads[chat_id] = thread.id
    thread_id = user_threads[chat_id]

    existing_runs = openai.beta.threads.runs.list(thread_id=thread_id, limit=1)
    if existing_runs.data and existing_runs.data[0].status in ["queued", "in_progress"]:
        send_telegram_message(chat_id, "⚠️ Пожалуйста, подождите, я ещё обрабатываю предыдущий запрос.")
        return

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

                elif function_name == "get_user_memory":
                    outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": "🧠 Вот что я помню о тебе:"
                    })

                elif function_name == "get_reminders_list":
                    outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": "📅 Вот список твоих напоминаний:"
                    })

            openai.beta.threads.runs.submit_tool_outputs(thread_id=thread_id, run_id=run.id, tool_outputs=outputs)
            continue
        elif run_status.status in ["failed", "cancelled", "expired"]:
            send_telegram_message(chat_id, "❌ Ошибка выполнения запроса.")
            return
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


def handle_message_data(chat_id, user_message):
    threading.Thread(target=_process_user_message, args=(chat_id, user_message), daemon=True).start()


def handle_callback_query_data(chat_id, callback_data):
    threading.Thread(target=_process_callback_query, args=(chat_id, callback_data), daemon=True).start()
