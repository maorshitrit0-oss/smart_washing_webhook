# app.py
from flask import Flask, request, jsonify
from twilio.rest import Client
import os, json, threading, time

# יצירת אפליקציית Flask
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
REMINDER_INTERVAL_SECONDS = 5 * 60  # כל 5 דקות
# ====================

client = Client(TWILIO_SID, TWILIO_TOKEN)
file_lock = threading.Lock()  # למניעת גישה כפולה לקובץ

# ====== פונקציות עזר ======
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


# ====== Scheduler (תזמון פנימי בחינם) ======
_scheduler_thread = None
_scheduler_stop_event = threading.Event()


def scheduler_loop():
    """לולאת תזמון שנשלחת כל 5 דקות עד שמישהו עונה כן"""
    app.logger.info("⏱️ Scheduler התחיל לפעול.")
    while not _scheduler_stop_event.is_set():
        data = load_status()
        if not data.get("answered"):
            app.logger.info("🔁 טרם נענו – שולח תזכורת לשני המספרים.")
            send_message_to_all("⏰ תזכורת: האם המכונה סיימה לעבוד? השיבו 'כן' או 'לא'.")
        else:
            app.logger.info("✅ נמצא answered=True – אין צורך בתזכורות נוספות.")
        # המתנה 5 דקות (או עצירה מוקדמת)
        completed = _scheduler_stop_event.wait(timeout=REMINDER_INTERVAL_SECONDS)
        if completed:
            break
    app.logger.info("🛑 Scheduler הופסק.")


def start_scheduler_background():
    """הפעלת תזמון ברקע אם לא פעיל"""
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_stop_event.clear()
        _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True, name="reminder-scheduler")
        _scheduler_thread.start()
        app.logger.info("🚀 Scheduler הופעל בהצלחה.")


def stop_scheduler_background():
    """עצירת התזמון"""
    _scheduler_stop_event.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=2)
        app.logger.info("⏹️ Scheduler נעצר בהצלחה.")


# ====== Flask routes ======

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/status", methods=["GET"])
def status():
    """בדיקת סטטוס נוכחי"""
    return jsonify(load_status()), 200


@app.route("/reset-status", methods=["GET"])
def reset_status():
    """איפוס הסקר"""
    data = {"responses": {}, "answered": False}
    save_status(data)
    start_scheduler_background()  # הפעלה מחדש אחרי איפוס
    return jsonify({"status": "reset"}), 200


@app.route("/send-test", methods=["GET"])
def send_test():
    """שליחה ידנית לבדיקה"""
    data = load_status()
    if data.get("answered"):
        return jsonify({"status": "already_answered"}), 200
    send_message_to_all("📢 תזכורת ידנית: האם המכונה סיימה לעבוד? השיבו 'כן' או 'לא'.")
    return jsonify({"status": "sent_manual"}), 200


@app.route("/incoming", methods=["POST"])
def incoming():
    """קליטת הודעות נכנסות מ-Twilio"""
    from_number = request.form.get("From", "").strip()
    body = (request.form.get("Body") or "").strip().lower()
    app.logger.info(f"📩 הודעה מ-{from_number}: {body}")

    data = load_status()
    responses = data.get("responses", {})
    responses[from_number] = body
    data["responses"] = responses

    # אם מישהו ענה כן -> לסמן ולשלוח הודעת סיום
    if body in ["כן", "yes", "done"]:
        data["answered"] = True
        save_status(data)
        try:
            send_final_message()
        except Exception as e:
            app.logger.error(f"שגיאה בשליחת הודעת סיום: {e}")
        stop_scheduler_background()  # לעצור את התזכורות
    else:
        data["answered"] = any(v in ["כן", "yes", "done"] for v in responses.values())
        save_status(data)

    return "OK", 200


# ====== התחלה אוטומטית ======
start_scheduler_background()  # מתחיל תזמון מיד עם עליית האפליקציה

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)


