import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# API Key নেওয়া হচ্ছে এবং মেসেজে কোনো বাড়তি স্পেস বা কোটেশন (" বা ') থাকলে তা পরিষ্কার করা হচ্ছে
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip().strip('"').strip("'")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "").strip()
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "").strip()
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()
GRAPH_API = "https://graph.facebook.com/v21.0"

# WhatsApp ব্যবহারকারীদের ছোট কথোপকথনের ইতিহাস (সার্ভার রিস্টার্টে মুছে যাবে)
wa_history = {}

# ডিবাগ: শেষ webhook মেসেজ ও শেষ পাঠানোর ফলাফল (শুধু অবস্থা, কোনো গোপন তথ্য না)
debug_state = {"last_webhook": None, "last_send": None}

SYSTEM_INSTRUCTION = (
    "You are a friendly and helpful AI assistant on a public website. "
    "Answer any question the user asks, clearly and helpfully. "
    "Always reply in the same language the user writes in (Bangla or English). "
    "Keep answers accurate; if you are unsure about something, say so honestly."
)

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
        return "Site is up, but index.html is missing. Check the templates folder.", 200

@app.route("/chat", methods=["POST"])
def chat():
    if not GEMINI_API_KEY:
        return jsonify({"reply": "⚠️ সার্ভারে AI এখনো চালু হয়নি (API key সেট করা হয়নি)। ওয়েবসাইটের মালিককে জানান।"}), 200

    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    if not message:
        return jsonify({"reply": "একটা প্রশ্ন লিখুন আগে।"}), 200
    if len(message) > 2000:
        message = message[:2000]

    contents = []
    for item in history[-10:]:
        role = "user" if item.get("role") == "user" else "model"
        text = (item.get("text") or "")[:2000]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
    }

    # আপডেট করা মডেল লিস্ট (২.৫ এর বদলে ৩.৮ এবং ৩.৬ ব্যবহার করা হয়েছে)
    models_to_try = [MODEL, "gemini-3.8-flash", "gemini-3.6-flash"]
    # ডুপ্লিকেট নাম থাকলে বাদ দেওয়া হচ্ছে
    models_to_try = list(dict.fromkeys(models_to_try))

    try:
        r = None
        first_status = None
        first_detail = ""

        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=45)
            
            if r.status_code == 200:
                break
                
            print("GEMINI ERROR:", model, r.status_code, r.text[:400], flush=True)
            
            if first_status is None:
                first_status = r.status_code
                try:
                    first_detail = r.json().get("error", {}).get("message", "")[:200]
                except Exception:
                    first_detail = r.text[:200]

        if r is None or r.status_code != 200:
            return jsonify({"reply": f"দুঃখিত, AI সার্ভার থেকে উত্তর আসেনি (এরর {first_status}: {first_detail})।"}), 200

        out = r.json()
        parts = out.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        reply = "".join(p.get("text", "") for p in parts).strip()
        if not reply:
            reply = "দুঃখিত, উত্তর তৈরি করা যায়নি। আবার চেষ্টা করুন।"
        return jsonify({"reply": reply})
    except Exception as e:
        print("CHAT ERROR:", repr(e), flush=True)
        return jsonify({"reply": "দুঃখিত, সার্ভারে সমস্যা হয়েছে। একটু পরে আবার চেষ্টা করুন।"}), 200

def ask_ai(message, history=None):
    """Gemini থেকে উত্তর আনে — ওয়েবসাইট চ্যাট আর WhatsApp দুটোই ব্যবহার করে।"""
    if not GEMINI_API_KEY:
        return "দুঃখিত, AI এখনো চালু হয়নি।"
    history = history or []
    contents = []
    for item in history[-10:]:
        role = "user" if item.get("role") == "user" else "model"
        text = (item.get("text") or "")[:2000]
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message[:2000]}]})
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
    }
    models_to_try = list(dict.fromkeys([MODEL, "gemini-3.8-flash", "gemini-3.6-flash"]))
    try:
        for model in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=45)
            if r.status_code == 200:
                out = r.json()
                parts = out.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                reply = "".join(p.get("text", "") for p in parts).strip()
                if reply:
                    return reply
            else:
                print("GEMINI ERROR (wa):", model, r.status_code, r.text[:300], flush=True)
    except Exception as e:
        print("ASK_AI ERROR:", repr(e), flush=True)
    return "দুঃখিত, এখন উত্তর দিতে পারছি না। একটু পরে আবার চেষ্টা করুন।"


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


@app.route("/privacy")
def privacy():
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy Policy - Tonmoy AI Chat</title></head>
<body style="font-family: Arial, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; line-height: 1.6; color: #222;">
<h1>Privacy Policy</h1>
<p><strong>Service:</strong> Tonmoy AI Chat (website and WhatsApp assistant)<br>
<strong>Last updated:</strong> 22 October 2026</p>
<h2>What we collect</h2>
<p>When you chat with our website assistant or WhatsApp number, we receive the messages you send and, on WhatsApp, your phone number so we can reply to you.</p>
<h2>How we use it</h2>
<p>Your messages are sent to Google's Gemini AI service to generate a reply. We use your messages and phone number only to answer your questions and operate this chat service. We do not sell your personal information to anyone.</p>
<h2>Data retention</h2>
<p>Conversation history is kept only in temporary server memory so the assistant can follow the conversation, and it is cleared when the server restarts. We do not keep a permanent database of your chats.</p>
<h2>Third parties</h2>
<p>This service uses Meta's WhatsApp Business Platform to receive and send WhatsApp messages, and Google's Gemini API to generate answers. Their own privacy policies also apply.</p>
<h2>Contact</h2>
<p>Questions about this policy: mdtonmoyhossen322@gmail.com</p>
</body></html>""", 200


@app.route("/debug")
def debug():
    return jsonify({
        "token_set": bool(WHATSAPP_TOKEN),
        "phone_id_set": bool(WHATSAPP_PHONE_ID),
        "verify_token_set": bool(WHATSAPP_VERIFY_TOKEN),
        "gemini_key_set": bool(GEMINI_API_KEY),
        "last_webhook": debug_state.get("last_webhook"),
        "last_send": debug_state.get("last_send"),
    })


@app.route("/health")
def health():
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))