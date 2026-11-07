"""Разбор японской фразы: слова, фуригана, словарные значения, грамматические пометки."""
import json
import os
import re
import sqlite3
import threading

import fugashi
import jaconv

DATA = os.environ.get("ICHIGO_DATA") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
KANJI_RE = re.compile(r"[㐀-鿿豈-﫿々〆ヶ]")
HIRA_RE = re.compile(r"[぀-ゟ]")

# Служебные слова: (лемма, часть речи UniDic pos1/pos2 префикс) -> пояснение.
PARTICLES = {
    "は": "[тема]",
    "が": "[подлеж.]",
    "を": "[кого/что]",
    "に": "[куда / кому / когда]",
    "へ": "[в сторону]",
    "で": "[где / чем]",
    "と": "[с / и / «цит.»]",
    "から": "[от, из / потому что]",
    "まで": "[до]",
    "より": "[чем / от]",
    "の": "[чей / X-овый]",
    "も": "[тоже / даже]",
    "や": "и (неполный перечень)",
    "か": "[?] / или",
    "ね": "[да? ведь]",
    "よ": "[!, говорю тебе]",
    "な": "[восклиц. / не делай]",
    "わ": "эмоция (женская речь)",
    "さ": "разг. акцент «ну»",
    "ぞ": "муж. акцент «!»",
    "ぜ": "муж. акцент «!»",
    "けれど": "но, хотя",
    "けれども": "но, хотя",
    "が/接続": "но",
    "し": "и ещё (перечень причин)",
    "て": "-и потом / -я (соединительная форма)",
    "ば": "если (условие)",
    "ながら": "одновременно с / хотя",
    "のに": "хотя / а ведь",
    "ので": "так как",
    "って": "«цитата» / мол / что касается (разг.)",
    "たって": "даже если",
    "だけ": "только",
    "しか": "только (с отрицанием)",
    "ばかり": "только, сплошь / только что",
    "など": "и т. п.",
    "なんか": "что-то вроде / и т. п. (разг.)",
    "くらい": "примерно / настолько",
    "ぐらい": "примерно / настолько",
    "ほど": "примерно / настолько, что",
    "でも": "даже / хоть / но",
    "こそ": "именно",
    "さえ": "даже",
    "かな": "«интересно…?» (размышление)",
    "かしら": "«интересно…?» (жен.)",
    "もん": "ведь (оправдание, разг.)",
    "もの": "ведь (оправдание)",
    "とか": "или там / например",
    "ってば": "«ну же!»",
    "っけ": "«как там было?»",
    "じゃん": "«ведь же!» (разг.)",
    "の/準体": "[дело в том, что / то, что]",
    "の/終助": "[?/объясн., разг.]",
    "たり": "-то… -то (перечень действий)",
    "つつ": "одновременно",
    "ずつ": "по (сколько-то каждому)",
    "なり": "как только / или",
}

AUX = {
    "です": "есть (связка, вежл.)",
    "だ": "есть (связка)",
    "ます": "[вежл.]",
    "た": "[прош.]",
    "ない": "[не]",
    "ぬ": "[не]",
    "ん": "[не]",
    "ず": "[не] (письм.)",
    "たい": "[хочу]",
    "れる": "[пассив / могу / уважит.]",
    "られる": "[пассив / могу / уважит.]",
    "せる": "[заставить / позволить]",
    "させる": "[заставить / позволить]",
    "う": "[давай / наверное]",
    "よう": "[давай / наверное]",
    "まい": "[не буду / вряд ли]",
    "らしい": "[похоже / говорят]",
    "そう": "[похоже / говорят]",
    "みたい": "[как будто]",
    "ようだ": "[похоже]",
    "ちゃう": "[совсем / досадно] (= てしまう)",
    "じゃう": "[совсем / досадно] (= でしまう)",
    "べし": "[следует]",
    "なさる": "[уважит.]",
    "や": "есть (связка, кансай)",
    "じゃ": "есть (связка) / ну",
    "だろう": "[наверное]",
    "でしょう": "[наверное] (вежл.)",
    "ごとし": "[подобно]",
    "ちまう": "[совсем / досадно]",
    "てる": "[делает сейчас / состояние] (= ている)",
    "でる": "[делает сейчас / состояние] (= でいる)",
    "とく": "[заранее] (= ておく)",
    "どく": "[заранее] (= でおく)",
    "そう-様態": "[выглядит, похоже]",
    "そう-伝聞": "[говорят, что]",
    "よう": "[похоже / как]",
    "みたい": "[как будто]",
}

SUFFIX = {
    "さん": "(г-н / г-жа, вежл.)",
    "ちゃん": "(ласкат.)",
    "君": "(к парню / младшему)",
    "くん": "(к парню / младшему)",
    "様": "(почтит.)",
    "さま": "(почтит.)",
    "達": "[мн. ч.]",
    "たち": "[мн. ч.]",
    "等": "[и др.]",
    "ら": "[мн. ч.]",
    "的": "-ический / -ый",
    "目": "-й (порядковый)",
    "頃": "около (времени)",
    "ごろ": "около (времени)",
    "ぐらい": "примерно",
    "中": "в течение / в процессе",
    "方": "способ / сторона",
    "っぽい": "[похожий на]",
    "がる": "[проявлять / показывать]",
    "過ぎる": "[слишком]",
    "すぎる": "[слишком]",
    "易い": "[легко -]",
    "やすい": "[легко -]",
    "難い": "[трудно -]",
    "にくい": "[трудно -]",
}

# Базовые значения самых частых разговорных слов (первое значение в словаре часто книжное).
CORE = {
    "為る": "делать", "する": "делать", "居る": "быть, находиться (о живых)", "いる": "быть, находиться (о живых)",
    "有る": "быть, иметься", "在る": "быть, находиться", "ある": "быть, иметься", "成る": "становиться",
    "言う": "говорить, сказать", "思う": "думать", "来る": "приходить", "行く": "идти, ехать",
    "見る": "смотреть, видеть", "分かる": "понимать", "出来る": "мочь, уметь; получаться",
    "遣る": "делать (разг.) / давать", "良い": "хороший", "いい": "хороший", "無い": "нет, не иметься",
    "然う": "так", "そう": "так", "斯う": "вот так", "こう": "вот так", "如何": "как", "どう": "как",
    "此れ": "это", "其れ": "это / то", "彼れ": "вон то", "此の": "этот", "其の": "этот / тот", "彼の": "вон тот",
    "何": "что", "誰": "кто", "何処": "где", "何時": "когда", "何故": "почему", "如何して": "почему / как",
    "本当": "правда", "凄い": "потрясающий; очень", "可愛い": "милый", "一寸": "немного; минутку",
    "矢張り": "всё-таки, как и думал", "皆": "все", "色々": "разный", "大丈夫": "в порядке, нормально",
    "好き": "нравится, любимый", "嫌い": "не нравится", "未だ": "ещё (не)", "もう": "уже / ещё",
    "多分": "наверное", "全然": "совсем (не)", "余り": "не очень (с отриц.)", "頑張る": "стараться",
    "有り難う": "спасибо", "御免": "извини", "済む": "заканчиваться (すみません — извините)",
    "宜しい": "хороший (よろしく — прошу, будь добр)", "御座る": "есть (очень вежл.)",
    "貴方": "ты, вы", "僕": "я (муж.)", "俺": "я (муж., грубовато)", "私": "я", "君": "ты",
    "彼": "он", "彼女": "она / девушка", "友達": "друг, подруга", "今日": "сегодня", "明日": "завтра",
    "昨日": "вчера", "今": "сейчас", "貰う": "получать", "呉れる": "давать (мне)", "上げる": "давать (кому-то); поднимать",
    "欲しい": "хотеть (что-то)", "楽しい": "весёлый, приятный", "面白い": "интересный, смешной",
    "美味しい": "вкусный", "一緒": "вместе", "確か": "точно; кажется", "違う": "отличаться; «не так»",
    "知る": "знать", "待つ": "ждать", "聞く": "слушать; спрашивать", "話す": "разговаривать",
    "食べる": "есть", "飲む": "пить", "寝る": "спать", "起きる": "вставать, просыпаться",
    "例えば": "например", "実は": "на самом деле", "因みに": "кстати", "じゃあ": "ну тогда", "じゃ": "ну тогда",
    "うん": "да, угу", "ええ": "да / э-э", "はい": "да", "いいえ": "нет", "ううん": "не-а", "へえ": "ого, надо же",
    "成る程": "понятно, вот как", "なるほど": "понятно, вот как", "あの": "э-э… (заминка) / тот",
    "えっと": "э-э… (думаю)", "まあ": "ну…", "ね": "слушай / да?", "本当に": "правда, действительно",
    "とても": "очень", "めっちゃ": "очень (разг.)", "結構": "довольно; хватит, нормально",
    "大好き": "очень нравится, обожаю", "会う": "встречаться", "住む": "жить (где-то)",
    "時間": "время", "ゲーム": "игра (видео-)", "ご飯": "еда; варёный рис", "眠い": "сонный, хочется спать",
    "遅い": "поздний; медленный", "早い": "ранний; быстрый", "さっき": "только что, недавно", "仕事": "работа", "勉強": "учёба", "日本": "Япония", "ロシア": "Россия",
}

# Вспомогательные глаголы после -て
AFTER_TE = {
    "いる": "[делает сейчас / состояние]",
    "居る": "[делает сейчас / состояние]",
    "ある": "[сделано и так лежит]",
    "有る": "[сделано и так лежит]",
    "しまう": "[совсем / досадно]",
    "仕舞う": "[совсем / досадно]",
    "おく": "[заранее]",
    "置く": "[заранее]",
    "くる": "[начинает / приходит сделав]",
    "来る": "[начинает / приходит сделав]",
    "いく": "[продолжает / уходит сделав]",
    "行く": "[продолжает / уходит сделав]",
    "みる": "[попробовать]",
    "見る": "[попробовать]",
    "あげる": "[для кого-то]",
    "上げる": "[для кого-то]",
    "くれる": "[для меня]",
    "呉れる": "[для меня]",
    "もらう": "[мне сделали (получаю услугу)]",
    "貰う": "[мне сделали (получаю услугу)]",
    "くださる": "[пожалуйста / для меня (вежл.)]",
    "下さる": "[пожалуйста / для меня (вежл.)]",
    "いただく": "[мне сделали (скромн.)]",
    "頂く": "[мне сделали (скромн.)]",
    "ほしい": "[хочу, чтобы сделали]",
    "欲しい": "[хочу, чтобы сделали]",
    "ござる": "[вежл. есть]",
    "御座る": "[вежл. есть]",
}

CFORM = {
    "仮定形": "[если]",
    "命令形": "[приказ]",
    "意志推量形": "[давай / наверное]",
}

CONTENT_POS = {"名詞", "動詞", "形容詞", "形状詞", "副詞", "連体詞", "接続詞", "感動詞", "代名詞", "接頭辞"}
JOIN_TO_PREV = {"助動詞"}

# Служебные сочетания из нескольких морфем: склеиваем в одно «слово» с пометкой.
FUNC_PHRASES = {
    ("か", "も", "しれ", "ない"): "[может быть]",
    ("か", "も", "しれ", "ませ", "ん"): "[может быть] (вежл.)",
    ("か", "も"): "[может быть]",
    ("な", "けれ", "ば", "なら", "ない"): "[должен, надо]",
    ("な", "けれ", "ば", "いけ", "ない"): "[должен, надо]",
    ("な", "きゃ"): "[надо]",
    ("な", "くちゃ"): "[надо]",
    ("ちゃ", "だめ"): "[нельзя]",
    ("て", "も", "いい"): "[можно]",
    ("で", "も", "いい"): "[можно]",
    ("て", "も"): "[даже если]",
    ("こと", "が", "できる"): "[можно, могу]",
    ("こと", "が", "でき"): "[можно, могу]",
    ("こと", "が", "ある"): "[бывает / доводилось]",
    ("ほう", "が", "いい"): "[лучше]",
    ("方", "が", "いい"): "[лучше]",
    ("と", "思う"): "[думаю, что]",
    ("と", "思い", "ます"): "[думаю, что] (вежл.)",
    ("ん", "です"): "[дело в том, что] (вежл.)",
    ("ん", "だ"): "[дело в том, что]",
    ("の", "です"): "[дело в том, что] (вежл.)",
    ("でしょ", "う"): "[наверное] (вежл.)",
    ("だろ", "う"): "[наверное]",
    ("じゃ", "ない"): "[не (связка)] / [ведь…, да?]",
    ("じゃ", "ん"): "[ведь же!] (разг.)",
    ("よ", "ね"): "[ведь так, да?]",
}
# Английские версии грамматических пометок (ключ — русская пометка из таблиц выше и из _grammar).
GRAM_EN = {
    "[тема]": "[topic]",
    "[подлеж.]": "[subject]",
    "[кого/что]": "[object]",
    "[куда / кому / когда]": "[to / at / for]",
    "[в сторону]": "[towards]",
    "[где / чем]": "[at / by means of]",
    "[с / и / «цит.»]": "[with / and / «quote»]",
    "[от, из / потому что]": "[from / because]",
    "[до]": "[until / up to]",
    "[чем / от]": "[than / from]",
    "[чей / X-овый]": "['s / of]",
    "[тоже / даже]": "[also / even]",
    "и (неполный перечень)": "and (among others)",
    "[?] / или": "[?] / or",
    "[да? ведь]": "[right? isn't it]",
    "[!, говорю тебе]": "[!, I'm telling you]",
    "[восклиц. / не делай]": "[exclam. / don't]",
    "эмоция (женская речь)": "emphasis (feminine speech)",
    "разг. акцент «ну»": "casual emphasis «well»",
    "муж. акцент «!»": "masculine emphasis «!»",
    "но, хотя": "but, although",
    "но": "but",
    "и ещё (перечень причин)": "and also (listing reasons)",
    "-и потом / -я (соединительная форма)": "and then / -ing (te-form)",
    "если (условие)": "if (condition)",
    "одновременно с / хотя": "while / although",
    "хотя / а ведь": "even though / despite",
    "так как": "since, because",
    "«цитата» / мол / что касается (разг.)": "«quote» / they say / as for (casual)",
    "даже если": "even if",
    "только": "only",
    "только (с отрицанием)": "only (with negative)",
    "только, сплошь / только что": "only, nothing but / just now",
    "и т. п.": "etc.",
    "что-то вроде / и т. п. (разг.)": "something like / etc. (casual)",
    "примерно / настолько": "about / to the extent",
    "примерно / настолько, что": "about / so much that",
    "даже / хоть / но": "even / at least / but",
    "именно": "precisely",
    "даже": "even",
    "«интересно…?» (размышление)": "«I wonder…?»",
    "«интересно…?» (жен.)": "«I wonder…?» (feminine)",
    "ведь (оправдание, разг.)": "because (excuse, casual)",
    "ведь (оправдание)": "because (excuse)",
    "или там / например": "or something / for example",
    "«ну же!»": "«come on!»",
    "«как там было?»": "«what was it again?»",
    "«ведь же!» (разг.)": "«right?!» (casual)",
    "[дело в том, что / то, что]": "[the thing is / the fact that]",
    "[?/объясн., разг.]": "[?/explanatory, casual]",
    "-то… -то (перечень действий)": "doing things like… (listing actions)",
    "одновременно": "while",
    "по (сколько-то каждому)": "each (so many apiece)",
    "как только / или": "as soon as / or",
    "есть (связка, вежл.)": "is (copula, polite)",
    "есть (связка)": "is (copula)",
    "[вежл.]": "[polite]",
    "[прош.]": "[past]",
    "[не]": "[not]",
    "[не] (письм.)": "[not] (written)",
    "[хочу]": "[want to]",
    "[пассив / могу / уважит.]": "[passive / can / honorific]",
    "[заставить / позволить]": "[make / let]",
    "[давай / наверное]": "[let's / probably]",
    "[похоже / как]": "[seems / like]",
    "[не буду / вряд ли]": "[won't / unlikely]",
    "[похоже / говорят]": "[seems / they say]",
    "[как будто]": "[as if]",
    "[похоже]": "[seems]",
    "[совсем / досадно] (= てしまう)": "[completely / regrettably] (= てしまう)",
    "[совсем / досадно] (= でしまう)": "[completely / regrettably] (= でしまう)",
    "[следует]": "[should]",
    "[уважит.]": "[honorific]",
    "есть (связка, кансай)": "is (copula, Kansai)",
    "есть (связка) / ну": "is (copula) / well",
    "[наверное]": "[probably]",
    "[наверное] (вежл.)": "[probably] (polite)",
    "[подобно]": "[like, similar to]",
    "[совсем / досадно]": "[completely / regrettably]",
    "[делает сейчас / состояние] (= ている)": "[-ing now / state] (= ている)",
    "[делает сейчас / состояние] (= でいる)": "[-ing now / state] (= でいる)",
    "[заранее] (= ておく)": "[in advance] (= ておく)",
    "[заранее] (= でおく)": "[in advance] (= でおく)",
    "[выглядит, похоже]": "[looks like]",
    "[говорят, что]": "[I hear that]",
    "(г-н / г-жа, вежл.)": "(Mr. / Ms., polite)",
    "(ласкат.)": "(affectionate)",
    "(к парню / младшему)": "(to a boy / junior)",
    "(почтит.)": "(respectful)",
    "[мн. ч.]": "[plural]",
    "[и др.]": "[and others]",
    "-ический / -ый": "-ic / -al",
    "-й (порядковый)": "-th (ordinal)",
    "около (времени)": "around (time)",
    "примерно": "about",
    "в течение / в процессе": "during / in the middle of",
    "способ / сторона": "way of / side",
    "[похожий на]": "[-ish, like]",
    "[проявлять / показывать]": "[shows signs of]",
    "[слишком]": "[too much]",
    "[легко -]": "[easy to -]",
    "[трудно -]": "[hard to -]",
    "[делает сейчас / состояние]": "[-ing now / state]",
    "[сделано и так лежит]": "[has been done (and stays so)]",
    "[заранее]": "[in advance]",
    "[начинает / приходит сделав]": "[starts to / comes after doing]",
    "[продолжает / уходит сделав]": "[keeps on / goes after doing]",
    "[попробовать]": "[try doing]",
    "[для кого-то]": "[for someone]",
    "[для меня]": "[for me]",
    "[мне сделали (получаю услугу)]": "[have it done for me]",
    "[пожалуйста / для меня (вежл.)]": "[please / for me (polite)]",
    "[мне сделали (скромн.)]": "[have it done for me (humble)]",
    "[хочу, чтобы сделали]": "[want someone to do]",
    "[вежл. есть]": "[polite «is»]",
    "[если]": "[if]",
    "[приказ]": "[command]",
    "[может быть]": "[maybe]",
    "[может быть] (вежл.)": "[maybe] (polite)",
    "[должен, надо]": "[must, have to]",
    "[надо]": "[have to]",
    "[нельзя]": "[must not]",
    "[можно]": "[may, it's ok to]",
    "[даже если]": "[even if]",
    "[можно, могу]": "[can, be able to]",
    "[бывает / доводилось]": "[sometimes happens / have done before]",
    "[лучше]": "[had better]",
    "[думаю, что]": "[I think that]",
    "[думаю, что] (вежл.)": "[I think that] (polite)",
    "[дело в том, что] (вежл.)": "[the thing is] (polite)",
    "[дело в том, что]": "[the thing is]",
    "[не (связка)] / [ведь…, да?]": "[is not] / […, right?]",
    "[ведь же!] (разг.)": "[right?!] (casual)",
    "[ведь так, да?]": "[right? isn't it]",
    "если / когда / как только": "if / when / as soon as",
    "[-и / -я]": "[and / -ing]",
    "[если / когда] (-тара)": "[if / when] (-tara)",
    "[если не… → надо] (なきゃ/なければ)": "[if not… → must] (なきゃ/なければ)",
    "[если] (なら)": "[if] (なら)",
    "(имя / название)": "(name)",
}
JP_TEXT_RE = re.compile(r"[぀-ヿ㐀-鿿]")

HALLUCINATIONS = ("ご視聴ありがとうございました", "チャンネル登録", "最後までご視聴", "字幕")


def kata2hira(s):
    return jaconv.kata2hira(s or "")


def furigana(surface, reading):
    """[(text, ruby|None)] — фуригана только над кандзи, окончания-кана без неё."""
    reading = kata2hira(reading)
    if "日本" in surface:  # UniDic читает «にっぽん», в разговоре почти всегда «にほん»
        reading = reading.replace("にっぽん", "にほん")
    if surface == "私" and reading == "わたくし":
        reading = "わたし"
    if surface == "明日" and reading == "あす":
        reading = "あした"
    if not KANJI_RE.search(surface) or not reading:
        return [[surface, None]]
    # Разбиваем на куски кандзи/не-кандзи и строим regex
    parts = re.findall(r"[㐀-鿿豈-﫿々〆ヶ]+|[^㐀-鿿豈-﫿々〆ヶ]+", surface)
    pattern = ""
    for p in parts:
        if KANJI_RE.match(p):
            pattern += "(.+?)"
        else:
            pattern += "(" + re.escape(kata2hira(p)) + ")"
    m = re.fullmatch(pattern, reading)
    if not m:
        return [[surface, reading]]
    out = []
    for p, g in zip(parts, m.groups()):
        out.append([p, g if KANJI_RE.match(p) else None])
    return out


class Dictionary:
    def __init__(self, path=None):
        path = path or os.path.join(DATA, "dict.sqlite")
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path}: словарь не собран, запусти setup.bat / dictionary not built, run setup.bat")
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.cache = {}
        self.kanji = {ch: (nick, on) for ch, nick, on in self.db.execute("SELECT ch,nick,info FROM kanji")}
        # языки переводов в этой сборке; в старых базах (до таблицы meta) были только ru и en
        try:
            self.langs = json.loads(self.db.execute("SELECT value FROM meta WHERE key='langs'").fetchone()[0])
        except (sqlite3.OperationalError, TypeError):
            self.langs = ["en", "ru"]

    def close(self):
        with self.lock:
            self.db.close()

    def has(self, term):
        with self.lock:
            return self.db.execute("SELECT 1 FROM term WHERE term=? LIMIT 1", (term,)).fetchone() is not None

    def _entries(self, term):
        with self.lock:
            return self.db.execute(
                "SELECT e.id,e.src,e.ext,e.kanji,e.kana,e.pos,e.senses,e.examples,e.ref,e.common,t.kind "
                "FROM term t JOIN entry e ON e.id=t.entry WHERE t.term=?",
                (term,),
            ).fetchall()

    def _by_ext(self, ext):
        with self.lock:
            return self.db.execute(
                "SELECT id,src,ext,kanji,kana,pos,senses,examples,ref,common,'k' FROM entry WHERE ext=? AND src='warodai'",
                (ext,),
            ).fetchone()

    def lookup(self, terms, reading=None, kana_only=False):
        """terms — варианты написания (лемма, форма в тексте). Возвращает лучшие статьи."""
        key = (tuple(terms), reading, kana_only)
        if key in self.cache:
            return self.cache[key]
        reading = kata2hira(reading) if reading else None
        seen, scored = set(), []
        for rank, term in enumerate(terms):
            if not term:
                continue
            for row in self._entries(term):
                if row[0] in seen:
                    continue
                seen.add(row[0])
                eid, src, ext, kanji, kana, pos, senses, examples, ref, common, kind = row
                kanas = [kata2hira(k) for k in kana.split("・")]
                score = -rank * 3
                if reading and reading in kanas:
                    score += 6
                elif reading and kind == "k":
                    score -= 4
                if kind == "k" and KANJI_RE.search(term):
                    score += 2
                if kana_only and kind == "r" and kanji:
                    # слово написано каной: скорее это «обычно каной» слово, а не омоним с кандзи
                    score += 3 if "kana alone" in senses else -5
                if src in ("warodai", "yarxi"):
                    score += 7
                elif any(v for k, v in json.loads(senses).items() if k not in ("en", "_src")):
                    score += 4  # есть перевод не только на английский — обычно это употребительное слово
                if common:
                    score += 3
                scored.append((score, row))
        scored.sort(key=lambda x: -x[0])
        result = []
        rows = [row for _, row in scored[:4]]
        # лучшая статья JMdict нужна всегда: в ней переводы на все языки, включая английский
        best_jm = next((row for _, row in scored if row[1] == "jmdict"), None)
        if best_jm and best_jm not in rows:
            rows.append(best_jm)
        for row in rows:
            e = self._format(row)
            if e:
                result.append(e)
        self.cache[key] = result
        return result

    def _format(self, row, depth=0):
        eid, src, ext, kanji, kana, pos, senses, examples, ref, common, _ = row
        if src == "yarxi":
            return {"src": "Yarxi", "kanji": kanji, "kana": kana, "glosses": {"ru": json.loads(senses)}}
        if src == "warodai":
            ss = json.loads(senses)
            if ref and depth < 2:
                tgt = self._by_ext(ref)
                if tgt:
                    e = self._format(tgt, depth + 1)
                    if e:
                        return e
            return {"src": "WARODAI", "kanji": kanji, "kana": kana, "glosses": {"ru": ss},
                    "examples": json.loads(examples)}
        d = json.loads(senses)
        srcs = d.pop("_src", {})  # откуда переводы, если не из JMdict: Wiktionary, свой словарь Yomitan
        glosses = {lang: ss for lang, ss in d.items() if ss}
        label = "JMdict" if src == "jmdict" else next(iter(srcs.values()), "Wiktionary")
        return {"src": label, "kanji": kanji, "kana": kana, "glosses": glosses, "srcs": srcs, "pos": pos}

    def kanji_info(self, text):
        out = []
        for ch in text:
            if ch in self.kanji:
                nick, on = self.kanji[ch]
                out.append({"ch": ch, "nick": nick, "on": on})
        return out


def clean_lemma(lemma):
    # UniDic: «ラーメン-Rahmen», «ちょっと-一寸»
    return (lemma or "").split("-")[0]


class Analyzer:
    def __init__(self):
        self.tagger = fugashi.Tagger()
        self.dict = Dictionary()

    def _tok(self, w):
        f = w.feature
        return {
            "surface": w.surface,
            "pos1": f.pos1 or "",
            "pos2": f.pos2 or "",
            "lemma": clean_lemma(f.lemma) or w.surface,
            "rawlemma": f.lemma or "",
            "lform": f.lForm or "",
            "base": f.orthBase or w.surface,
            "kana": f.kana or "",
            "cform": f.cForm or "",
        }

    @staticmethod
    def is_hallucination(text):
        return any(h in text for h in HALLUCINATIONS) or not JP_TEXT_RE.search(text)

    def analyze(self, text):
        toks = [self._tok(w) for w in self.tagger(text)]
        toks = self._merge_compounds(toks)
        chunks = []
        prev_te = False
        for t in toks:
            p1, lemma = t["pos1"], t["lemma"]
            gram = self._grammar(t, prev_te)
            attach = chunks and chunks[-1]["head"] and (
                p1 in JOIN_TO_PREV
                or t["pos2"] == "助動詞語幹"
                or (p1 == "接尾辞" and (lemma in SUFFIX or t["surface"] in SUFFIX))
                or (p1 == "助詞" and t["pos2"] == "接続助詞" and lemma in ("て", "で", "ば") )
                or (prev_te and p1 == "動詞" and t["base"] in AFTER_TE or prev_te and lemma in AFTER_TE)
            )
            if attach:
                c = chunks[-1]
                c["parts"].append(self._part(t, gram, lookup=False))
                c["surface"] += t["surface"]
            else:
                is_head = p1 in CONTENT_POS or t.get("compound")
                chunks.append({
                    "surface": t["surface"],
                    "head": bool(is_head),
                    "kind": "content" if is_head else ("punct" if p1 in ("補助記号", "空白") else "func"),
                    "parts": [self._part(t, gram, lookup=is_head)],
                })
            prev_te = p1 == "助詞" and lemma in ("て", "で") and t["pos2"] == "接続助詞"
        return {"text": text, "chunks": chunks}

    def _merge_compounds(self, toks):
        """Склеиваем соседние морфемы, если такое слово есть в словаре (日本+語 → 日本語)."""
        out, i = [], 0
        keys = sorted(FUNC_PHRASES, key=len, reverse=True)
        nounish = {"名詞", "接頭辞", "接尾辞", "形状詞"}
        while i < len(toks):
            merged = False
            for key in keys:
                seg = toks[i:i + len(key)]
                if tuple(t["surface"] for t in seg) == key and i > 0:
                    t = dict(seg[0])
                    t.update(surface="".join(key), lemma="".join(key), base="".join(key), rawlemma="",
                             kana="".join(x["kana"] for x in seg), lform="", pos1="助詞", pos2="連語",
                             cform="", phrase=FUNC_PHRASES[key])
                    out.append(t)
                    i += len(key)
                    merged = True
                    break
            if merged:
                continue
            for n in (4, 3, 2):
                seg = toks[i:i + n]
                if len(seg) < n:
                    continue
                surf = "".join(t["surface"] for t in seg)
                all_noun = all(t["pos1"] in nounish for t in seg) and seg[0]["pos1"] != "接尾辞"
                if (all_noun or (len(surf) >= 5 and seg[0]["pos1"] in ("感動詞", "名詞", "副詞"))) and self.dict.has(surf):
                    t = dict(seg[0])
                    t.update(surface=surf, lemma=surf, base=surf, lform="".join(x["kana"] for x in seg),
                             kana="".join(x["kana"] for x in seg), pos1=seg[0]["pos1"] if all_noun else "名詞",
                             cform="", compound=True)
                    out.append(t)
                    i += n
                    merged = True
                    break
            if not merged:
                out.append(toks[i])
                i += 1
        return out

    def _grammar(self, t, prev_te):
        p1, p2, lemma = t["pos1"], t["pos2"], t["lemma"]
        notes = []
        if t.get("phrase"):
            return [t["phrase"]]
        if p1 == "助詞":
            if p2 == "準体助詞":
                notes.append(PARTICLES["の/準体"])
            elif lemma == "が" and p2 == "接続助詞":
                notes.append(PARTICLES["が/接続"])
            elif lemma == "の" and p2 == "終助詞":
                notes.append(PARTICLES["の/終助"])
            elif lemma == "と" and p2 == "接続助詞":
                notes.append("если / когда / как только")
            elif lemma in ("て", "で") and p2 == "接続助詞":
                notes.append("[-и / -я]")
            elif lemma in PARTICLES:
                notes.append(PARTICLES[lemma])
            elif t["surface"] in PARTICLES:
                notes.append(PARTICLES[t["surface"]])
        elif p1 == "接尾辞":
            notes.append(SUFFIX.get(lemma) or SUFFIX.get(t["surface"]))
        elif p2 == "助動詞語幹":
            notes.append(AUX.get(t["rawlemma"]) or AUX.get(lemma))
        elif p1 == "助動詞":
            if t["surface"] == "ん" and lemma in ("ず", "ぬ"):
                notes.append("[не]")
            elif lemma == "た" and t["cform"].startswith("仮定形"):
                notes.append("[если / когда] (-тара)")
            elif lemma == "ない" and t["cform"].startswith("仮定形"):
                notes.append("[если не… → надо] (なきゃ/なければ)")
            elif lemma == "だ" and t["cform"].startswith("仮定形"):
                notes.append("[если] (なら)")
            elif t["rawlemma"] in AUX:
                notes.append(AUX[t["rawlemma"]])
            elif lemma in AUX:
                notes.append(AUX[lemma])
            elif t["surface"] in AUX:
                notes.append(AUX[t["surface"]])
        elif prev_te and (lemma in AFTER_TE or t["base"] in AFTER_TE):
            notes.append(AFTER_TE.get(lemma) or AFTER_TE.get(t["base"]))
        if p2 == "固有名詞":
            notes.append("(имя / название)")
        if p1 not in ("助動詞",):
            for k, v in CFORM.items():
                if t["cform"].startswith(k) and p1 in ("動詞", "形容詞"):
                    notes.append(v)
        return notes

    def _part(self, t, gram, lookup):
        gram = [g for g in gram if g]
        part = {
            "surface": t["surface"],
            "ruby": furigana(t["surface"], t["kana"]),
            "lemma": t["base"] if t["base"] != t["surface"] else (t["lemma"] if t["lemma"] != t["surface"] else ""),
            "lemma_reading": kata2hira(t["lform"]) if t["lform"] and KANJI_RE.search(t["lemma"]) else "",
            "pos": t["pos1"],
            "gram": gram,
            "gram_en": [GRAM_EN.get(g, g) for g in gram],
        }
        if lookup and t["pos1"] not in ("補助記号", "空白"):
            terms = [t["lemma"], t["base"], t["surface"]]
            # леммы UniDic иногда в кандзи, которых нет в словаре — добавим кану
            terms.append(kata2hira(t["lform"]))
            entries = self.dict.lookup(list(dict.fromkeys(terms)), t["lform"], kana_only=not KANJI_RE.search(t["surface"]))
            core = CORE.get(t["lemma"]) or CORE.get(t["surface"]) if not t.get("compound") else CORE.get(t["surface"])
            if core and "ru" in self.dict.langs:  # базовые значения написаны только по-русски
                entries = [{"src": "core", "kanji": t["lemma"] if KANJI_RE.search(t["lemma"]) else "",
                            "kana": kata2hira(t["lform"]), "glosses": {"ru": [core]}}] + entries
            part["entries"] = entries
            part["kanji"] = self.dict.kanji_info(t["surface"] + t["lemma"])
        return part


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    a = Analyzer()
    s = sys.argv[1] if len(sys.argv) > 1 else "昨日は友達とラーメンを食べに行っちゃったんですけど、すごく美味しかったよね。"
    r = a.analyze(s)
    for c in r["chunks"]:
        p = c["parts"][0]
        gl = ""
        if p.get("entries"):
            e = p["entries"][0]
            lang, ss = next(iter(e["glosses"].items()))
            gl = f'{e["src"]}/{lang}: ' + " | ".join(ss[:2])[:120]
        print(c["kind"], c["surface"], "".join(f"{x}({r})" if r else x for x, r in p["ruby"]),
              [g for q in c["parts"] for g in q["gram"]], gl)
