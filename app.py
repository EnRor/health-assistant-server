import os
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")  # Это ID модели ассистента (например, "ft:...")

openai = OpenAI(api_key=OPENAI_API_KEY)

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_telegram_message(chat_id: int, text: str):
    requests.post(f"{TELEGRAM_API_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    message = data.get("message")
    if not message:
        return jsonify({"ok": True})

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_message = message.get("text")

    if message.get("from", {}).get("is_bot"):
        return jsonify({"ok": True})

    if not user_message:
        return jsonify({"ok": True})

    # Формируем список сообщений - можно добавить историю из БД/памяти, сейчас только последнее
    messages = [
        {"role": "user", "content": user_message}
    ]

    try:
        # Вызов chat.completions.create с model=ASSISTANT_ID
        response = openai.chat.completions.create(
            model=ASSISTANT_ID,
            messages=messages,
            user=str(user_id)  # необязательно, но полезно для логирования и отслеживания
        )

        # Получаем ответ ассистента из первого выбора
        assistant_reply = response.choices[0].message.content

        if assistant_reply:
            send_telegram_message(chat_id, assistant_reply)
        else:
            send_telegram_message(chat_id, "Извините, не удалось получить ответ от ассистента.")

    except Exception as e:
        print(f"OpenAI API error: {e}")
        send_telegram_message(chat_id, "Произошла ошибка при обращении к ассистенту.")

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
