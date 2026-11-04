"""Собирает data/dict.sqlite по data/settings.json (его пишет мастер настройки или download_data.py).

Запуск: .venv\\Scripts\\python.exe build_dict.py [--data DIR]
Обычно не нужен: мастер настройки в программе скачивает и собирает словарь сам.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
import dictionaries  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Сборка словаря / build the dictionary")
    ap.add_argument("--data", default=dictionaries.DATA, help="папка словарей (по умолчанию data/)")
    data = ap.parse_args().data
    dictionaries.build(dictionaries.load_settings(data), data)
