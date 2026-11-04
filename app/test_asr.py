"""Проверка распознавания на wav-файле: python test_asr.py file.wav"""
import glob
import os
import sys
import time
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "cache", "hf"))
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
for d in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
    os.add_dll_directory(d)
    os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

import numpy as np
from faster_whisper import WhisperModel

sys.stdout.reconfigure(encoding="utf-8")
w = wave.open(sys.argv[1])
x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
if w.getnchannels() > 1:
    x = x.reshape(-1, w.getnchannels()).mean(1)
sr = w.getframerate()
if sr != 16000:
    x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)), np.arange(len(x)), x).astype(np.float32)
t = time.time()
m = WhisperModel(os.environ.get("ICHIGO_MODEL", "large-v3"), device="cuda", compute_type="float16",
                 download_root=os.path.join(ROOT, "cache", "hf"))
print("load", round(time.time() - t, 1), "s")
t = time.time()
segs, _ = m.transcribe(x, language="ja", beam_size=5, vad_filter=True)
print("".join(s.text for s in segs), "|", round(time.time() - t, 2), "s for", round(len(x) / 16000, 1), "s audio")
