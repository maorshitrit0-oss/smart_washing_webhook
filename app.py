from flask import Flask, request
from twilio.rest import Client
import os
import json

app = Flask(__name__)

# --- הגדרות Twilio ---
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = "whatsapp:+14155238886"

TO_NUMBERS = [
    "whatsapp:+972534313371",  # אתה
    "whatsapp:+972523340644"   # אשתך
]

client = Client(TWILIO_SID, TWILIO_TOKEN)
STATUS_FILE = "survey_status.json"


# --- פונקציות עזר לניהול סטטוס ---

def load_status():
    if not os.path.exists(STATUS_FILE):
        return {"responses": {}, "answered": False}
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_status(data):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 נשמר סטטוס חדש: {data}")


def mark_response(number, text):
    """עדכון תשובה למספר מסוים"""
    data = load_status()
    responses = data.get("responses", {})
    responses[number] = text
    data["responses"] = responses

    # אם מישהו ענה כן → נעצור תזכורות
    if text in ["yes", "כן"]:
        data["answered"] = True
        save_status(data)
        send_final_message()
    else:
        data["answered"] = any(resp in ["yes", "כן"] for resp in responses.values())
        save_status(data)


# --- פונקציה לשליחת הודעת סיום ---
def send_final_message():
    for num in TO_NUMBERS:
        client.messages.create(
            from_=FROM_NUMBER,
            to=num,
            body="✅ תודה רבה! המשך יום טוב 🌞"
        )
    print("🎉 נשלחה הודעת סיום לשני המספרים.")


# --- בדיקה בסיסית ---
@app.get("/health")
def health():
    return {"status": "ok"}, 200


# --- בדיקת סטטוס ---
@app.get("/status")
def status():
    return load_status(), 200


# --- שליחת הודעה (תזכורת או מבחן) ---
@app.get("/send-test")
def send_test():
    data = load_status()
    if data.get("answered"):
        return {"status": "already_answered"}, 200

    for num in TO_NUMBERS:
        client.messages.create(
            from_=FROM_NUMBER,
            to=num,
            body="📢 תזכורת: האם המכונה סיימה לעבוד? השיבו 'כן' או 'לא'."
        )
    print("📨 נשלחו תזכורות לשני המספרים.")
    return {"status": "sent"}, 200


# --- הודעות נכנסות ---
@app.post("/incoming")
def incoming_whatsapp():
    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip().lower()

    print(f"📩 הודעה מ-{from_number}: {body}")

    # נעדכן את הסטטוס ונבדוק אם צריך לעצור תזכורות
    mark_response(from_number, body)

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)

