"""Scores a short audio chunk: probability that the voice is AI-generated (0..1)."""
import os, re
import numpy as np
import librosa

SR = 16000
MODEL_ID = os.getenv("VOICEGUARD_MODEL", "MelodyMachine/Deepfake-audio-detection-V2")
MODELS = list(dict.fromkeys([MODEL_ID, "MelodyMachine/Deepfake-audio-detection-V2", "sparshsinghal/deepfakeguard-finetuned",
                             "garystafford/wav2vec2-deepfake-voice-detector",
                             "Gustking/wav2vec2-large-xlsr-deepfake-audio-classification"]))
FORCE_DEMO = os.getenv("VOICEGUARD_DEMO", "0") == "1"
FAKE_LABEL = re.compile(os.getenv("VOICEGUARD_FAKE_LABEL",
                        r"\b(fake|spoof\w*|synthetic|ai|deepfake|generated)\b"), re.I)


class Detector:
    def __init__(self):
        self.pipe, self.name = None, "demo-heuristic"
        if not FORCE_DEMO:
            try:
                self.load(MODEL_ID)
            except Exception as e:
                print(f"[VoiceGuard] Model unavailable ({e}). Running in DEMO mode.")

    def load(self, model_id, strict=False):
        from transformers import pipeline
        p = pipeline("audio-classification", model=model_id)
        names = list(p.model.config.id2label.values())
        if not any(FAKE_LABEL.search(n) for n in names):
            if strict:
                raise ValueError(f"its labels {names} are not recognised as fake/real")
            print(f"[VoiceGuard] Warning: labels {names} not recognised. Set VOICEGUARD_FAKE_LABEL.")
        self.pipe, self.name = p, model_id

    @property
    def labels(self):
        return {str(k): v for k, v in self.pipe.model.config.id2label.items()} if self.pipe else {}

    @property
    def demo(self):
        return self.pipe is None

    def score(self, y):
        y = np.asarray(y, dtype="float32")
        if self.pipe:
            out = self.pipe({"raw": y, "sampling_rate": SR}, top_k=None)
            if os.getenv("VOICEGUARD_DEBUG") == "1":
                print("[raw model output]", {o["label"]: round(o["score"], 3) for o in out})
            return float(sum(o["score"] for o in out if FAKE_LABEL.search(o["label"])))
        # DEMO ONLY: arbitrary heuristic, not a real detector.
        v = float(np.std(librosa.feature.delta(librosa.feature.mfcc(y=y, sr=SR, n_mfcc=13))))
        return float(1 / (1 + np.exp((v - 2.0) * 1.5)))
