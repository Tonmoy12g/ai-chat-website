import os
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

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
    try:
        r = None
        last_status = None
        for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = requests.post(url, params={"key": GEMINI_API_KEY}, json=payload, timeout=45)
            last_status = r.status_code
            if r.status_code == 200:
                break
            print("GEMINI ERROR:", model, r.status_code, r.text[:400], flush=True)
        if r is None or r.status_code != 200:
            return jsonify({"reply": f"দুঃখিত, AI সার্ভার থেকে উত্তর আসেনি (এরর কোড: {last_status})। ওয়েবসাইটের মালিককে জানান।"}), 200
        out = r.json()
        parts = out["candidates"][0]["content"]["parts"]
        reply = "".join(p.get("text", "") for p in parts).strip()
        if not reply:
            reply = "দুঃখিত, উত্তর তৈরি করা যায়নি। আবার চেষ্টা করুন।"
        return jsonify({"reply": reply})
    except Exception as e:
        print("CHAT ERROR:", repr(e), flush=True)
        return jsonify({"reply": "দুঃখিত, সার্ভারে সমস্যা হয়েছে। একটু পরে আবার চেষ্টা করুন।"}), 200


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
