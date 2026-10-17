# VoiceGuard (live call + file check)

Two modes in one site: **Live call** and **Check a file** (both use the same model and two-step check).
Live mode listens to a call, scores the voice every 4 seconds, double-checks anything suspicious
with more audio context, and alerts you with a risk score. Stack: Flask, librosa, Hugging Face audio-deepfake model, SQLite, plain JS.

## Run
    pip install -r requirements.txt -r requirements-model.txt
    python app.py            # demo mode only: set VOICEGUARD_DEMO=1 first (placeholder scores, not real detection)
Open http://localhost:5000 (use localhost so the browser allows the microphone). Check /api/health shows "demo":false.

## How to use it on a call
- Phone call: put it on speaker near the computer, choose "Microphone".
- Web call (Meet/Zoom/WhatsApp Web): choose "Tab or system audio", pick the call tab, tick "Share tab audio".

## How it decides
1. Browser captures audio, converts to 16 kHz, sends a 4 s chunk to /api/live/chunk.
2. First check: model scores the chunk. Silence is skipped.
3. If score >= 0.50: second check scores the last 8 s of audio. Alert only if the second check agrees.
4. Smoothed risk = running average; low < 40%, medium < 65%, high >= 65%.
5. Audio is kept in memory only; at the end of the call only length, peak risk and alert count are saved.

## Settings (env vars)
VOICEGUARD_MODEL, VOICEGUARD_DEMO, VOICEGUARD_FAKE_LABEL, VOICEGUARD_T_FLAG (0.50), VOICEGUARD_T_HIGH (0.65), VOICEGUARD_DB, PORT.

## File check
Upload any audio file (WAV/MP3/M4A/OGG). It is cut into 4 s sections; suspicious sections get a second check with 2 s extra context on each side. Result: verdict, risk score, and a shaded waveform.
API: POST /api/analyze (multipart `audio`).

## Windows quick start
Double-click `run.bat` (it activates C:\vg, turns demo mode off, and starts the server). Open http://localhost:5000.
Edit run.bat to switch model (`VOICEGUARD_MODEL`), flip labels (`VOICEGUARD_FAKE_LABEL`), or save debug audio (`VOICEGUARD_DEBUG=1`).

## If real voices score as AI
1. Live capture: the browser now resamples to 16 kHz itself, and noise suppression is on (MIC setting at the top of static/app.js).
2. Set VOICEGUARD_DEBUG=1, talk for 20 s, then play the files in debug_chunks/ to hear what the model hears (delete the folder afterwards).
3. Run `python check.py <model-id> real.ogg ai.mp3` to compare raw scores. If the AI clip scores lower than your real voice, labels are inverted: set VOICEGUARD_FAKE_LABEL=\breal\b. If both score high, try another model.

## Pick the best model with your own clips
Put real voices in samples/real and AI voices in samples/ai, then run `python compare_models.py`.
It prints each clip's fake score per model and a summary. Use the model with the best separation:
set VOICEGUARD_MODEL=<model-id> (or edit run.bat). `/api/health` now shows the model's label names.
Set VOICEGUARD_DEBUG=1 to print raw model scores in the terminal for every live chunk.
