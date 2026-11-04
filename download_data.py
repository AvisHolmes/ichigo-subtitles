"""Скачивает словари без графического интерфейса и сохраняет выбор в data/settings.json.

Обычно не нужен: при первом запуске программа сама откроет мастер настройки.
Пример: .venv\\Scripts\\python.exe download_data.py --langs ru,de --warodai --yarxi D:\\yarxi\\yarxi.db
Потом:  .venv\\Scripts\\python.exe build_dict.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
import dictionaries as d  # noqa: E402


def main():
    langs = ", ".join(f"{k} ({v['name']})" for k, v in d.LANGS.items() if v["sources"])
    ap = argparse.ArgumentParser(description="Скачать словари / download dictionaries",
                                 epilog=f"Languages with open dictionaries: {langs}")
    ap.add_argument("--data", default=d.DATA, help="папка словарей (по умолчанию data/)")
    ap.add_argument("--langs", help="языки переводов кроме английского, через запятую")
    ap.add_argument("--warodai", action=argparse.BooleanOptionalAction, help="WARODAI (только с ru)")
    ap.add_argument("--yarxi", help="путь к своей копии yarxi.db (только с ru); пустая строка — без Яркси")
    ap.add_argument("--yomitan", action="append", metavar="ZIP:LANG",
                    help="свой словарь Yomitan и язык его переводов, например D:\\ja-ar.zip:ar")
    ap.add_argument("--force", action="store_true", help="перекачать всё заново (обновить словари)")
    a = ap.parse_args()
    s = d.load_settings(a.data)
    if a.langs is not None:
        s["langs"] = ["en"] + [l for l in a.langs.replace(" ", "").split(",") if l in d.LANGS and l != "en"]
    if a.warodai is not None:
        s["warodai"] = a.warodai
    if a.yarxi is not None:
        s["yarxi"] = d.check_yarxi(a.yarxi) if a.yarxi else None
        if a.yarxi and not s["yarxi"]:
            sys.exit(f"не база Яркси / not a Yarxi database: {a.yarxi}")
    if a.yomitan:
        s["yomitan"] = []
        for item in a.yomitan:
            path, _, lang = item.rpartition(":")
            if not d.check_yomitan(path) or lang not in d.LANGS:
                sys.exit(f"не словарь Yomitan или неизвестный язык / bad Yomitan dictionary or language: {item}")
            s["yomitan"].append({"path": os.path.abspath(path), "lang": lang})
    d.save_settings(s, a.data)
    d.download(s, a.data, force=a.force)
    print("OK. Next: .venv\\Scripts\\python.exe build_dict.py")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
