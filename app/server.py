"""Живые японские субтитры: звук из колонок/наушников (WASAPI loopback) -> Whisper -> разбор.

Запуск: start.bat, затем http://127.0.0.1:8770
"""
import asyncio
import glob
import json
import os
import queue
import re
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Всё кэшируем на E:, а не на C:
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "cache", "hf"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# DLL CUDA из pip-пакетов nvidia-*
for d in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
    os.add_dll_directory(d)
    os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]

import numpy as np
import pyaudiowpatch as pyaudio
from aiohttp import web

import dictionaries
from analyzer import Analyzer

SR = 16000
FRAME = 480  # 30 мс
MODEL = os.environ.get("ICHIGO_MODEL", "large-v3")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Capture:
    """Захват звука с выбранного устройства; отдаёт моно float32 16 кГц."""

    def __init__(self, on_audio):
        self.pa = pyaudio.PyAudio()
        self.on_audio = on_audio
        self.stream = None
        self.device = None

    def refresh(self):
        """Заново перечислить устройства (Bluetooth-наушники в звонке меняют профиль и устройство)."""
        idx = self.device["index"] if self.device else None
        self.stop()
        self.pa.terminate()
        self.pa = pyaudio.PyAudio()
        return idx

    def devices(self):
        out = []
        wasapi = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out = self.pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        for i in range(self.pa.get_device_count()):
            d = self.pa.get_device_info_by_index(i)
            if d["hostApi"] != wasapi["index"] or d["maxInputChannels"] < 1:
                continue
            loop = bool(d.get("isLoopbackDevice"))
            out.append({
                "index": i,
                "name": d["name"],
                "loopback": loop,
                "default": loop and default_out["name"] in d["name"],
            })
        out.sort(key=lambda d: (not d["default"], not d["loopback"], d["name"]))
        return out

    def start(self, index=None):
        self.stop()
        if index is None:
            devs = self.devices()
            index = devs[0]["index"] if devs else None
        if index is None:
            raise RuntimeError("no_devices")  # код, текст подставляет интерфейс
        d = self.pa.get_device_info_by_index(index)
        rate = int(d["defaultSampleRate"])
        ch = max(1, min(2, d["maxInputChannels"]))
        state = {"rest": np.zeros(0, np.float32)}

        def cb(data, frames, info, status):
            x = np.frombuffer(data, np.float32).reshape(-1, ch).mean(axis=1)
            if rate != SR:
                x = np.concatenate([state["rest"], x])
                if rate % SR == 0:
                    k = rate // SR
                    n = len(x) // k * k
                    state["rest"] = x[n:]
                    x = x[:n].reshape(-1, k).mean(axis=1)
                else:
                    n_out = int(len(x) * SR / rate)
                    xs = np.linspace(0, len(x) - 1, n_out)
                    x = np.interp(xs, np.arange(len(x)), x).astype(np.float32)
                    state["rest"] = np.zeros(0, np.float32)
            self.on_audio(x.astype(np.float32))
            return (None, pyaudio.paContinue)

        self.stream = self.pa.open(format=pyaudio.paFloat32, channels=ch, rate=rate, input=True,
                                   input_device_index=index, frames_per_buffer=int(rate * 0.03),
                                   stream_callback=cb)
        self.stream.start_stream()
        self.device = {"index": index, "name": d["name"]}
        log("capture:", d["name"], rate, "Hz", ch, "ch")

    def stop(self):
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class Segmenter:
    """Режет поток на фразы по паузам (энергетический VAD)."""

    def __init__(self):
        self.buf = np.zeros(0, np.float32)
        self.pending = np.zeros(0, np.float32)
        self.speech = []
        self.in_speech = False
        self.silence = 0.0
        self.last_audio = time.time()
        self.threshold = 0.006
        self.pause = 0.7
        self.max_len = 14.0
        self.lock = threading.Lock()
        self.finals = queue.Queue()
        self.seg_id = 0
        self.level = 0.0

    def feed(self, x):
        with self.lock:
            self.last_audio = time.time()
            self.pending = np.concatenate([self.pending, x])
            while len(self.pending) >= FRAME:
                f, self.pending = self.pending[:FRAME], self.pending[FRAME:]
                self._frame(f)

    def _frame(self, f):
        rms = float(np.sqrt(np.mean(f * f)) + 1e-9)
        self.level = 0.9 * self.level + 0.1 * rms
        voiced = rms > self.threshold
        if self.in_speech:
            self.speech.append(f)
            self.silence = 0.0 if voiced else self.silence + FRAME / SR
            dur = len(self.speech) * FRAME / SR
            if self.silence >= self.pause or dur >= self.max_len:
                self._close()
        else:
            self.buf = np.concatenate([self.buf, f])[-int(SR * 0.4):]  # предзахват 0.4 с
            if voiced:
                self.in_speech = True
                self.silence = 0.0
                self.seg_id += 1
                self.speech = [self.buf.copy()]

    def _close(self):
        audio = np.concatenate(self.speech)
        self.in_speech = False
        self.speech = []
        self.buf = np.zeros(0, np.float32)
        if len(audio) > SR * 0.35:
            self.finals.put((self.seg_id, audio))

    def tick(self):
        """WASAPI loopback ничего не шлёт в полной тишине — закрываем фразу по таймеру."""
        with self.lock:
            if self.in_speech and time.time() - self.last_audio > self.pause:
                self._close()

    def current(self):
        with self.lock:
            if not self.in_speech:
                return None, None
            return self.seg_id, np.concatenate(self.speech)


class App:
    def __init__(self):
        self.clients = set()
        self.loop = None
        self.settings = dictionaries.load_settings()
        self.analyzer = None  # нет словаря — сначала мастер настройки (/setup)
        if not dictionaries.needs_setup():
            log("loading dictionary + tokenizer")
            self.analyzer = Analyzer()
        # установка словарей из мастера: idle | running | done | error
        self.job = {"state": "idle", "stage": "", "detail": "", "frac": None, "error": "", "result": None}
        self.seg = Segmenter()
        self.cap = Capture(self.seg.feed)
        self.paused = False
        self.history = []
        self.context = ""
        self.model = None
        # loading | gpu | cpu — текст статуса подставляет интерфейс на своём языке
        self.model_state, self.model_name = "loading", MODEL

    def load_model(self):
        from faster_whisper import WhisperModel
        try:
            log("loading whisper", MODEL, "on cuda")
            self.model = WhisperModel(MODEL, device="cuda", compute_type="float16",
                                      download_root=os.path.join(ROOT, "cache", "hf"))
            self.model_state = "gpu"
        except Exception as e:
            log("cuda failed:", e, "-> cpu small")
            self.model = WhisperModel("small", device="cpu", compute_type="int8",
                                      download_root=os.path.join(ROOT, "cache", "hf"))
            self.model_state, self.model_name = "cpu", "small"
        # прогрев
        list(self.model.transcribe(np.zeros(SR, np.float32), language="ja")[0])
        log("model ready:", self.model_name, self.model_state)
        self.broadcast({"type": "status", **self.status()})

    def status(self):
        return {"model": self.model_name, "model_state": self.model_state, "device": self.cap.device,
                "langs": self.analyzer.dict.langs if self.analyzer else [], "ui": self.settings["ui"],
                "lang_names": {k: v["name"] for k, v in dictionaries.LANGS.items()},
                "gloss": self.settings["gloss"], "paused": self.paused, "threshold": self.seg.threshold,
                "pause": self.seg.pause}

    def transcribe(self, audio, final):
        segs, info = self.model.transcribe(
            audio, language="ja", beam_size=5 if final else 1, best_of=1 if not final else 5,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
            condition_on_previous_text=False, without_timestamps=True,
            initial_prompt=self.context[-120:] or None, temperature=0.0 if not final else [0.0, 0.2, 0.4],
        )
        parts = []
        for s in segs:
            if s.no_speech_prob > 0.6 and s.avg_logprob < -0.8:
                continue
            if s.compression_ratio > 2.6:
                continue
            parts.append(s.text.strip())
        text = "".join(parts).strip()
        if Analyzer.is_hallucination(text):
            return ""
        return text

    def asr_worker(self):
        while self.model is None:
            time.sleep(0.2)
        last_partial = 0
        while True:
            self.seg.tick()
            try:
                sid, audio = self.seg.finals.get(timeout=0.15)
                t0 = time.time()
                text = self.transcribe(audio, final=True)
                if text and self.analyzer:
                    ms = int((time.time() - t0) * 1000)
                    # длинную фразу показываем по предложениям
                    sentences = re.findall(r"[^。？！?!]+[。？！?!]*", text) or [text]
                    for n, sent in enumerate(sentences):
                        res = self.analyzer.analyze(sent.strip())
                        res.update(type="final", id=sid if n == 0 else f"{sid}_{n}", ts=time.strftime("%H:%M:%S"))
                        if n == 0:
                            res.update(dur=round(len(audio) / SR, 1), ms=ms)
                        self.history.append(res)
                        self.broadcast(res)
                    self.history = self.history[-300:]
                    self.context = (self.context + text)[-300:]
                    log(f"[{ms}ms]", text)
                else:
                    self.broadcast({"type": "drop", "id": sid})
                continue
            except queue.Empty:
                pass
            sid, audio = self.seg.current()
            if audio is not None and not self.paused and len(audio) > SR * 0.8 and time.time() - last_partial > 0.9:
                last_partial = time.time()
                text = self.transcribe(audio[-SR * 12:], final=False)
                if text:
                    self.broadcast({"type": "partial", "id": sid, "text": text})

    def broadcast(self, msg):
        if not self.loop:
            return
        data = json.dumps(msg, ensure_ascii=False)
        for ws in list(self.clients):
            asyncio.run_coroutine_threadsafe(ws.send_str(data), self.loop)

    async def ws_handler(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        await ws.send_str(json.dumps({"type": "status", **self.status()}, ensure_ascii=False))
        await ws.send_str(json.dumps({"type": "devices", "list": self.cap.devices()}, ensure_ascii=False))
        await ws.send_str(json.dumps({"type": "history", "items": self.history[-80:]}, ensure_ascii=False))
        try:
            async for m in ws:
                if m.type != web.WSMsgType.TEXT:
                    continue
                msg = json.loads(m.data)
                t = msg.get("type")
                if t == "analyze":
                    text = msg.get("text", "").strip()
                    if text and self.analyzer:
                        res = await asyncio.to_thread(self.analyzer.analyze, text)
                        res.update(type="final", id=f"t{time.time()}", typed=True, ts=time.strftime("%H:%M:%S"))
                        self.history.append(res)
                        self.broadcast(res)
                elif t == "device":
                    try:
                        self.cap.start(int(msg["index"]))
                    except Exception as e:
                        await ws.send_str(json.dumps({"type": "error", "text": str(e)}, ensure_ascii=False))
                    self.broadcast({"type": "status", **self.status()})
                elif t == "refresh":
                    await asyncio.to_thread(self.cap.refresh)
                    try:
                        self.cap.start(None)  # текущий выход Windows по умолчанию
                    except Exception as e:
                        await ws.send_str(json.dumps({"type": "error", "text": str(e)}, ensure_ascii=False))
                    self.broadcast({"type": "devices", "list": self.cap.devices()})
                    self.broadcast({"type": "status", **self.status()})
                elif t == "pause":
                    self.paused = bool(msg.get("value"))
                    if self.paused:
                        self.cap.stop()
                        self.cap.device = None
                    else:
                        self.cap.start(msg.get("index"))
                    self.broadcast({"type": "status", **self.status()})
                elif t == "settings":
                    if "threshold" in msg:
                        self.seg.threshold = float(msg["threshold"])
                    if "pause" in msg:
                        self.seg.pause = float(msg["pause"])
                    self.broadcast({"type": "status", **self.status()})
                elif t == "clear":
                    self.history = []
                    self.context = ""
                elif t == "prefs":  # язык интерфейса и подписей — запоминаем между запусками
                    if msg.get("ui") in ("en", "ru"):
                        self.settings["ui"] = msg["ui"]
                    if isinstance(msg.get("gloss"), str):
                        self.settings["gloss"] = msg["gloss"]
                    dictionaries.save_settings(self.settings)
        finally:
            self.clients.discard(ws)
        return ws

    # ------------------------------------------------ мастер настройки словарей

    def setup_info(self):
        langs = {k: {**v, "available": bool(v["sources"])} for k, v in dictionaries.LANGS.items()}
        yarxi = os.path.join(dictionaries.DATA, "yarxi.db")
        return {"settings": self.settings, "langs": langs, "sources": dictionaries.SOURCE_INFO,
                "installed": self.analyzer.dict.langs if self.analyzer else [],
                "first_run": self.analyzer is None, "yarxi_default": yarxi if os.path.exists(yarxi) else "",
                "job": self.job, "model": self.model_name, "model_state": self.model_state}

    def run_setup(self, s, force):
        def report(stage, detail="", frac=None):
            self.job.update(stage=stage, detail=detail, frac=frac)

        try:
            data = dictionaries.DATA
            dictionaries.download(s, data, report, force=force)
            new = os.path.join(data, "dict.sqlite.new")
            self.job["result"] = dictionaries.build(s, data, out=new, report=report)
            # подменяем словарь на лету: старый закрыть, новый открыть
            old, self.analyzer = self.analyzer, None
            if old:
                old.dict.close()
            os.replace(new, os.path.join(data, "dict.sqlite"))
            self.analyzer = Analyzer()
            self.job.update(state="done", stage="done")
            log("dictionary ready:", self.job["result"])
            self.broadcast({"type": "status", **self.status()})
        except Exception as e:
            log("setup failed:", repr(e))
            self.job.update(state="error", error=f"{type(e).__name__}: {e}")
            if self.analyzer is None and not dictionaries.needs_setup():
                self.analyzer = Analyzer()

    async def api_setup_get(self, request):
        return web.json_response(self.setup_info())

    async def api_setup_post(self, request):
        if self.job["state"] == "running":
            return web.json_response({"error": "busy"}, status=409)
        body = await request.json()
        langs = ["en"] + [l for l in body.get("langs", []) if l in dictionaries.LANGS and l != "en"]
        s = dict(self.settings, langs=langs, warodai=bool(body.get("warodai")) and "ru" in langs)
        if body.get("ui") in ("en", "ru"):
            s["ui"] = body["ui"]
        s["yarxi"] = dictionaries.check_yarxi(body.get("yarxi") or "") if "ru" in langs else None
        if body.get("yarxi") and "ru" in langs and not s["yarxi"]:
            return web.json_response({"error": "yarxi"}, status=400)
        s["yomitan"] = []
        for y in body.get("yomitan", []):
            if not dictionaries.check_yomitan(y.get("path", "")) or y.get("lang") not in dictionaries.LANGS:
                return web.json_response({"error": "yomitan", "path": y.get("path")}, status=400)
            s["yomitan"].append({"path": os.path.abspath(y["path"]), "lang": y["lang"]})
        # подписи — на языке интерфейса при первой установке или если прежнего языка больше нет
        if self.analyzer is None or s["gloss"] not in langs + [y["lang"] for y in s["yomitan"]]:
            s["gloss"] = s["ui"] if s["ui"] in langs else "en"
        self.settings = s
        dictionaries.save_settings(s)
        self.job = {"state": "running", "stage": "start", "detail": "", "frac": None, "error": "", "result": None}
        threading.Thread(target=self.run_setup, args=(s, bool(body.get("force"))), daemon=True).start()
        return web.json_response({"ok": True})

    async def api_prefs(self, request):
        """Язык интерфейса из первого шага мастера — сразу, ещё до установки словарей."""
        body = await request.json()
        if body.get("ui") in ("en", "ru"):
            self.settings["ui"] = body["ui"]
            dictionaries.save_settings(self.settings)
        return web.json_response({"ok": True})

    async def api_check(self, request):
        """Проверка пути к Яркси / словарю Yomitan, пока пользователь его вводит."""
        body = await request.json()
        path = body.get("path", "")
        if body.get("kind") == "yarxi":
            found = dictionaries.check_yarxi(path)
            return web.json_response({"ok": bool(found), "path": found})
        title = dictionaries.check_yomitan(path)
        return web.json_response({"ok": bool(title), "title": title})

    async def level_task(self):
        while True:
            await asyncio.sleep(0.15)
            lv = self.seg.level
            self.broadcast({"type": "level", "v": round(lv, 4), "speech": self.seg.in_speech})

    async def on_startup(self, app):
        self.loop = asyncio.get_running_loop()
        threading.Thread(target=self.load_model, daemon=True).start()
        threading.Thread(target=self.asr_worker, daemon=True).start()
        try:
            self.cap.start()
        except Exception as e:
            log("capture failed:", e)
        asyncio.create_task(self.level_task())


def make_app():
    a = App()

    async def index(request):
        if a.analyzer is None:  # первый запуск: словаря ещё нет
            raise web.HTTPFound("/setup")
        return web.FileResponse(os.path.join(HERE, "static", "index.html"))

    async def setup_page(request):
        return web.FileResponse(os.path.join(HERE, "static", "setup.html"))

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/api/setup", a.api_setup_get)
    app.router.add_post("/api/setup", a.api_setup_post)
    app.router.add_post("/api/prefs", a.api_prefs)
    app.router.add_post("/api/check", a.api_check)
    app.router.add_get("/ws", a.ws_handler)
    app.router.add_static("/static", os.path.join(HERE, "static"))
    app.on_startup.append(a.on_startup)
    return a, app


def main():
    a, app = make_app()
    port = int(os.environ.get("ICHIGO_PORT", "8770"))
    log(f"open http://127.0.0.1:{port}")
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
