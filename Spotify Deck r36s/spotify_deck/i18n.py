# -*- coding: utf-8 -*-
"""
Traduzioni / translations for Spotify Deck.

Nessuna dipendenza (niente pygame): lo usano sia spotify_deck.py sia get_token.py.
No dependencies (no pygame): used by both spotify_deck.py and get_token.py.

Ogni lingua e' un file  lang/<codice>.json  (es. lang/it.json).
Each language is one file  lang/<code>.json.  To add a language:
    1) copy lang/en.json to lang/xx.json
    2) translate the values (keep %d / %s, and the "|" in error messages)
    3) run  python3 check_lang.py xx   to verify placeholders and lengths
No code changes needed: the language shows up in the menu by itself.

Special keys (start with "_"):
    _name   language name in its own language (shown in the language menu)
    _kb     optional extra keyboard layer(s) for the search keyboard
            (list of layers, each layer = 4 strings of exactly 10 characters)
"""
import bisect
import json
import locale
import os

BASE = os.path.dirname(os.path.abspath(__file__))
LANG_DIR = os.path.join(BASE, "lang")
DEFAULT = "en"

_tables = {}
_cur = DEFAULT

# Caratteri (codepoint) presenti nel font pixel assets/PressStart2P-Regular.ttf:
# ASCII, Latin-1, Latin Extended-A, Greco, Cirillico e un po' di simboli.
# Tutto il resto (CJK, arabo, ebraico, thai, hindi, vietnamita...) non c'e'.
GLYPH_RANGES = (
    (32, 127), (160, 328), (330, 353), (356, 383), (402, 402), (538, 539), (700, 700), (710, 711),
    (713, 715), (727, 733), (768, 769), (806, 806), (821, 821), (890, 890), (894, 894), (900, 906),
    (908, 908), (910, 929), (931, 974), (1024, 1119), (1122, 1123), (1130, 1131), (1138, 1141),
    (1168, 1181), (1184, 1189), (1194, 1201), (1206, 1211), (1216, 1218), (1227, 1228), (1231, 1241),
    (1244, 1247), (1250, 1257), (1262, 1273), (1306, 1309), (1316, 1317), (8211, 8213), (8216, 8218),
    (8220, 8222), (8224, 8226), (8230, 8230), (8240, 8240), (8249, 8250), (8260, 8260), (8364, 8364),
    (8470, 8470), (8482, 8482), (8592, 8595),
)
_GL_STARTS = [a for a, _ in GLYPH_RANGES]


def has_glyph(o):
    """True se il font pixel ha il carattere con codepoint 'o'."""
    i = bisect.bisect_right(_GL_STARTS, o) - 1
    return i >= 0 and o <= GLYPH_RANGES[i][1]


def _load(code):
    if code in _tables:
        return _tables[code]
    path = os.path.join(LANG_DIR, code + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    _tables[code] = data
    return data


def available():
    """Lista [(codice, nome nativo)] ordinata; 'en' sempre presente."""
    out = []
    try:
        names = sorted(n[:-5] for n in os.listdir(LANG_DIR) if n.endswith(".json"))
    except OSError:
        names = []
    for code in names:
        tbl = _load(code)
        if tbl:
            out.append((code, str(tbl.get("_name") or code)))
    if not any(c == DEFAULT for c, _ in out):
        out.insert(0, (DEFAULT, "English"))
    # inglese in testa, poi in ordine alfabetico per nome
    out.sort(key=lambda x: (x[0] != DEFAULT, x[1].lower()))
    return out


def normalize(code):
    """'it_IT.UTF-8' -> 'it', 'pt-BR' -> 'pt'. Ritorna '' se non supportata."""
    if not code:
        return ""
    code = str(code).strip().lower().replace("-", "_")
    for cand in (code.split(".")[0], code.split("_")[0]):
        if cand and os.path.exists(os.path.join(LANG_DIR, cand + ".json")):
            return cand
    return ""


def detect():
    """Prova a indovinare la lingua dal sistema. Ritorna '' se non riesce."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE", "LANG"):
        v = os.environ.get(var, "")
        for part in v.split(":"):
            n = normalize(part)
            if n:
                return n
    try:
        n = normalize((locale.getdefaultlocale() or ("", ""))[0])
        if n:
            return n
    except Exception:
        pass
    return ""


def set_language(code):
    global _cur
    _cur = normalize(code) or DEFAULT
    _load(_cur)
    return _cur


def current():
    return _cur


def t(key, *args):
    """Testo tradotto (fallback: inglese, poi la chiave stessa)."""
    s = _load(_cur).get(key)
    if not isinstance(s, str):
        s = _load(DEFAULT).get(key)
    if not isinstance(s, str):
        s = key
    if args:
        try:
            return s % args
        except (TypeError, ValueError):
            return s
    return s


def tl(key):
    """Come t() ma per valori che sono liste di righe."""
    v = _load(_cur).get(key)
    if not isinstance(v, list):
        v = _load(DEFAULT).get(key)
    return [str(x) for x in v] if isinstance(v, list) else [key]


def _valid_layers(extra):
    out = []
    if isinstance(extra, list):
        for layer in extra:
            if (isinstance(layer, list) and len(layer) == 4
                    and all(isinstance(r, str) and len(r) == 10 for r in layer)):
                out.append(list(layer))
    return out


def kb_layers(base_layer):
    """Livelli della tastiera di ricerca (si cambia con L1/R1).

    1) latino di base; 2) quelli della lingua in uso; 3) gli alfabeti non latini
    (cirillico, greco...) di tutte le lingue installate: chi ascolta musica in
    un'altra scrittura deve poterla cercare qualunque sia la lingua dell'interfaccia.
    """
    layers = [list(base_layer)]

    def add(layer):
        if layer not in layers:
            layers.append(layer)

    for layer in _valid_layers(_load(_cur).get("_kb")):
        add(layer)
    for code, _ in available():
        for layer in _valid_layers(_load(code).get("_kb")):
            if any(ord(ch) >= 0x370 for row in layer for ch in row):
                add(layer)
    return layers
