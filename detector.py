"""Voice analysis: preprocessing + anti-spoofing model (with a demo fallback)."""
import os, re
import numpy as np
import librosa

SR = 16000
WIN = 4 * SR
MODEL_ID = os.getenv("VOICEGUARD_MODEL", "MelodyMachine/Deepfake-audio-detection-V2")
FORCE_DEMO = os.getenv("VOICEGUARD_DEMO", "0") == "1"
T_SUSPECT = float(os.getenv("VOICEGUARD_T_SUSPECT", "0.40"))
T_CLONED = float(os.getenv("VOICEGUARD_T_CLONED", "0.70"))
FAKE_LABEL = re.compile(r"\b(fake|spoof\w*|synthetic|ai|deepfake|generated)\b", re.I)


class Detector:
    def __init__(self):
        self.pipe, self.name = None, "demo-heuristic"
        if not FORCE_DEMO:
            try:
                from transformers import pipeline
                self.pipe = pipeline("audio-classification", model=MODEL_ID)
                self.name = MODEL_ID
            except Exception as e:  # missing libs / no internet
                print(f"[VoiceGuard] Model unavailable ({e}). Running in DEMO mode.")

    @property
    def demo(self):
        return self.pipe is None

    def _score_chunk(self, c):
        if self.pipe:
            out = self.pipe({"raw": c, "sampling_rate": SR}, top_k=None)
            return float(sum(o["score"] for o in out if FAKE_LABEL.search(o["label"])))
        # DEMO ONLY: arbitrary heuristic, not a real detector.
        v = float(np.std(librosa.feature.delta(librosa.feature.mfcc(y=c, sr=SR, n_mfcc=13))))
        return float(1 / (1 + np.exp((v - 2.0) * 1.5)))

    def analyze(self, path):
        y, _ = librosa.load(path, sr=SR, mono=True)
        duration = len(y) / SR
        y, (a, _b) = librosa.effects.trim(y, top_db=30)
        if len(y) < SR:
            raise ValueError("Not enough speech found. Use a clip with at least 1 second of speech.")
        offset = a / SR
        chunks = [(i, y[i:i + WIN]) for i in range(0, len(y), WIN)]
        chunks = [c for c in chunks if len(c[1]) >= SR][:15]
        wins = [{"start": round(offset + i / SR, 2),
                 "end": round(offset + (i + len(c)) / SR, 2),
                 "score": round(self._score_chunk(c), 3)} for i, c in chunks]
        s = [w["score"] for w in wins]
        agg = 0.6 * float(np.mean(s)) + 0.4 * float(np.max(s))
        verdict = "cloned" if agg >= T_CLONED else "suspicious" if agg >= T_SUSPECT else "genuine"
        return {"verdict": verdict, "score": round(agg, 3), "windows": wins,
                "duration": round(duration, 2), "model": self.name, "demo": self.demo}
