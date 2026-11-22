
import os, re, urllib.parse, requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)
CR_API_TOKEN = os.getenv("CLASH_ROYALE_API_TOKEN", "")
CR_API_BASE = os.getenv("CLASH_ROYALE_API_BASE", "https://api.clashroyale.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

def clean_tag(tag):
    tag = (tag or "").strip().upper().replace(" ", "")
    if not tag.startswith("#"): tag = "#" + tag
    if not re.fullmatch(r"#[0289PYLQGRJCUV]+", tag):
        raise ValueError("Invalid player tag. Use only Clash Royale tag characters.")
    return urllib.parse.quote(tag, safe="")

def cr_get(path):
    if not CR_API_TOKEN:
        return None, ("Add your Clash Royale API token to the server environment first.", 503)
    try:
        r = requests.get(CR_API_BASE + path, headers={"Authorization": "Bearer " + CR_API_TOKEN},
                         timeout=20)
        if r.status_code == 401: return None, ("Clash Royale API token is invalid.", 401)
        if r.status_code == 403: return None, ("API access blocked. Check the IP address allowed for your token.", 403)
        if r.status_code == 404: return None, ("Player or endpoint not found. Check the tag.", 404)
        r.raise_for_status()
        return r.json(), None
    except requests.RequestException as e:
        return None, (f"Clash Royale API request failed: {e}", 502)

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.get("/api/health")
def health():
    return jsonify({"api_token_configured": bool(CR_API_TOKEN), "ai_configured": bool(OPENAI_API_KEY)})

@app.get("/api/player/<path:tag>")
def player(tag):
    try: encoded = clean_tag(tag)
    except ValueError as e: return jsonify({"error": str(e)}), 400
    data, err = cr_get("/players/" + encoded)
    if err: return jsonify({"error": err[0]}), err[1]
    return jsonify(data)

@app.get("/api/battles/<path:tag>")
def battles(tag):
    try: encoded = clean_tag(tag)
    except ValueError as e: return jsonify({"error": str(e)}), 400
    data, err = cr_get("/players/" + encoded + "/battlelog")
    if err: return jsonify({"error": err[0]}), err[1]
    return jsonify(data)

@app.post("/api/coach")
def coach():
    if not OPENAI_API_KEY:
        return jsonify({"error": "Add an OpenAI API key to enable AI-written coaching. Basic stats and deck tools work without it."}), 503
    payload = request.get_json(force=True)
    context = payload.get("context", {})
    prompt = payload.get("question", "Analyze my recent Clash Royale battles. Be specific, honest, and distinguish evidence from guesses.")
    try:
        r = requests.post("https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer " + OPENAI_API_KEY, "Content-Type": "application/json"},
            json={"model": OPENAI_MODEL, "instructions":
              "You are a rigorous Clash Royale strategy coach. Analyze only the supplied data. Battle logs do not reveal exact troop placements, elixir decisions, card cycle, or timing, so never claim to know those. Separate observed facts from hypotheses. Give actionable advice, matchup guidance, and uncertainty.",
              "input": prompt + "\n\nPLAYER DATA:\n" + json.dumps(context)[:45000]},
            timeout=60)
        r.raise_for_status()
        result = r.json()
        text = "".join(x.get("text","") for item in result.get("output",[]) for x in item.get("content",[]) if x.get("type")=="output_text")
        return jsonify({"analysis": text or "No text returned by the AI."})
    except Exception as e:
        return jsonify({"error": "AI request failed: " + str(e)}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
