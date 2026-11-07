# Ichigo · 一語一語 — live word-by-word subtitles for Japanese calls

*一語一語 (ichigo ichigo) — "word by word".*

Ichigo helps you during **language exchange calls** with Japanese speakers. It listens to whatever
your PC is playing (Discord, LINE, Zoom, a stream), transcribes the Japanese with Whisper and lays
each phrase out word by word, as an interlinear gloss:

- furigana above the kanji;
- a short dictionary gloss under every word — in English or another language you install;
- grammar notes for particles and endings: past tense, negation, polite form, "want to", and so on;
- a "literally" line in Japanese word order.

Click any word to open the full dictionary entry. You can also paste Japanese text from the chat
to have it broken down the same way. The interface and grammar notes are in **English or Russian**.

## Requirements
- Windows 10/11 (audio is captured via WASAPI loopback; the window uses WebView2);
- Python 3.12 with the `py` launcher;
- an NVIDIA GPU for the `large-v3` model (without one, the `small` model runs on CPU with lower accuracy);
- disk space: ~3 GB for Python packages, ~3 GB for the Whisper model, 0.1–0.5 GB for dictionaries.
  Everything is kept inside the app folder.

## Install
```bat
git clone https://github.com/AvisHolmes/ichigo-subtitles.git
cd ichigo-subtitles
setup.bat
```
`setup.bat` installs the Python packages, puts an **Ichigo** shortcut on the desktop and starts the app.
On first start a setup wizard opens:

1. **Interface language** — English or Русский.
2. **Dictionaries.** English JMdict is always installed: it is the base of the dictionary (headwords,
   parts of speech, the fallback gloss for every word). Pick any extra languages for the glosses.
3. **Install** — the wizard downloads and builds the dictionary (a minute or two, several minutes with
   WARODAI); meanwhile the speech model downloads in the background on the first run (~3 GB).

The dictionaries are not part of this repository (see the licenses below), so this step is required.
To change languages later, press **⚙** in the app.

### Dictionary languages
Dictionaries in other languages are **much less complete than English**. Where a translation is
missing, the English gloss is shown in italics. Share of frequent words (JMdict "common" entries)
that have a translation, November 2026:

| Language | Source | Frequent words | Download |
|---|---|:-:|:-:|
| English | JMdict | 100% | 12 MB |
| Deutsch | JMdict | 96% | 7 MB |
| Русский | JMdict (+ WARODAI, Yarxi) | 82% | 4 MB (+32 MB) |
| Español | JMdict | 70% | 2 MB |
| Français | JMdict + Wiktionary | 62% | 88 MB |
| 中文（简体 / 繁體） | Wiktionary | 40% | 127 MB |
| 한국어 | Wiktionary | 31% | 8 MB |
| More: Nederlands 77%, Magyar 66%, Slovenščina 35%, Svenska 22% | JMdict | | 1–3 MB |

- **Russian** speakers can also install [WARODAI](https://github.com/warodai/warodai-source), a large
  Japanese–Russian dictionary (non-commercial license), and connect **their own copy of
  [Yarxi](https://www.yarxi.ru/)** (`yarxi.db`), a large Japanese–Russian dictionary of words and kanji.
  Yarxi is never downloaded or redistributed: the app reads your file and adds its data only to the
  dictionary on your computer. Surnames and place names from Yarxi are skipped.
- **Your own dictionaries.** There is no open Japanese dictionary yet for Italian, Vietnamese, Arabic,
  Hebrew, Indonesian, Ukrainian and many other languages. If you have a
  [Yomitan](https://github.com/yomidevs/yomitan) dictionary (`.zip`), connect it in the wizard and choose
  its language. It stays on your computer; use only dictionaries you have the right to use.

Without the GUI: `download_data.py --langs ru,de --warodai --yarxi D:\Yarxi\yarxi.db`, then `build_dict.py`.

## Run
Double-click the **Ichigo** shortcut (or `start.bat`). The app opens in its own window. The model takes
about 10 seconds to load; then "large-v3 · GPU" appears in the top-right corner. Closing the window quits
the app. If something goes wrong, see `cache\ichigo.log`.

Environment variables: `ICHIGO_MODEL` (default `large-v3`), `ICHIGO_PORT` (default 8770),
`ICHIGO_DATA` (dictionary folder, default `data`).

## During a call
1. **Source**: `🔊 PC audio: …` is whatever plays in your headphones or speakers.
   The current Windows output is selected by default.
2. **Bluetooth headphones.** If the call uses the headset's microphone, Windows switches it to
   "Hands-Free" mode and the audio goes through a different device. Press **🔄** after the call
   starts to pick up the current output. Better still, choose a separate microphone in the call app,
   so the headphones stay in high-quality mode and recognition is more accurate.
3. **Sensitivity**: the orange mark on the meter is the speech threshold. Move it left
   if phrases are missed, right if noise gets picked up.
4. **Phrase pause**: how much silence ends a phrase.
5. **Dictionary** (key `L` cycles): language of the glosses under the words. Italic glosses are
   English fallbacks for words without a translation.
6. **Glosses** (key `T`): hide all glosses and keep only the Japanese, for when you want to test yourself.
7. **🌐 EN / RU**: interface and grammar-note language. **⚙**: dictionaries and languages.
8. Click a word for its dictionary entry; `Esc` closes it.

## Files
- `app/gui.py`: the app window (pywebview), starts the server;
- `app/server.py`: audio capture, Whisper, web server, setup API;
- `app/analyzer.py`: morphological analysis (UniDic), furigana, dictionary lookup, grammar notes;
- `app/dictionaries.py`: dictionary languages and sources, download and build of `data/dict.sqlite`;
- `app/static/index.html`, `app/static/setup.html`: the interface and the setup wizard;
- `app/shortcut.py`: creates the desktop shortcut;
- `download_data.py`, `build_dict.py`: the same dictionary setup from the command line;
- settings are kept in `data/settings.json`; the Whisper model, logs and window data in `cache/`.

## Dictionaries and data licenses
The dictionaries are not part of this repository; each user downloads them from the original sources.
- [JMdict](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project) © EDRDG,
  CC BY-SA 4.0, via [jmdict-simplified](https://github.com/scriptin/jmdict-simplified);
- [Wiktionary](https://www.wiktionary.org/) (French, Chinese and Korean editions), CC BY-SA 4.0 / GFDL,
  extracted by [Wiktextract](https://github.com/tatuylonen/wiktextract) and published at
  [kaikki.org](https://kaikki.org/);
- [WARODAI](https://github.com/warodai/warodai-source), Japanese–Russian dictionary,
  CC BY-NC-ND 3.0 (non-commercial use only);
- [Yarxi](https://www.yarxi.ru/) and Yomitan dictionaries: optional, read from the user's own copy,
  never downloaded or redistributed;
- speech recognition: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (Whisper models © OpenAI, MIT);
  morphology: [fugashi](https://github.com/polm/fugashi) + UniDic-lite;
  simplified/traditional Chinese: [OpenCC](https://github.com/BYVoid/OpenCC) (Apache 2.0).

---

## По-русски

**Итиго (一語一語, «слово за словом»)** — живой подстрочник японской речи для языкового обмена
по звонкам. Программа слушает звук ПК, распознаёт японскую речь через Whisper и показывает каждую
фразу по словам: фуригана над кандзи, перевод под словом, грамматические пометки и строка
«буквально» в порядке японских слов. Клик по слову открывает словарную статью.

**Установка:** `setup.bat` ставит зависимости, кладёт ярлык «Ichigo» на рабочий стол и запускает
программу. При первом запуске открывается мастер настройки: язык интерфейса (English / Русский),
потом словари. Английский JMdict ставится всегда, это основа словаря. Словари на других языках
намного менее полные (см. таблицу выше); где перевода нет, показывается английский курсивом.
Для русского можно дополнительно скачать WARODAI (большой японско-русский словарь, только
некоммерческое использование) и подключить свою копию Яркси (`yarxi.db`) — большого словаря слов
и кандзи. Яркси не скачивается и не распространяется: программа читает ваш файл и добавляет его
данные только в словарь на вашем компьютере. Для языков без открытого словаря можно подключить свой словарь Yomitan (`.zip`).
Поменять языки потом — кнопка **⚙** в программе.

Запуск — ярлык «Ichigo» или `start.bat`, лог — `cache\ichigo.log`. Подробности — в разделах выше.
