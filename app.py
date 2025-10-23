# app.py
from flask import Flask, request, jsonify
from twilio.rest import Client
import os, json, threading, time

app = Flask(__name__)

# ====== CONFIG ======
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
FROM_NUMBER = "whatsapp:+14155238886"  # Twilio sandbox
TO_NUMBERS = [
    "whatsapp:+972534313371",  # אתה
    "whatsapp:+972523340644"   # אשתך
]
STATUS_FILE = "survey_status.json"
REMINDER_INTERVAL_SECONDS = 5 * 60  # 5 דקות
# ====================

client = Client(TWILIO_SID, TWILIO_TOKEN)

# Lock לשמירה/קריאה בטוחה מהקובץ (thread-safe)
file_lock = threading.Lock()


def load_status():
    with file_lock:
        if not os.path.exists(STATUS_FILE):
            return {"responses": {}, "answered": False}
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {"responses": {}, "answered": False}


def save_status(data):
    with file_lock:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    app.logger.info(f"Saved status: {data}")


def send_message_to_all(body_text):
    for num in TO_NUMBERS:
        try:
            msg = client.messages.create(from_=FROM_NUMBER, to=num, body=body_text)
            app.logger.info(f"Sent to {num} SID={msg.sid}")
        except Exception as e:
            app.logger.error(f"Failed sending to {num}: {e}")


def send_final_message():
    send_message_to_all("✅ תודה רבה! המשך יום טוב 🌞")
    app.logger.info("Final message sent to all.")


# ====== Scheduler thread (runs in background) ======
# הלוגיקה: כל REMINDER_INTERVAL_SECONDS תבדוק את הסטטוס; אם answered==False -> שלח תזכורת.
# ברגע שהתשובה משתנה ל-True, תשלח הודעת סיום ותפסיק לשלוח.

_scheduler_thread = None
_scheduler_stop_event = threading.Event()


def scheduler_loop():
    app.logger.info("Scheduler thread started.")
    while not _scheduler_stop_event.is_set():
        data = load_status()
        if data.get("answered"):
            app.logger.debug("Already answered==True -> scheduler sleeping until next check.")
            # אם כבר ענו, לא לשלוח; לבדוק שוב בעוד אינטרוול
        else:
            # שלח תזכורת לכל מי שרשום ברשימת TO_NUMBERS
            app.logger.info("No 'yes' yet -> sending reminder to all numbers.")
            send_message_to_all("⏰ תזכורת: האם המכונה סיימה לעבוד? השיבו 'כן' או 'לא'.")
        # המתנה או עצירה מוקדמת
        # מחכים בדיוק REMINDER_INTERVAL_SECONDS, אבל נשאלים אם יש עצירה
        completed = _scheduler_stop_event.wait(timeout=REMINDER_INTERVAL_SECONDS)
        if completed:
            break
    app.logger.info("Scheduler thread stopped.")


def start_scheduler_background():
    global _scheduler_thread
    # אל תפעיל יותר מפעם אחת
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_stop_event.clear()
        _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True, name="reminder-scheduler")
        _scheduler_thread.start()


def stop_scheduler_background():
    _scheduler_stop_event.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=2)


# ====== Flask routes ======

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/status", methods=["GET"])
def status():
    return jsonify(load_status()), 200


@app.route("/reset-status", methods=["GET"])
def reset_status():
    data = {"responses": {}, "answered": False}
    save_status(data)
    return jsonify({"status": "reset"}), 200


@app.route("/send-test", methods=["GET"])
def send_test():
    # שלח תזכורת ידנית (אם לא ענו)
    data = load_status()
    if data.get("answered"):
        return jsonify({"status": "already_answered"}), 200
    send_message_to_all("📢 תזכורת ידנית: האם המכונה סיימה לעבוד? השיבו 'כן' או 'לא'.")
    return jsonify({"status": "sent_manual"}), 200


@app.route("/incoming", methods=["POST"])
def incoming():
    # Twilio שולח form-encoded data
    from_number = request.form.get("From", "").strip()
    body = (request.form.get("Body") or "").strip().lower()
    app.logger.info(f"Incoming from {from_number}: {body}")

    data = load_status()
    responses = data.get("responses", {})

    # שמירת התשובה לפי מספר
    responses[from_number] = body
    data["responses"] = responses

    # אם מישהו ענה "כן" -> סימון answered ולהפעיל הודעת סיום
    if body in ["כן", "yes", "done"]:
        data["answered"] = True
        save_status(data)
        # נשלח הודעת תודה מיד ונפסיק את scheduler
        try:
            send_final_message()
        except Exception as e:
            app.logger.error(f"Error sending final message: {e}")
        # אפשר לעצור את ה-scheduler, או להשאירו לבדוק ולראות answered==True
        # נעצור אותו כדי שלא ינסה לשלוח שוב מיד
        stop_scheduler_background()
    else:
        # לא "כן" -> נשמור ונשאיר answered כפי שהוא (ייתכן שאחר ענה כבר כן בעבר)
        # אם אף אחד לא ענה כן -> answered יישאר False
        data["answered"] = any(v in ["כן", "yes", "done"] for v in responses.values())
        save_status(data)

    return "OK", 200


# ===== start scheduler automatically when app starts =====
@app.before_first_request
def activate_scheduler():
    # מפעיל את ה-thread רק ב־process הראשי אחרי בקשת ה־first-request
    # שים לב: עם gunicorn כדאי להריץ worker=1 כדי למנוע כפילויות
    start_scheduler_background()


if __name__ == "__main__":
    # להרצה מקומית
    start_scheduler_background()
    app.run(host="0.0.0.0", port=10000, debug=True)



