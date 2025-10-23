from flask import Flask, request

app = Flask(__name__)

# בריאות בסיסית לבדיקת חיים בענן
@app.get("/health")
def health():
    return {"status": "ok"}, 200

# Webhook של Twilio לקליטת הודעות נכנסות (WhatsApp)
@app.post("/incoming")
def incoming_whatsapp():
    # Twilio שולח POST עם form-encoded
    from_number = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    wa_id = request.form.get("WaId", "")  # מזהה השולח

    print("📩 Incoming message")
    print(f"From: {from_number} (WaId={wa_id})")
    print(f"Body: {body}")

    # מחזירים תשובה בסיסית כדי שטוויליו לא ישלח שוב
    return "OK", 200

# הרצה מקומית (לא בשימוש בענן)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
