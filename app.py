from flask import Flask, request, jsonify
from twilio.rest import Client
import os, json, threading, time
from datetime import datetime

app = Flask(__name__)

# ====== CONFIG ======
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = "whatsapp:+14155238886"  # Twilio sandbox
TO_NUMBERS = [
    "whatsapp:+972534313371",  # מאור
    "whatsapp:+972523340644"   # אשתך
]
STATUS_FILE = "survey_status.json"
REMINDER_INTERVAL_SECONDS = 300  # כל 5 דקות
# ====================

client = Client(TWILIO_SID, TWILIO_TOKEN)
file_lock = threading.Lock()

# ====== פונקציות עזר ======
def load_status():
    """טוען את מצב הסקר מקובץ JSON"""
    with file_lock:
        if not os.path.exists(STATUS_FILE):
            data = {"responses": {}, "first_sent": False}
            save_status(data)
            return data
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {"responses": {}, "first_sent": False}


def save_status(data):
    """שומר מצב חדש לקובץ"""
    with file_lock:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    app.logger.info(f"💾 נשמר סטטוס חדש: {data}")


def send_message(to_number, body_text):
    """שליחת הודעה בודדת"""
    try:
        msg = client.messages.create(from_=FROM_NUMBER, to=to_number, body=body_text)
        app.logger.info(f"נשלחה הודעה אל {to_number}, SID={msg.sid}")
    except Exception as e:
        app.logger.error(f"שגיאה בשליחה אל {to_number}: {e}")


def send_message_to_all(body_text):
    """שליחת הודעה לכל המספרים"""
    for num in TO_NUMBERS:
        send_message(num, body_text)


def send_final_message():
    """שליחת הודעת סיום לשניהם"""
    send_message_to_all("✅ תודה רבה! המשך יום טוב 🌞")
    app.logger.info("🎉 נשלחה הודעת סיום לשני המספרים.")


# ====== Scheduler ======
_scheduler_thread = None
_scheduler_stop_event = threading.Event()

def scheduler_loop():
    """לולאת תזכורות חכמה לפי מי שענה"""
    app.logger.info("⏱️ Scheduler התחיל לפעול.")
    while not _scheduler_stop_event.is_set():
        data = load_status()
        responses = data.get("responses", {})

        # הודעה ראשונה
        if not data.get("first_sent", False):
            app.logger.info("📢 שולח הודעה ראשונה לשני המספרים.")
            send_message_to_all("📢 המכונה סיימה לעבוד! האם תלית את הכביסה?\nאנא השב 'כן' או 'לא'.")
            data["first_sent"] = True
            save_status(data)

        # תזכורת רק למי שלא ענה בכלל או שענה "לא"
        else:
            unanswered = [num for num in TO_NUMBERS if responses.get(num) not in ["כן", "yes", "done"]]
            if unanswered:
                now = datetime.now().strftime("%H:%M:%S")
                app.logger.info(f"🔁 שולח תזכורת רק למי שלא ענה ({unanswered}) - {now}")
                for num in unanswered:
                    send_message(num, "⏰ תזכורת: האם תלית את הכביסה?\nאנא השב 'כן' או 'לא'.")
            else:
                app.logger.info("✅ כולם ענו כן – עוצר תזכורות.")
                break

        # המתנה 5 דקות
        app.logger.info(f"🕒 ממתין {REMINDER_INTERVAL_SECONDS} שניות לפני התזכורת הבאה")
        completed = _scheduler_stop_event.wait(timeout=REMINDER_INTERVAL_SECONDS)
        if completed:
            break

    app.logger.info("🛑 Scheduler הופסק.")


def start_scheduler_background():
    """מפעיל את הסקדולר ברקע"""
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_stop_event.clear()
        _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        _scheduler_thread.start()
        app.logger.info("🚀 Scheduler הופעל בהצלחה.")


def stop_scheduler_background():
    """עוצר את הסקדולר"""
    _scheduler_stop_event.set()
    app.logger.info("⏹️ Scheduler נעצר בהצלחה.")


# ====== Flask Routes ======
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/status", methods=["GET"])
def status():
    return jsonify(load_status()), 200


@app.route("/reset-status", methods=["GET"])
def reset_status():
    """מאפס את הסקר"""
    data = {"responses": {}, "first_sent": False}
    save_status(data)
    start_scheduler_background()
    return jsonify({"status": "reset"}), 200


@app.route("/incoming", methods=["POST"])
def incoming():
    """קליטת הודעות נכנסות מ-Twilio"""
    from_number = request.form.get("From", "").strip()
    body = (request.form.get("Body") or "").strip().lower()
    clean_body = body.replace("!", "").replace(".", "").replace("?", "").strip()
    app.logger.info(f"📩 הודעה מ-{from_number}: {clean_body}")

    data = load_status()
    responses = data.get("responses", {})
    responses[from_number] = clean_body
    data["responses"] = responses
    save_status(data)

    # אם מישהו ענה כן → שולחים הודעת סיום לכולם ועוצרים תזכורות
    if clean_body in ["כן", "yes", "done"]:
        app.logger.info(f"✅ {from_number} ענה כן — שולח הודעת סיום.")
        send_final_message()
        stop_scheduler_background()

    return "OK", 200


# ====== התחלה אוטומטית ======
if __name__ != "__main__":
    start_scheduler_background()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    start_scheduler_background()
    app.run(host="0.0.0.0", port=port)


