#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Controlla i file di traduzione in lang/  /  Checks the translation files in lang/.

    python3 check_lang.py          # tutte le lingue / all languages
    python3 check_lang.py it de    # solo alcune / only some

Verifica: chiavi mancanti o in piu', segnaposto (%d, %s), il "|" dei messaggi
d'errore, caratteri che il font 8-bit non ha, e la lunghezza (lo schermo e'
largo 40 caratteri: un testo troppo lungo viene tagliato con "..").
Esce con codice 1 se trova ERRORI (le lunghezze sono solo AVVISI).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import i18n  # noqa: E402

PH = re.compile(r"%[-+ 0#]*\d*(?:\.\d+)?[sd]")

# lunghezza massima (in caratteri) per gruppo di chiavi; default 38
LIMITS = [
    (("now_playing", "paused"), 16),                       # accanto all'equalizzatore
    (("shuffle_tag", "repeat_tag", "repeat1_tag"), 6),     # etichette accanto a SHUF/REP
    (("kb_space", "kb_del", "kb_go"), 10),                 # tasti della tastiera a schermo
    (("fatal_title", "nologin_title"), 20),                # titolo grande centrato
    (("menu_",), 20),                                      # voci del menu (con il valore a destra)
    (("home_",), 37),
]
LINE_KEYS = ("fatal_lines", "nologin_lines")               # righe da max 40 caratteri


def limit_for(key):
    for prefixes, n in LIMITS:
        if any(key == p or key.startswith(p) for p in prefixes):
            return n
    return 38


def load(code):
    with open(os.path.join(i18n.LANG_DIR, code + ".json"), encoding="utf-8") as f:
        return json.load(f)


def bad_glyphs(s):
    return sorted({c for c in s.upper() if ord(c) >= 32 and not i18n.has_glyph(ord(c))})


def check(code, en):
    errs, warns = [], []
    try:
        d = load(code)
    except (OSError, ValueError) as e:
        return ["%s: file non valido / invalid file: %s" % (code, e)], []
    keys = [k for k in en if not k.startswith("_")]
    for k in keys:
        if k not in d:
            errs.append("%s: manca la chiave / missing key '%s'" % (code, k))
    for k in d:
        if not k.startswith("_") and k not in en:
            errs.append("%s: chiave sconosciuta / unknown key '%s'" % (code, k))
    if not d.get("_name"):
        errs.append("%s: manca '_name' (nome della lingua nella lingua stessa)" % code)
    for k in keys:
        if k not in d:
            continue
        a, b = en[k], d[k]
        if isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                errs.append("%s: '%s' deve essere una lista di %d righe" % (code, k, len(a)))
                continue
            items = list(zip(a, b))
        else:
            if not isinstance(b, str):
                errs.append("%s: '%s' deve essere testo" % (code, k))
                continue
            items = [(a, b)]
        for ea, tb in items:
            if sorted(PH.findall(ea)) != sorted(PH.findall(tb)):
                errs.append("%s: '%s' segnaposto diversi da en (%s vs %s)" %
                            (code, k, PH.findall(ea), PH.findall(tb)))
            if ("|" in ea) != ("|" in tb):
                errs.append("%s: '%s' deve contenere il '|' come in en (titolo|dettaglio)" % (code, k))
            if not k.startswith("gt_"):
                bg = bad_glyphs(tb)
                if bg:
                    errs.append("%s: '%s' ha caratteri non disponibili nel font 8-bit: %s" %
                                (code, k, "".join(bg)))
        if k.startswith("gt_"):
            continue                                        # get_token.py: nessun limite di schermo
        if k in LINE_KEYS:
            for ln in b:
                if len(ln.upper()) > 40:
                    warns.append("%s: '%s' riga lunga %d (max 40): %s" % (code, k, len(ln), ln))
        elif k.startswith("err_"):
            head, _, tail = b.partition("|")
            if len(head.upper()) > 38:
                warns.append("%s: '%s' titolo lungo %d (max 38)" % (code, k, len(head)))
            if len(tail) > 130:
                warns.append("%s: '%s' dettaglio lungo %d (max ~130, 4 righe)" % (code, k, len(tail)))
        elif isinstance(b, str):
            plain = PH.sub("00", b)                         # %d e %s occupano ~2 caratteri
            n, m = len(plain.upper()), limit_for(k)
            if n > m:
                warns.append("%s: '%s' lungo %d (max %d): %s" % (code, k, n, m, b))
    kb = d.get("_kb")
    if kb is not None:
        if not isinstance(kb, list):
            errs.append("%s: '_kb' deve essere una lista di livelli" % code)
        else:
            for li, layer in enumerate(kb):
                if not (isinstance(layer, list) and len(layer) == 4 and all(isinstance(r, str) and len(r) == 10 for r in layer)):
                    errs.append("%s: '_kb' livello %d: servono 4 righe di ESATTAMENTE 10 caratteri" % (code, li + 1))
                    continue
                bg = bad_glyphs("".join(layer))
                if bg:
                    errs.append("%s: '_kb' livello %d: caratteri non disponibili: %s" % (code, li + 1, "".join(bg)))
    return errs, warns


def main():
    en = load("en")
    codes = [a for a in sys.argv[1:]] or [c for c, _ in i18n.available()]
    bad = 0
    for code in codes:
        errs, warns = check(code, en) if code != "en" else check("en", en)
        status = "OK" if not errs else "ERRORI"
        print("[%s] %s%s" % (code, status, "  (%d avvisi)" % len(warns) if warns else ""))
        for m in errs:
            print("   ERRORE:", m)
        for m in warns:
            print("   avviso:", m)
        bad += len(errs)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
