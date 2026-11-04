"""Словари: какие есть, скачивание и сборка data/dict.sqlite.

Общий код для мастера настройки (static/setup.html через server.py) и консольных
download_data.py / build_dict.py.

Английский JMdict обязателен: это основа (заголовки, части речи, пометки «обычно каной»).
Переводы на другие языки цепляются к его статьям: из JMdict, из Wiktionary (выгрузки kaikki.org)
и из словарей Yomitan, которые пользователь подключил сам. WARODAI и Яркси — для русского.
Всё скачанное и собранное лежит в data/ (или ICHIGO_DATA), на диск C ничего не пишется.
"""
import glob
import json
import os
import re
import shutil
import sqlite3
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile

import jaconv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("ICHIGO_DATA") or os.path.join(ROOT, "data")

JMDICT_API = "https://api.github.com/repos/scriptin/jmdict-simplified/releases/latest"
WARODAI_ZIP = "https://github.com/warodai/warodai-source/archive/refs/heads/master.zip"
KAIKKI = "https://kaikki.org/"

# Языки переводов. sources — открытые словари, которые скачиваются сами
# (jmdict:<код jmdict-simplified>, wikt:<раздел Wiktionary>); coverage — доля частотных слов JMdict
# (пометка common) с переводом после сборки, % (ноябрь 2026); size — примерный объём скачивания, МБ.
# Языки без sources: открытого японского словаря нет — английский + свой словарь Yomitan.
LANGS = {
    "en": {"name": "English", "sources": ["jmdict:eng"], "coverage": 100, "size": 12},
    "ru": {"name": "Русский", "sources": ["jmdict:rus"], "coverage": 82, "size": 4},
    "es": {"name": "Español", "sources": ["jmdict:spa"], "coverage": 70, "size": 2},
    "zh-Hans": {"name": "中文（简体）", "sources": ["wikt:zh"], "coverage": 40, "size": 127},
    "zh-Hant": {"name": "中文（繁體）", "sources": ["wikt:zh"], "coverage": 40, "size": 127},
    "ko": {"name": "한국어", "sources": ["wikt:ko"], "coverage": 31, "size": 8},
    "fr": {"name": "Français", "sources": ["jmdict:fre", "wikt:fr"], "coverage": 62, "size": 88},
    "de": {"name": "Deutsch", "sources": ["jmdict:ger"], "coverage": 96, "size": 7},
    # ещё языки JMdict — небольшие, в мастере под «Ещё языки»
    "nl": {"name": "Nederlands", "sources": ["jmdict:dut"], "coverage": 77, "size": 3, "more": True},
    "hu": {"name": "Magyar", "sources": ["jmdict:hun"], "coverage": 66, "size": 2, "more": True},
    "sv": {"name": "Svenska", "sources": ["jmdict:swe"], "coverage": 22, "size": 1, "more": True},
    "sl": {"name": "Slovenščina", "sources": ["jmdict:slv"], "coverage": 35, "size": 1, "more": True},
    # открытых японских словарей нет — только свой словарь Yomitan
    "it": {"name": "Italiano", "sources": []},
    "vi": {"name": "Tiếng Việt", "sources": []},
    "ar": {"name": "العربية", "sources": []},
    "he": {"name": "עברית", "sources": []},
    "id": {"name": "Bahasa Indonesia", "sources": []},
    "uk": {"name": "Українська", "sources": []},
}
# Японские статьи из разделов Wiktionary на kaikki.org (у китайского раздела два заголовка: 日语 и 日語)
WIKT = {
    "fr": ["frwiktionary/Japonais/kaikki.org-dictionary-Japonais.jsonl"],
    "ko": ["kowiktionary/일본어/kaikki.org-dictionary-일본어.jsonl"],
    "zh": ["zhwiktionary/日语/kaikki.org-dictionary-日语.jsonl",
           "zhwiktionary/日語/kaikki.org-dictionary-日語.jsonl"],
}
SOURCE_INFO = {
    "jmdict": {"name": "JMdict", "license": "CC BY-SA 4.0 © EDRDG",
               "url": "https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project"},
    "wikt": {"name": "Wiktionary", "license": "CC BY-SA 4.0 / GFDL (kaikki.org)", "url": "https://kaikki.org/"},
    "warodai": {"name": "WARODAI", "license": "CC BY-NC-ND 3.0", "url": "https://github.com/warodai/warodai-source"},
    "yarxi": {"name": "Yarxi", "license": "", "url": "https://www.yarxi.ru/"},
}

DEFAULT_SETTINGS = {"ui": "en", "gloss": "en", "langs": ["en"], "warodai": False, "yarxi": None, "yomitan": []}

JP_RE = re.compile(r"[぀-ヿ㐀-鿿々〆ヶ]")
KANJI_RE = re.compile(r"[㐀-鿿豈-﫿々〆ヶ]")


def hira(s):
    return jaconv.kata2hira(s or "")


# ---------------------------------------------------------------- настройки

def settings_path(data=DATA):
    return os.path.join(data, "settings.json")


def load_settings(data=DATA):
    s = dict(DEFAULT_SETTINGS)
    path = settings_path(data)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            s.update(json.load(fh))
    elif os.path.exists(os.path.join(data, "dict.sqlite")):
        s.update(legacy_settings(data))  # сборка до мастера настройки — берём то, что скачано
    if "en" not in s["langs"]:
        s["langs"] = ["en"] + s["langs"]
    return s


def save_settings(s, data=DATA):
    os.makedirs(data, exist_ok=True)
    with open(settings_path(data), "w", encoding="utf-8") as fh:
        json.dump(s, fh, ensure_ascii=False, indent=1)


def legacy_settings(data):
    codes = {src.split(":")[1]: lang for lang, v in LANGS.items() for src in v["sources"] if src.startswith("jmdict:")}
    langs = [codes[os.path.basename(f).split("-")[1]] for f in glob.glob(os.path.join(data, "jmdict-*-[0-9]*.json"))
             if os.path.basename(f).split("-")[1] in codes]
    yarxi = os.path.join(data, "yarxi.db")
    return {"langs": sorted(set(langs), key=list(LANGS).index),
            "warodai": os.path.isdir(os.path.join(data, "warodai")),
            "yarxi": yarxi if os.path.exists(yarxi) else None}


def needs_setup(data=DATA):
    return not os.path.exists(os.path.join(data, "dict.sqlite"))


def check_yarxi(path):
    """Путь к yarxi.db (можно указать папку) или None, если это не база Яркси."""
    if not path:
        return None
    if os.path.isdir(path):
        path = os.path.join(path, "yarxi.db")
    try:
        db = sqlite3.connect(f"file:{urllib.parse.quote(os.path.abspath(path))}?mode=ro", uri=True)
        db.execute("SELECT Uncd, RusNick FROM Kanji LIMIT 1")
        db.close()
        return os.path.abspath(path)
    except sqlite3.Error:
        return None


def check_yomitan(path):
    """Название словаря Yomitan (.zip с index.json и term_bank_*.json) или None."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if not any(re.search(r"term_bank_\d+\.json$", n) for n in names):
                return None
            index = json.loads(zf.read("index.json")) if "index.json" in names else {}
            return index.get("title") or os.path.splitext(os.path.basename(path))[0]
    except (OSError, zipfile.BadZipFile, ValueError, KeyError):
        return None


def print_report(stage, detail="", frac=None):
    print(f"{stage}: {detail}" + (f" {frac * 100:.0f}%" if frac is not None else ""), flush=True)


# ---------------------------------------------------------------- скачивание

def _fetch(url, dest, report, detail):
    """Качает url в dest (через .part), сообщая долю скачанного."""
    req = urllib.request.Request(url, headers={"User-Agent": "ichigo"})
    tmp = dest + ".part"
    last = 0
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if time.time() - last > 0.3:
                last = time.time()
                report("download", detail, done / total if total else None)
    os.replace(tmp, dest)
    report("download", detail, 1.0)


def jmdict_file(data, code):
    # jmdict-eng-3.6.2.json и т. п. (не *-common-*); берём самую свежую версию
    files = sorted(glob.glob(os.path.join(data, f"jmdict-{code}-[0-9]*.json")))
    return files[-1] if files else None


def wikt_files(data, section):
    return [os.path.join(data, "wiktionary", f"{section}-{i}.jsonl") for i in range(len(WIKT[section]))]


def needed_sources(s):
    srcs = ["jmdict:eng"]
    for lang in s["langs"]:
        srcs += [x for x in LANGS.get(lang, {}).get("sources", []) if x not in srcs]
    return srcs


def download(s, data=DATA, report=print_report, force=False):
    """Скачивает недостающие исходники под настройки s (force — перекачать всё заново)."""
    os.makedirs(data, exist_ok=True)
    dl = os.path.join(data, "_download")
    os.makedirs(dl, exist_ok=True)
    srcs = needed_sources(s)
    jm = [x.split(":")[1] for x in srcs if x.startswith("jmdict:") and (force or not jmdict_file(data, x.split(":")[1]))]
    if jm:
        report("download", "JMdict", None)
        with urllib.request.urlopen(urllib.request.Request(JMDICT_API, headers={"User-Agent": "ichigo"}), timeout=60) as r:
            rel = json.load(r)
        for code in jm:
            prefix = f"jmdict-{code}-"
            asset = next(a for a in rel["assets"] if a["name"].startswith(prefix)
                         and a["name"][len(prefix)].isdigit() and a["name"].endswith(".json.tgz"))
            tgz = os.path.join(dl, asset["name"])
            _fetch(asset["browser_download_url"], tgz, report, f"JMdict ({code})")
            report("unpack", f"JMdict ({code})", None)
            old = glob.glob(os.path.join(data, f"jmdict-{code}-[0-9]*.json"))
            with tarfile.open(tgz) as tf:
                for m in tf.getmembers():
                    if m.isfile() and m.name.endswith(".json") and "/" not in m.name and ".." not in m.name:
                        tf.extract(m, data)
                        old = [f for f in old if os.path.basename(f) != m.name]
            for f in old:  # прежние версии
                os.remove(f)
            os.remove(tgz)
    for src in srcs:
        if not src.startswith("wikt:"):
            continue
        section = src.split(":")[1]
        os.makedirs(os.path.join(data, "wiktionary"), exist_ok=True)
        for url, path in zip(WIKT[section], wikt_files(data, section)):
            if force or not os.path.exists(path):
                _fetch(KAIKKI + urllib.parse.quote(url), path, report, f"Wiktionary ({section})")
    if "ru" in s["langs"] and s.get("warodai") and (force or not os.path.isdir(os.path.join(data, "warodai"))):
        zpath = os.path.join(dl, "warodai.zip")
        _fetch(WARODAI_ZIP, zpath, report, "WARODAI")
        report("unpack", "WARODAI", None)
        dst = os.path.join(data, "warodai")
        shutil.rmtree(dst, ignore_errors=True)
        with zipfile.ZipFile(zpath) as zf:
            for name in zf.namelist():
                if ".." in name or name.startswith(("/", "\\")):
                    continue
                zf.extract(name, dst)
        os.remove(zpath)
    shutil.rmtree(dl, ignore_errors=True)


# ---------------------------------------------------------------- WARODAI

HEAD_RE = re.compile(r"^(?P<kana>[^【(〔]+)(?:【(?P<kanji>[^】]*)】)?\s*\((?P<rd>[^)]*)\)\s*〔(?P<id>[^〕]+)〕")
REF_RE = re.compile(r'<a href="#([\d-]+)">(.*?)</a>')
CYR_RE = re.compile(r"[А-Яа-яЁё]")
SENSE_RE = re.compile(r"^\s*(\d+)\)\s*:?\s*")


def clean_html(s):
    s = REF_RE.sub(r"\2", s)
    s = re.sub(r"</?(?!i>|/i>)[a-z][^>]*>", "", s)
    return s.strip()


def split_forms(s):
    # 有り難う･有難う / 行く・往く ; убираем пометки вроде (…) и ×
    forms = []
    for f in re.split(r"[･・,，、;]", s or ""):
        f = re.sub(r"[×△◇▽〈〉《》]", "", f).strip()
        f = re.sub(r"\(.*?\)", "", f)
        if f:
            forms.append(f)
    return forms


def is_example(line):
    """Строка-пример: японский текст идёт раньше кириллицы и это не «～な …»."""
    body = SENSE_RE.sub("", line)
    if body.startswith(("～", "〜")):
        return False
    c = CYR_RE.search(body)
    j = JP_RE.search(body)
    if not j:
        return False
    return c is None or j.start() < c.start()


def parse_warodai(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    m = HEAD_RE.match(lines[0])
    if not m:
        return None
    kana = split_forms(m.group("kana"))
    kanji = split_forms(m.group("kanji"))
    senses, examples, refs = [], [], []
    for raw in lines[1:]:
        for rid, _ in REF_RE.findall(raw):
            refs.append(rid)
        line = clean_html(raw)
        if is_example(line):
            examples.append(line)
            continue
        sm = SENSE_RE.match(line)
        if sm:
            line = line[sm.end():]
        line = line.rstrip(";").strip()
        if line:
            senses.append(line)
    return {
        "id": m.group("id"),
        "kana": kana,
        "kanji": kanji,
        "senses": senses,
        "examples": examples[:6],
        "ref": refs[0] if refs and len(senses) <= 1 and "см." in (senses[0] if senses else "") else None,
    }


# ---------------------------------------------------------------- Wiktionary и Yomitan

SKIP_POS = {"character", "romanization", "symbol", "name", "proper noun", "unknown"}


def ruby_reading(form, ruby):
    """「生存する」 + [["生","せい"],["存","ぞん"]] -> せいぞんする."""
    out = form
    for base, rt in ruby or []:
        out = out.replace(base, rt, 1)
    return hira(out) if not KANJI_RE.search(out) else ""


def wikt_records(path):
    """(слово, {чтения}, [значения]) из выгрузки kaikki.org."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            word = d.get("word", "")
            if d.get("lang_code") != "ja" or d.get("pos") in SKIP_POS or not JP_RE.search(word):
                continue
            glosses = []
            for s in d.get("senses", []):
                tags = s.get("tags", [])
                g = (s.get("glosses") or [""])[-1].strip()
                if g and "{{" not in g and "form-of" not in tags and "alt-of" not in tags and g not in glosses:
                    glosses.append(g[:300])
            if not glosses:
                continue
            readings = set()
            for f in d.get("forms", []):
                if "canonical" in f.get("tags", []) and f.get("ruby"):
                    r = ruby_reading(f.get("form", ""), f["ruby"])
                    if r:
                        readings.add(r)
                elif {"hiragana", "kana"} & set(f.get("tags", [])) and not KANJI_RE.search(f.get("form", "")):
                    readings.add(hira(f["form"]))
            if not KANJI_RE.search(word):
                readings.add(hira(word))
            yield word, readings, glosses


BLOCK_TAGS = {"div", "li", "p", "tr", "ol", "ul", "table", "details", "summary"}


def _sc_text(c):
    """Текст из structured-content Yomitan."""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(_sc_text(x) for x in c)
    if isinstance(c, dict):
        if c.get("tag") == "br":
            return "\n"
        inner = _sc_text(c.get("content"))
        return inner + "\n" if c.get("tag") in BLOCK_TAGS else inner
    return ""


def yomitan_records(path):
    with zipfile.ZipFile(path) as zf:
        for name in sorted(zf.namelist()):
            if not re.search(r"term_bank_\d+\.json$", name):
                continue
            for row in json.loads(zf.read(name)):
                term, reading, glossary = row[0], row[1], row[5]
                glosses = []
                for g in glossary:
                    if isinstance(g, str):
                        text = g
                    elif isinstance(g, dict) and g.get("type") == "text":
                        text = g.get("text", "")
                    elif isinstance(g, dict) and g.get("type") == "structured-content":
                        text = _sc_text(g.get("content"))
                    else:
                        continue  # картинки, формы спряжения
                    for part in text.split("\n"):
                        part = part.strip(" ;")
                        if part and part not in glosses:
                            glosses.append(part[:300])
                if glosses:
                    readings = {hira(reading)} if reading else ({hira(term)} if not KANJI_RE.search(term) else set())
                    yield term, readings, glosses


# ---------------------------------------------------------------- сборка

def build(s, data=DATA, out=None, report=print_report):
    """Собирает словарь по настройкам s в out (по умолчанию data/dict.sqlite)."""
    if not jmdict_file(data, "eng"):
        raise FileNotFoundError("jmdict-eng-*.json не скачан / not downloaded — run download first")
    out = out or os.path.join(data, "dict.sqlite")
    langs = [l for l in s["langs"] if l in LANGS]

    def load_json(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    # --- JMdict: английский — основа, переводы JMdict на другие языки — по id статьи
    report("build", "JMdict (eng)", None)
    eng = load_json(jmdict_file(data, "eng"))
    tags = eng["tags"]
    entries, by_id = [], {}
    for w in eng["words"]:
        senses, pos = [], []
        for sn in w["sense"]:
            pos.extend(p for p in sn["partOfSpeech"] if p not in pos)
            g = "; ".join(x["text"] for x in sn["gloss"])
            misc = ", ".join(tags.get(m, m) for m in sn["misc"])
            senses.append(g + (f" ({misc})" if misc else ""))
        e = {"ext": w["id"], "kanji": [k["text"] for k in w["kanji"]], "kana": [k["text"] for k in w["kana"]],
             "pos": pos, "glosses": {"en": senses}, "src": {},
             "common": int(any(k["common"] for k in w["kanji"]) or any(k["common"] for k in w["kana"]))}
        by_id[w["id"]] = len(entries)
        entries.append(e)
    del eng
    for lang in langs:
        for src in LANGS[lang]["sources"]:
            if not src.startswith("jmdict:") or src == "jmdict:eng" or not jmdict_file(data, src.split(":")[1]):
                continue
            report("build", f"JMdict ({src.split(':')[1]})", None)
            for w in load_json(jmdict_file(data, src.split(":")[1]))["words"]:
                if w["id"] in by_id:
                    e = entries[by_id[w["id"]]]
                    e["glosses"][lang] = ["; ".join(x["text"] for x in sn["gloss"]) for sn in w["sense"]]
                    e["src"][lang] = ["JMdict"]

    # --- указатель для привязки переводов из других словарей к статьям JMdict
    index, kana_of = {}, []
    for i, e in enumerate(entries):
        kana_of.append({hira(k) for k in e["kana"]})
        for t in e["kanji"] + e["kana"]:
            index.setdefault(t, []).append(i)
    extra = {}  # статьи, которых нет в JMdict: (слово, чтения) -> индекс

    def attach(word, readings, glosses, lang, srcname):
        cands = index.get(word, [])
        if readings:
            cands = [i for i in cands if kana_of[i] & readings]
        if cands:
            i = max(cands, key=lambda i: entries[i]["common"])  # при равенстве — первая (порядок JMdict)
        else:
            key = (word, tuple(sorted(readings)))
            if key not in extra:
                kanji = [word] if KANJI_RE.search(word) else []
                extra[key] = len(entries)
                entries.append({"ext": None, "kanji": kanji, "kana": sorted(readings) or ([] if kanji else [word]),
                                "pos": [], "glosses": {}, "src": {}, "common": 0})
                kana_of.append(set(readings))
            i = extra[key]
        e = entries[i]
        have = e["glosses"].setdefault(lang, [])
        have.extend(g for g in glosses if g not in have)
        e["src"].setdefault(lang, [])
        if srcname not in e["src"][lang]:
            e["src"][lang].append(srcname)

    # --- Wiktionary
    sections = {}
    for lang in langs:
        for src in LANGS[lang]["sources"]:
            if src.startswith("wikt:"):
                sections.setdefault(src.split(":")[1], []).append(lang)
    for section, targets in sections.items():
        conv = {}
        if section == "zh":
            import opencc
            conv = {"zh-Hans": opencc.OpenCC("t2s").convert, "zh-Hant": opencc.OpenCC("s2t").convert}
        for path in wikt_files(data, section):
            if not os.path.exists(path):
                continue
            report("build", f"Wiktionary ({section})", None)
            for word, readings, glosses in wikt_records(path):
                for lang in targets:
                    c = conv.get(lang)
                    attach(word, readings, [c(g) for g in glosses] if c else glosses, lang, "Wiktionary")

    # --- свои словари Yomitan
    for y in s.get("yomitan", []):
        if y.get("lang") in LANGS and os.path.exists(y.get("path", "")):
            title = check_yomitan(y["path"]) or "Yomitan"
            report("build", title, None)
            for word, readings, glosses in yomitan_records(y["path"]):
                attach(word, readings, glosses, y["lang"], title)
            if y["lang"] not in langs:
                langs.append(y["lang"])

    # --- запись
    report("write", "dict.sqlite", None)
    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript(
        """
        CREATE TABLE entry(id INTEGER PRIMARY KEY, src TEXT, ext TEXT, kanji TEXT, kana TEXT,
                           pos TEXT, senses TEXT, examples TEXT, ref TEXT, common INTEGER);
        CREATE TABLE term(term TEXT, kind TEXT, entry INTEGER);
        CREATE TABLE kanji(ch TEXT PRIMARY KEY, nick TEXT, info TEXT);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        """
    )
    eid = 0

    def add_terms(eid, kanji, kana):
        db.executemany("INSERT INTO term VALUES(?,?,?)", [(k, "k", eid) for k in kanji] + [(k, "r", eid) for k in kana])

    # WARODAI (японско-русский, по желанию)
    files = glob.glob(os.path.join(data, "warodai", "*", "*", "*", "*.txt")) if "ru" in langs and s.get("warodai") else []
    for n, f in enumerate(files):
        e = parse_warodai(f)
        if not e:
            continue
        eid += 1
        db.execute("INSERT INTO entry VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (eid, "warodai", e["id"], "・".join(e["kanji"]), "・".join(e["kana"]), "",
                    json.dumps(e["senses"], ensure_ascii=False), json.dumps(e["examples"], ensure_ascii=False),
                    e["ref"], 0))
        add_terms(eid, e["kanji"], e["kana"])
        if n % 5000 == 0:
            report("build", "WARODAI", n / len(files))

    covered, covered_common = {}, {}  # сколько статей JMdict (и частотных среди них) получили перевод
    for n, e in enumerate(entries):
        eid += 1
        g = dict(e["glosses"])
        # откуда перевод, если не только из JMdict: «JMdict + Wiktionary», «Wiktionary», название словаря Yomitan
        src = {l: " + ".join(v) for l, v in e["src"].items() if v != ["JMdict"]}
        if src:
            g["_src"] = src
        db.execute("INSERT INTO entry VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (eid, "jmdict" if e["ext"] else "extra", e["ext"], "・".join(e["kanji"]), "・".join(e["kana"]),
                    ",".join(e["pos"]), json.dumps(g, ensure_ascii=False), "[]", None, e["common"]))
        add_terms(eid, e["kanji"], e["kana"])
        if e["ext"]:
            for l in e["glosses"]:
                covered[l] = covered.get(l, 0) + 1
                if e["common"]:
                    covered_common[l] = covered_common.get(l, 0) + 1
        if n % 20000 == 0:
            report("write", "dict.sqlite", n / len(entries))

    # Яркси: «русские прозвища» кандзи из копии пользователя (по желанию)
    ypath = check_yarxi(s.get("yarxi")) if "ru" in langs else None
    if ypath:
        report("build", "Yarxi", None)
        y = sqlite3.connect(f"file:{urllib.parse.quote(ypath)}?mode=ro", uri=True)
        for uc, nick, on, kun in y.execute("SELECT Uncd, RusNick, Onyomi, Kunyomi FROM Kanji"):
            if not uc or not nick:
                continue
            try:
                ch = chr(int(uc))
            except (ValueError, OverflowError):
                continue
            parts = [p.strip("#-^ ") for p in str(nick).split("*") if p.strip("#-^ ")]
            nk = parts[0] if parts else ""
            ons = [p for p in re.split(r"[*;]+", str(on or "")) if re.fullmatch(r"[a-z:]+", p)]
            db.execute("INSERT OR IGNORE INTO kanji VALUES(?,?,?)", (ch, nk, ",".join(ons)))
        y.close()

    jm_total = sum(1 for e in entries if e["ext"])
    jm_common = sum(1 for e in entries if e["ext"] and e["common"])
    installed = [l for l in LANGS if l in covered or (l == "ru" and files)]
    # доля частотных слов (пометка common в JMdict) с переводом — то, что важно в разговоре; all — по всем статьям
    coverage = {l: round(covered_common.get(l, 0) * 100 / jm_common) for l in installed}
    coverage_all = {l: round(covered.get(l, 0) * 100 / jm_total) for l in installed}
    db.execute("INSERT INTO meta VALUES('langs', ?)", (json.dumps(installed),))
    db.execute("INSERT INTO meta VALUES('coverage', ?)", (json.dumps({"common": coverage, "all": coverage_all}),))
    db.execute("CREATE INDEX term_i ON term(term)")
    db.execute("CREATE INDEX entry_ext ON entry(ext)")
    db.commit()
    db.close()
    report("done", ", ".join(f"{l} {coverage[l]}%" for l in installed), 1.0)
    return {"langs": installed, "coverage": coverage, "entries": eid}
