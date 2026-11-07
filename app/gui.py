"""Итиго (一語一語) как обычная программа: своё окно (WebView2) без браузера и консоли.

Запуск: start.bat (или ярлык на него).
"""
import asyncio
import os
import socket
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "cache")
os.makedirs(os.path.join(CACHE, "tmp"), exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = os.path.join(CACHE, "tmp")

# Под pythonw.exe консоли нет — пишем лог в файл.
if sys.stdout is None or not sys.stdout.isatty():
    _log = open(os.path.join(CACHE, "ichigo.log"), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log
else:
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, HERE)
import webview  # noqa: E402
from aiohttp import web  # noqa: E402

import server  # noqa: E402


def free_port():
    # 8770 — привычный порт; если занят (вторая копия, Anki и т. п.), берём любой свободный
    for port in (8770, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue


def run_server(port, ready, holder):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    a, app = server.make_app()
    holder["app"] = a
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", port).start())
    server.log(f"server on http://127.0.0.1:{port}")
    ready.set()
    loop.run_forever()


class Api:
    """Доступно странице как window.pywebview.api: системный диалог выбора файла."""

    _window = None  # с подчёркиванием — pywebview не отдаёт такие атрибуты странице

    def pick_file(self, kind):
        types = {"yarxi": ("Yarxi (*.db)", "All files (*.*)"),
                 "yomitan": ("Yomitan (*.zip)", "All files (*.*)")}.get(kind, ("All files (*.*)",))
        res = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=types)
        return res[0] if res else ""


def main():
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ichigo.subtitles")
    # без словаря сервер сам откроет мастер настройки (/setup)
    port = free_port()
    ready, holder = threading.Event(), {}
    threading.Thread(target=run_server, args=(port, ready, holder), daemon=True).start()
    ready.wait(60)

    api = Api()
    window = webview.create_window("Ichigo · 一語一語", f"http://127.0.0.1:{port}/", js_api=api,
                                   width=1280, height=860, min_size=(700, 450), background_color="#15161a")
    api._window = window

    def on_closed():
        a = holder.get("app")
        if a:
            a.cap.stop()
        os._exit(0)

    def on_shown():
        # своя иконка в заголовке и на панели задач вместо значка Python
        import ctypes
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, window.title)
        ico = os.path.join(HERE, "ichigo.ico")
        for size, kind in ((16, 0), (32, 1)):  # ICON_SMALL, ICON_BIG
            h = u.LoadImageW(None, ico, 1, size * 2, size * 2, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            if hwnd and h:
                u.SendMessageW(hwnd, 0x80, kind, h)  # WM_SETICON

    window.events.closed += on_closed
    window.events.shown += on_shown
    # Данные WebView2 (размер шрифта и т. п.) — тоже в папке программы
    webview.start(gui="edgechromium", private_mode=False, storage_path=os.path.join(CACHE, "webview"))
    os._exit(0)


if __name__ == "__main__":
    main()
