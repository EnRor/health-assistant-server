from flask import Flask, request, jsonify
import os
import requests
from dotenv import load_dotenv
import openai

load_dotenv()

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ASSISTANT_INSTRUCTIONS = "Ты — доброжелательный и профессиональный ассистент по здоровью и фитнесу. Отвечай кратко, по делу, с чуткостью."

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
        # Используем ChatCompletion напрямую вместо Assistants API
        response = openai.ChatCompletion.create(
            model="gpt-4o",  # можно заменить на gpt-4-turbo или другой
            messages=[
                {"role": "system", "content": ASSISTANT_INSTRUCTIONS},
                {"role": "user", "content": user_input}
            ]
        )

        assistant_reply = response.choices[0].message["content"]
        send_telegram_message(chat_id, assistant_reply)
        return jsonify({"status": "success", "reply": assistant_reply}), 200

    except Exception as e:
        print("Ошибка:", e)
        send_telegram_message(chat_id, "Произошла внутренняя ошибка.")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
