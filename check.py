"""Print the model's raw scores for audio files.
Usage: python check.py <model-id> file1 file2 ...
Example: python check.py MelodyMachine/Deepfake-audio-detection-V2 sugi.ogg voiceguard_ai_male.mp3"""
import sys, librosa
from transformers import pipeline

p = pipeline("audio-classification", model=sys.argv[1])
for f in sys.argv[2:]:
    y, _ = librosa.load(f, sr=16000, mono=True)
    out = p({"raw": y[:16000 * 8], "sampling_rate": 16000}, top_k=None)
    print(f, {o["label"]: round(o["score"], 3) for o in out})
