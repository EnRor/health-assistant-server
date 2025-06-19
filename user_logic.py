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

def handle_callback_query_data(callback_query, chat_id):
    try:
        callback_query_id = callback_query["id"]
        data_key = callback_query["data"]

        answer_callback_query(callback_query_id)

        if data_key == "memory_view":
            thread_id = user_threads.get(chat_id)
            if not thread_id:
                thread = openai.beta.threads.create()
                thread_id = thread.id
                user_threads[chat_id] = thread_id

            runs_list = openai.beta.threads.runs.list(thread_id=thread_id, limit=1)
            if runs_list.data and runs_list.data[0].status in ["queued", "in_progress"]:
                send_telegram_message(chat_id, "⚠️ Пожалуйста, подождите, я обрабатываю предыдущий запрос.")
                return

            openai.beta.threads.messages.create(thread_id=thread_id, role="user", content="Что ты обо мне помнишь?")
            run = openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)

            while True:
                run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                status = run_status.status
                if status == "completed":
                    break
                elif status == "failed":
                    send_telegram_message(chat_id, "❌ Ошибка при выполнении запроса.")
                    return
                time.sleep(1)

            messages = openai.beta.threads.messages.list(thread_id=thread_id)
            assistant_msgs = [m for m in messages.data if m.role == "assistant"]

            if assistant_msgs:
                last_msg = assistant_msgs[-1]
                text_blocks = [b.text.value for b in last_msg.content if b.type == "text"]
                final_text = "\n".join(text_blocks).strip()
                if final_text:
                    send_telegram_message(chat_id, final_text)
                else:
                    send_telegram_message(chat_id, "⚠️ Ассистент не вернул текстовый ответ.")
            else:
                send_telegram_message(chat_id, "⚠️ Ответ от ассистента отсутствует.")

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
        print(f"[handle_callback_query_data] Exception: {e}")
        send_telegram_message(chat_id, "❌ Ошибка при обработке команды меню.")

def handle_message_data(message, chat_id):
    try:
        if "text" not in message:
            return
        user_message = message["text"].strip()

        # Обработка команды меню
        if user_message.lower() == "/menu":
            send_telegram_message(chat_id, "📍 Главное меню:", reply_markup=build_main_menu())
            return

        # Обработка установки напоминания через "через N минут"
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

        if chat_id not in user_threads:
            thread = openai.beta.threads.create()
            user_threads[chat_id] = thread.id
        thread_id = user_threads[chat_id]

        runs_list = openai.beta.threads.runs.list(thread_id=thread_id, limit=1)
        if runs_list.data and runs_list.data[0].status in ["queued", "in_progress"]:
            send_telegram_message(chat_id, "⚠️ Пожалуйста, подождите, я обрабатываю предыдущий запрос.")
            return

        openai.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
        run = openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)

        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            status = run_status.status
            print(f"[OpenAI Run Status] {status}")
            if status == "completed":
                break
            elif status == "failed":
                send_telegram_message(chat_id, "❌ Ошибка при выполнении запроса.")
                return
            elif status == "requires_action":
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                outputs = []
                for tool_call in tool_calls:
                    fname = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    print(f"[Tool call] {fname} with args {args}")

                    if fname == "set_reminder_delay":
                        delay = args.get("delay_minutes")
                        text = args.get("reminder_text", "Напоминание")
                        schedule_reminder_delay(chat_id, delay * 60, text)
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": f"Напоминание установлено через {delay} минут."
                        })
                    elif fname == "set_reminder_time":
                        reminder_text = args.get("reminder_text", "Напоминание")
                        reminder_time_absolute = args.get("reminder_time_absolute")
                        user_local_time = args.get("user_local_time")
                        schedule_reminder_time(chat_id, reminder_time_absolute, reminder_text, user_local_time)
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": f"Напоминание установлено на {reminder_time_absolute}."
                        })
                    elif fname == "google_search":
                        query = args.get("query")
                        res = google_search(query) if query else "❌ Отсутствует параметр 'query'."
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": res
                        })
                    elif fname == "get_user_memory":
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": "🧠 Вот что я помню о тебе."
                        })
                    elif fname == "get_reminders_list":
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": "📅 Вот список твоих напоминаний."
                        })
                    else:
                        outputs.append({
                            "tool_call_id": tool_call.id,
                            "output": f"❌ Неизвестная функция: {fname}"
                        })

                openai.beta.threads.runs.submit_tool_outputs(thread_id=thread_id, run_id=run.id, tool_outputs=outputs)
                continue
            else:
                time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        assistant_msgs = [m for m in messages.data if m.role == "assistant"]
        if assistant_msgs:
            last_msg = assistant_msgs[-1]
            text_blocks = [b.text.value for b in last_msg.content if b.type == "text"]
            final_text = "\n".join(text_blocks).strip()
            if final_text:
                send_telegram_message(chat_id, final_text)
            else:
                send_telegram_message(chat_id, "⚠️ Ассистент не вернул текстовый ответ.")
        else:
            send_telegram_message(chat_id, "⚠️ Ответ от ассистента отсутствует.")

    except Exception as e:
        print(f"[handle_message_data] Exception: {e}")
        send_telegram_message(chat_id, "❌ Ошибка при обработке сообщения.")
