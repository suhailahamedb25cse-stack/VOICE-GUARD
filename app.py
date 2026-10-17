import io, os, sqlite3, uuid
import librosa, numpy as np, soundfile as sf
from flask import Flask, jsonify, render_template, request
from detector import Detector, MODELS, SR

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
DB = os.getenv("VOICEGUARD_DB", "voiceguard.db")
T_FLAG = float(os.getenv("VOICEGUARD_T_FLAG", "0.50"))    # first check flags a chunk
T_HIGH = float(os.getenv("VOICEGUARD_T_HIGH", "0.65"))    # smoothed risk counted as high
det = Detector()
SESS = {}  # session id -> state (audio lives in memory only)


def db():
    con = sqlite3.connect(DB, timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT,
        started_at TEXT DEFAULT CURRENT_TIMESTAMP, seconds REAL, peak REAL, alerts INTEGER, model TEXT)""")
    return con


def level(r):
    return "high" if r >= T_HIGH else "medium" if r >= 0.4 else "low"


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", model=det.name, demo=det.demo, labels=det.labels, models=MODELS)


ADVICE = {
    "low": "No signs of cloning found. For money or access requests, still confirm through a second channel.",
    "medium": "Some signs of synthetic speech. Do not act on this request yet. Call the person back on a number you already know.",
    "high": "This voice is likely AI-generated. Do not share codes or money. Verify through a trusted contact.",
}


@app.post("/api/analyze")
def analyze():
    f = request.files.get("audio")
    if not f:
        return jsonify(error="No audio file received."), 400
    try:
        y, sr = sf.read(io.BytesIO(f.read()), dtype="float32")
    except Exception:
        return jsonify(error="This file could not be decoded. Try a WAV, MP3 or M4A file."), 422
    if y.ndim > 1:
        y = y.mean(1)
    if sr != SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=SR)
    dur = len(y) / SR
    y, (a, _) = librosa.effects.trim(y, top_db=30)
    if len(y) < SR:
        return jsonify(error="Not enough speech found. Use a clip with at least 1 second of speech."), 422
    wins = []
    for i in range(0, len(y), 4 * SR):
        c = y[i:i + 4 * SR]
        if len(c) < SR or len(wins) >= 15:
            continue
        s1 = det.score(c)                                  # first check: this section
        s2, conf, fin = None, False, s1
        if s1 >= T_FLAG:                                   # second check: 2 s more context each side
            s2 = det.score(y[max(0, i - 2 * SR): i + len(c) + 2 * SR])
            conf = s2 >= T_FLAG
            fin = (s1 + s2) / 2 if conf else s2
        wins.append({"start": round((a + i) / SR, 2), "end": round((a + i + len(c)) / SR, 2),
                     "first": round(s1, 3), "second": None if s2 is None else round(s2, 3),
                     "confirmed": conf, "score": round(fin, 3)})
    sc = [w["score"] for w in wins]
    risk = 0.6 * float(np.mean(sc)) + 0.4 * float(np.max(sc))
    lv = level(risk)
    n_conf = sum(w["confirmed"] for w in wins)
    con = db()
    with con:
        con.execute("INSERT INTO checks(kind,name,seconds,peak,alerts,model) VALUES(?,?,?,?,?,?)",
                    ("file", f.filename or "recording", round(dur, 1), round(risk, 3), n_conf, det.name))
    con.close()
    return jsonify(risk=round(risk, 3), level=lv, windows=wins, confirmed=n_conf, duration=round(dur, 2),
                   advice=ADVICE[lv], model=det.name, demo=det.demo)


@app.post("/api/live/start")
def start():
    sid = uuid.uuid4().hex
    SESS[sid] = {"buf": np.zeros(0, "float32"), "risk": 0.0, "peak": 0.0, "alerts": 0, "n": 0,
                 "t0": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    return jsonify(id=sid, demo=det.demo, model=det.name)


@app.post("/api/live/chunk")
def chunk():
    s, f = SESS.get(request.form.get("id")), request.files.get("audio")
    if not s or not f:
        return jsonify(error="Session not found. Start protection again."), 404
    try:
        y, _ = sf.read(io.BytesIO(f.read()), dtype="float32")
    except Exception:
        return jsonify(error="Bad audio chunk."), 422
    if y.ndim > 1:
        y = y.mean(1)
    if float(np.sqrt((y ** 2).mean())) < 0.003:  # silence: nothing to check
        return jsonify(speech=False, risk=round(s["risk"], 3), level=level(s["risk"]))
    s["n"] += 1
    if os.getenv("VOICEGUARD_DEBUG") == "1":  # save what the model hears, to listen for distortion
        os.makedirs("debug_chunks", exist_ok=True)
        sf.write(f"debug_chunks/{s['n']:03d}.wav", y, SR)
    s1 = det.score(y)                                    # first check: this 4 s chunk
    s["buf"] = np.concatenate([s["buf"], y])[-8 * SR:]   # keep last 8 s in memory
    s2, confirmed, final = None, False, s1
    if s1 >= T_FLAG:                                     # second check: last 8 s of context
        s2 = det.score(s["buf"])
        confirmed = s2 >= T_FLAG
        final = (s1 + s2) / 2 if confirmed else s2
        s["alerts"] += int(confirmed)
    s["risk"] = 0.5 * s["risk"] + 0.5 * final
    s["peak"] = max(s["peak"], s["risk"])
    r = lambda v: None if v is None else round(v, 3)
    return jsonify(speech=True, first=r(s1), second=r(s2), confirmed=confirmed,
                   risk=r(s["risk"]), level=level(s["risk"]))


@app.post("/api/live/stop")
def stop():
    s = SESS.pop(request.form.get("id"), None)
    if s:
        con = db()
        with con:
            con.execute("INSERT INTO checks(kind,name,started_at,seconds,peak,alerts,model) VALUES(?,?,?,?,?,?,?)",
                        ("live", "Live call", s["t0"], s["n"] * 4, round(s["peak"], 3), s["alerts"], det.name))
        con.close()
    return jsonify(ok=True)


@app.get("/api/history")
def history():
    con = db()
    rows = [dict(zip(("kind", "name", "started_at", "seconds", "peak", "alerts"), r)) for r in
            con.execute("SELECT kind,name,started_at,seconds,peak,alerts FROM checks ORDER BY id DESC LIMIT 15")]
    con.close()
    return jsonify(rows)


@app.post("/api/model")
def set_model():
    mid = (request.get_json(silent=True) or {}).get("id")
    if mid not in MODELS:
        return jsonify(error="Unknown model."), 400
    try:
        det.load(mid, strict=True)
    except Exception as e:
        return jsonify(error=f"Could not use that model: {str(e)[:200]}"), 422
    return jsonify(model=det.name, demo=det.demo, labels=det.labels)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
