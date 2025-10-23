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
REMINDER_INTERVAL_SECONDS = 300  # כל 5 דקות בדיוק
# ====================

client = Client(TWILIO_SID, TWILIO_TOKEN)
file_lock = threading.Lock()

# ====== פונקציות עזר ======
def load_status():
    """טוען את מצב הסקר מקובץ JSON"""
    with file_lock:
        if not os.path.exists(STATUS_FILE):
            return {"responses": {}, "answered": False, "first_sent": False}
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {"responses": {}, "answered": False, "first_sent": False}


def save_status(data):
    """שומר מצב חדש לקובץ"""
    with file_lock:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    app.logger.info(f"💾 נשמר סטטוס חדש: {data}")


def send_message_to_all(body_text):
    """שליחת הודעה לכל המספרים"""
    for num in TO_NUMBERS:
        try:
            msg = client.messages.create(from_=FROM_NUMBER, to=num, body=body_text)
            app.logger.info(f"נשלחה הודעה אל {num}, SID={msg.sid}")
        except Exception as e:
            app.logger.error(f"שגיאה בשליחה אל {num}: {e}")


def send_final_message():
    """שליחת הודעת סיום לאחר תשובה חיובית"""
    send_message_to_all("✅ תודה רבה! המשך יום טוב 🌞")
    app.logger.info("🎉 נשלחה הודעת סיום לשני המספרים.")


# ====== Scheduler ======
_scheduler_thread = None
_scheduler_stop_event = threading.Event()

def scheduler_loop():
    """לולאת תזכורות אוטומטית"""
    app.logger.info("⏱️ Scheduler התחיל לפעול.")
    while not _scheduler_stop_event.is_set():
        data = load_status()

        # אם טרם נשלחה ההודעה הראשונה
        if not data.get("first_sent", False):
            app.logger.info("📢 שולח הודעה ראשונה - המכונה סיימה לעבוד.")
            send_message_to_all("📢 המכונה סיימה לעבוד! האם תלית את הכביסה?\nאנא השב 'כן' או 'לא'.")
            data["first_sent"] = True
            save_status(data)

        # אם טרם נענו
        elif not data.get("answered"):
            now = datetime.now().strftime("%H:%M:%S")
            app.logger.info(f"🔁 טרם נענו – שולח תזכורת ({now})")
            send_message_to_all("⏰ תזכורת: האם תלית את הכביסה?\nאנא השב 'כן' או 'לא'.")

        else:
            app.logger.info("✅ נמצא answered=True – אין צורך בתזכורות נוספות.")
            break

        # המתנה 5 דקות
        app.logger.info(f"🕒 ממתין {REMINDER_INTERVAL_SECONDS} שניות לפני התזכורת הבאה ({datetime.now().strftime('%H:%M:%S')})")
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
    """מאפס את הסקר לחלוטין"""
    data = {"responses": {}, "answered": False, "first_sent": False}
    save_status(data)
    start_scheduler_background()
    return jsonify({"status": "reset"}), 200


@app.route("/send-test", methods=["GET"])
def send_test():
    """בדיקה ידנית"""
    data = load_status()
    if data.get("answered"):
        return jsonify({"status": "already_answered"}), 200
    send_message_to_all("📢 בדיקה: האם תלית את הכביסה?\nאנא השב 'כן' או 'לא'.")
    return jsonify({"status": "sent_manual"}), 200


@app.route("/incoming", methods=["POST"])
def incoming():
    """קליטת הודעות נכנסות מ-Twilio"""
    from_number = request.form.get("From", "").strip()
    body = (request.form.get("Body") or "").strip().lower()
    app.logger.info(f"📩 הודעה מ-{from_number}: {body}")

    # ניקוי סימנים
    clean_body = body.replace("!", "").replace(".", "").strip()

    data = load_status()
    responses = data.get("responses", {})
    responses[from_number] = clean_body
    data["responses"] = responses

    # אם מישהו ענה כן
    if any(v in ["כן", "yes", "done"] for v in responses.values()):
        data["answered"] = True
        save_status(data)
        send_final_message()
        stop_scheduler_background()
    else:
        # לא לדרוס תשובה קודמת אם כבר נענתה בחיוב
        data["answered"] = data.get("answered", False)
        save_status(data)

    return "OK", 200


# ====== התחלה אוטומטית ======
if __name__ == "__main__":
    start_scheduler_background()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)


