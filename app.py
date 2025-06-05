from flask import Flask, request, jsonify
import os
import requests
import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

ASSISTANT_INSTRUCTIONS = (
    "Ты — персональный ассистент по здоровью, спорту и питанию. "
    "Отвечай понятно, профессионально и с заботой, предлагая конкретные рекомендации."
)

app = Flask(__name__)

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_input = message.get("text")

    if not user_input:
        return jsonify({"error": "No user input"}), 400

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": ASSISTANT_INSTRUCTIONS},
                {"role": "user", "content": user_input}
            ]
        )
        assistant_reply = response.choices[0].message["content"]
        send_telegram_message(chat_id, assistant_reply)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"[ERROR] {e}")  # 👈 Выводим ошибку в логи Render
        send_telegram_message(chat_id, "Произошла ошибка при обработке запроса.")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
