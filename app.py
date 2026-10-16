import hashlib, os, sqlite3, tempfile
from flask import Flask, jsonify, render_template, request
from detector import Detector

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
DB = os.getenv("VOICEGUARD_DB", "voiceguard.db")
detector = Detector()

ADVICE = {
    "genuine": "No signs of cloning found. For money or access requests, still confirm through a second channel.",
    "suspicious": "Some signs of synthetic speech. Do not act on this request yet. Call the person back on a number you already know.",
    "cloned": "This voice is likely AI-generated. Do not share codes or money. Hang up and verify through a trusted contact.",
}


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS analyses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, file_hash TEXT, filename TEXT, duration REAL,
        verdict TEXT, score REAL, model TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return con


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify(status="ok", model=detector.name, demo=detector.demo)


@app.post("/api/analyze")
def analyze():
    f = request.files.get("audio")
    if not f:
        return jsonify(error="No audio file received."), 400
    data = f.read()
    suffix = os.path.splitext(f.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        r = detector.analyze(tmp.name)
    except ValueError as e:
        return jsonify(error=str(e)), 422
    except Exception:
        return jsonify(error="This file could not be decoded. Try a WAV, MP3 or M4A file."), 422
    finally:
        os.remove(tmp.name)  # raw audio is never kept
    r["advice"] = ADVICE[r["verdict"]]
    with db() as con:
        con.execute("INSERT INTO analyses(file_hash,filename,duration,verdict,score,model) VALUES(?,?,?,?,?,?)",
                    (hashlib.sha256(data).hexdigest(), f.filename, r["duration"], r["verdict"], r["score"], r["model"]))
    return jsonify(r)


@app.get("/api/history")
def history():
    with db() as con:
        rows = con.execute("SELECT filename,duration,verdict,score,created_at FROM analyses ORDER BY id DESC LIMIT 20")
        return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
