from flask import Flask, request
from twilio.rest import Client
import os

app = Flask(__name__)

# --- שלב B: הגדרות Twilio ---
# נשתמש במשתני סביבה ב-Render
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = "whatsapp:+14155238886"  # מספר ה-Sandbox של Twilio
TO_NUMBER = "whatsapp:+972534313371"   # המספר שלך (תעדכן כאן)
client = Client(TWILIO_SID, TWILIO_TOKEN)

# --- בדיקה בסיסית שהשרת חי ---
@app.get("/health")
def health():
    return {"status": "ok"}, 200

# --- שליחת הודעה יזומה ---
@app.get("/send-test")
def send_test():
    try:
        msg = client.messages.create(
            from_=FROM_NUMBER,
            body="📢 הודעת מבחן מהשרת שלך ברנדר! ✅",
            to=TO_NUMBER
        )
        return {"status": "sent", "sid": msg.sid}, 200
    except Exception as e:
        return {"error": str(e)}, 500

# --- קליטת הודעות נכנסות ---
@app.post("/incoming")
def incoming_whatsapp():
    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    wa_id = request.form.get("WaId", "")
    print("📩 Incoming message")
    print(f"From: {from_number} (WaId={wa_id})")
    print(f"Body: {body}")
    return "OK", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
