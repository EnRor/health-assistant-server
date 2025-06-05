from flask import Flask, request, jsonify
import os
import requests
from dotenv import load_dotenv
import openai

load_dotenv()

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    print("Полученные данные:", data)

    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_input = message.get("text")

    if not user_input:
        return jsonify({"error": "No user input"}), 400

    try:
        # Создаём thread
        thread = openai.beta.threads.create()

        # Отправляем сообщение от пользователя
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )

        # Запускаем ассистента
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Ждём выполнения
        import time
        while True:
            status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if status.status == "completed":
                break
            elif status.status == "failed":
                raise Exception("Ассистент не смог завершить ответ.")
            time.sleep(1)

        # Получаем сообщение от ассистента
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        assistant_reply = messages.data[0].content[0].text.value

        # Отправляем пользователю в Telegram
        send_telegram_message(chat_id, assistant_reply)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        print("Ошибка:", e)
        send_telegram_message(chat_id, "Произошла ошибка при обработке запроса.")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
