import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- শুধুমাত্র Groq API Key ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# WhatsApp Settings
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "").strip()
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()
GRAPH_API = "https://graph.facebook.com/v21.0"
WHATSAPP_WABA_ID = os.environ.get("WHATSAPP_WABA_ID", "2534359393738787").strip()

wa_history = {}
debug_state = {"last_webhook": None, "last_send": None}

SYSTEM_INSTRUCTION = (
    "You are a friendly and helpful AI assistant on a public website. "
    "Answer any question the user asks, clearly and helpfully. "
    "Always reply in the same language the user writes in (Bangla or English). "
    "Keep answers accurate; if you are unsure about something, say so honestly."
)

# ---------------- Web & Chat Routes ----------------

@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception as e:
        print("TEMPLATE ERROR:", repr(e), flush=True)
        for candidate in ("templates/index.html", "index.html"):
            if os.path.exists(candidate):
                with open(candidate, encoding="utf-8") as f:
                    return f.read()
        return "Site is up, but index.html is missing.", 200

@app.route("/chat", methods=["POST"])
def chat():
    if not GROQ_API_KEY:
        return jsonify({"reply": "⚠️ সার্ভারে AI চালু হয়নি (Groq API key সেট করা হয়নি)।"}), 200

    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    
    if not message:
        return jsonify({"reply": "একটা প্রশ্ন লিখুন আগে।"}), 200

    reply = ask_ai(message, history)
    return jsonify({"reply": reply})

# ---------------- AI Logic (শুধু Groq) ----------------

def ask_ai(message, history=None):
    if not GROQ_API_KEY:
        return "দুঃখিত, AI কী সেট করা নেই।"

    try:
        messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        for item in (history or [])[-10:]:
            role = "user" if item.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": (item.get("text") or "")[:2000]})
        messages.append({"role": "user", "content": message[:2000]})

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.1-8b-instant", # Groq এর দ্রুত মডেল
            "messages": messages
        }
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", 
                          headers=headers, json=payload, timeout=30)
        
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        else:
            print("GROQ ERROR:", r.status_code, r.text[:300], flush=True)
            return f"দুঃখিত, Groq এরর দিচ্ছে ({r.status_code})। লগ চেক করুন।"
            
    except Exception as e:
        print("GROQ EXCEPTION:", repr(e), flush=True)
        return "দুঃখিত, এখন উত্তর দিতে পারছি না। একটু পরে আবার চেষ্টা করুন।"

# ---------------- WhatsApp Logic ----------------

def send_whatsapp(to, text):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_ID):
        print("WA SEND SKIPPED: token/phone id missing", flush=True)
        return
    try:
        r = requests.post(
            f"{GRAPH_API}/{WHATSAPP_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text[:4000]}},
            timeout=30,
        )
        debug_state["last_send"] = {"status": r.status_code, "body": r.text[:300]}
        if r.status_code != 200:
            print("WA SEND ERROR:", r.status_code, r.text[:300], flush=True)
    except Exception as e:
        print("WA SEND EXC:", repr(e), flush=True)

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def webhook_receive():
    data = request.get_json(force=True, silent=True) or {}
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    sender = msg.get("from", "")
                    text = (msg.get("text", {}) or {}).get("body", "").strip()
                    if not sender or not text:
                        continue
                    import time as _t
                    debug_state["last_webhook"] = {"at": _t.strftime("%H:%M:%S"), "from": sender[-4:], "text": text[:50]}
                    hist = wa_history.get(sender, [])
                    reply = ask_ai(text, hist)
                    hist = hist + [{"role": "user", "text": text}, {"role": "model", "text": reply}]
                    wa_history[sender] = hist[-10:]
                    send_whatsapp(sender, reply)
    except Exception as e:
        print("WEBHOOK ERROR:", repr(e), flush=True)
    return "ok", 200

# ---------------- Helper Routes ----------------

@app.route("/privacy")
def privacy():
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Privacy Policy</title></head>
<body style="font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; line-height: 1.6;">
<h1>Privacy Policy</h1>
<p><strong>Service:</strong> Tonmoy AI Chat<br><strong>Last updated:</strong> 22 October 2026</p>
<p>We receive your messages to generate replies using Groq AI. We do not sell your data.</p>
<p>Contact: mdtonmoyhossen322@gmail.com</p>
</body></html>""", 200

@app.route("/debug")
def debug():
    return jsonify({
        "groq_key_set": bool(GROQ_API_KEY),
        "token_set": bool(WHATSAPP_TOKEN),
        "phone_id_set": bool(WHATSAPP_PHONE_ID),
        "verify_token_set": bool(WHATSAPP_VERIFY_TOKEN),
        "last_webhook": debug_state.get("last_webhook"),
        "last_send": debug_state.get("last_send"),
    })

@app.route("/health")
def health():
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))