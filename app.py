from flask import Flask, request
from twilio.rest import Client
import os
import json

app = Flask(__name__)

# --- הגדרות Twilio ---
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = "whatsapp:+14155238886"  # מספר ה-Sandbox של Twilio

# שני מספרים למשלוח
TO_NUMBERS = [
    "whatsapp:+972534313371",  # אתה
    "whatsapp:+972523340644"   # אשתך
]

client = Client(TWILIO_SID, TWILIO_TOKEN)
STATUS_FILE = "survey_status.json"  # קובץ לניהול מצב הסקר


# --- פונקציות עזר לניהול קובץ הסטטוס ---

def load_status():
    """קריאת מצב נוכחי מקובץ JSON"""
    if not os.path.exists(STATUS_FILE):
        return {"answered": False}
    with open(STATUS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_status(answered: bool):
    """שמירת סטטוס תשובה לקובץ"""
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({"answered": answered}, f, ensure_ascii=False, indent=2)
    print(f"💾 נשמר סטטוס: answered={answered}")


# --- בדיקת חיים בסיסית ---
@app.get("/health")
def health():
    return {"status": "ok"}, 200


# --- בדיקת סטטוס נוכחי ---
@app.get("/status")
def status():
    data = load_status()
    return data, 200


# --- שליחת הודעת מבחן לשני המספרים ---
@app.get("/send-test")
def send_test():
    data = load_status()
    if data.get("answered"):
        return {"status": "already_answered"}, 200

    for num in TO_NUMBERS:
        msg = client.messages.create(
            from_=FROM_NUMBER,
            body="📢 הודעת מבחן משודרת לשני המספרים! ✅",
            to=num
        )
        print(f"נשלחה הודעה אל {num}, SID={msg.sid}")

    return {"status": "sent_to_all"}, 200


# --- קליטת הודעות נכנסות מ-Twilio ---
@app.post("/incoming")
def incoming_whatsapp():
    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip().lower()
    print("📩 הודעה נכנסת:")
    print(f"From: {from_number}")
    print(f"Body: {body}")

    if body in ["כן", "yes", "done"]:
        save_status(True)
        print("✅ המשתמש ענה כן – הסקר סומן כנגמר.")
    elif body in ["לא", "no"]:
        save_status(False)
        print("❌ המשתמש ענה לא – נמשיך בתזכורות.")
    else:
        print("ℹ️ תשובה לא מזוהה (לא כן/לא).")

    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)

