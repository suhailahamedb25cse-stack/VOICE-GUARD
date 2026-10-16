# VoiceGuard

Web app that checks whether a voice recording is real or AI-cloned.
Stack: Flask, librosa, a pretrained Hugging Face audio-deepfake classifier, SQLite, plain HTML/CSS/JS.

## Run (demo mode, no model download)
    pip install -r requirements.txt
    VOICEGUARD_DEMO=1 python app.py          # Windows PowerShell: $env:VOICEGUARD_DEMO=1; python app.py
Open http://localhost:5000. Demo mode uses a placeholder heuristic and is NOT a real detector.

## Run with the real model
    pip install -r requirements.txt -r requirements-model.txt
    python app.py
The first run downloads the model (internet needed). Change it with `VOICEGUARD_MODEL=<hf-model-id>`.
Any Hugging Face `audio-classification` model whose labels include fake/spoof/synthetic works.

## Docker
    docker build -t voiceguard . && docker run -p 5000:5000 voiceguard

## Settings (environment variables)
VOICEGUARD_MODEL, VOICEGUARD_DEMO, VOICEGUARD_T_SUSPECT (0.40), VOICEGUARD_T_CLONED (0.70), VOICEGUARD_DB, PORT.

## API
POST /api/analyze (multipart field `audio`) | GET /api/history | GET /api/health

## Pipeline
Browser decodes audio to 16 kHz mono WAV -> Flask -> trim silence -> 4 s windows -> classifier score per window
-> combined score (0.6 mean + 0.4 max) -> genuine / suspicious / cloned -> result saved to SQLite (audio deleted).
Tune thresholds on your own real and cloned samples before the demo.
