"""Compare detector models on YOUR clips, then pick the one that separates real from AI best.
1. Put real voices in samples/real and AI-generated voices in samples/ai (WAV, MP3 or OGG).
2. Run:  python compare_models.py            (or:  python compare_models.py model-id-1 model-id-2)
Needs internet the first time (models download). Models that fail to load are skipped."""
import glob, os, re, sys
import numpy as np, librosa
from transformers import pipeline

SR = 16000
MODELS = sys.argv[1:] or [
    "MelodyMachine/Deepfake-audio-detection-V2",
    "sparshsinghal/deepfakeguard-finetuned",
    "garystafford/wav2vec2-deepfake-voice-detector",
    "Gustking/wav2vec2-large-xlsr-deepfake-audio-classification",
]
FAKE = re.compile(r"\b(fake|spoof\w*|synthetic|ai|deepfake|generated)\b", re.I)


def load(folder):
    items = []
    for f in sorted(glob.glob(os.path.join("samples", folder, "*"))):
        if f.endswith(".txt"):
            continue
        try:
            items.append((os.path.basename(f), librosa.load(f, sr=SR, mono=True)[0]))
        except Exception as e:
            print(f"  skipped {f}: {str(e)[:80]}")
    return items


def fake_score(p, y):
    vals = []
    for i in range(0, len(y), 4 * SR):
        c = y[i:i + 4 * SR]
        if len(c) < SR:
            continue
        labs = {o["label"]: o["score"] for o in p({"raw": c, "sampling_rate": SR}, top_k=None)}
        hit = [v for k, v in labs.items() if FAKE.search(k)]
        if not hit:
            return None, list(labs)
        vals.append(sum(hit))
        if len(vals) >= 3:
            break
    return (float(np.mean(vals)) if vals else None), None


real, ai = load("real"), load("ai")
if not real or not ai:
    sys.exit("Put audio files in samples/real and samples/ai first.")

for m in MODELS:
    print(f"\n=== {m}")
    try:
        p = pipeline("audio-classification", model=m)
    except Exception as e:
        print("  could not load:", str(e)[:150]); continue
    sc, bad = {"real": [], "ai": []}, None
    for kind, items in (("real", real), ("ai", ai)):
        for name, y in items:
            s, labs = fake_score(p, y)
            if s is None:
                bad = labs or bad; continue
            sc[kind].append(s); print(f"  {kind:4} {name[:32]:32} fake score = {s:.2f}")
    if not sc["real"] or not sc["ai"]:
        print("  labels not recognised:", bad, "-> send these label names to Claude" if bad else ""); continue
    r, a = np.array(sc["real"]), np.array(sc["ai"])
    acc = (np.sum(r < 0.5) + np.sum(a >= 0.5)) / (len(r) + len(a))
    print(f"  SUMMARY  real avg {r.mean():.2f} | ai avg {a.mean():.2f} | correct at 0.5: {acc:.0%}")
