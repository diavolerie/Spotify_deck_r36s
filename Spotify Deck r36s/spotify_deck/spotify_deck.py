#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPOTIFY DECK - telecomando Spotify in stile 8-bit per R36S (e handheld Linux simili)

Comanda un qualsiasi dispositivo Spotify Connect (PC, telefono, speaker) tramite
la Spotify Web API. L'audio NON esce dalla console: e' solo un telecomando.

Dipendenze: solo python3 + pygame (Pillow opzionale, usato solo come fallback
per decodificare le copertine se pygame non ha il supporto JPEG).

Uso:
    python3 spotify_deck.py            # modalita' normale (fullscreen)
    python3 spotify_deck.py --window   # in finestra 640x480 (test su PC)
    python3 spotify_deck.py --demo     # senza Spotify, dati finti (test grafica)
"""
import bisect
import io
import json
import math
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

import i18n  # noqa: E402
import qr  # noqa: E402
from i18n import t as tr, tl as trl  # noqa: E402

INFO_URL = "https://instagram.com/diavoleriee"      # link codificato nel QR della schermata INFO

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "config.json")
FONT_PATH = os.path.join(BASE, "assets", "PressStart2P-Regular.ttf")
API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
W, H = 320, 240          # canvas logico, scalato a intero sullo schermo
FPS = 30
COVER = 112              # lato copertina sul canvas (vista player)
FULL = 240               # lato copertina a schermo intero
LRCLIB = "https://lrclib.net/api"
UA = "SpotifyDeck/1.1 (R36S handheld remote)"
VIEWS = ("now", "cover", "lyrics")
LOGIN_DAYS = 182         # Spotify: i refresh token scadono dopo 6 mesi
KB_ROWS = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ0123", "456789'-.&"]
KB_MAX = 40
SCOPE_FOR = {            # permesso necessario per ogni sezione della libreria
    "saved_tracks": "user-library-read", "saved_albums": "user-library-read",
    "followed": "user-follow-read", "recent": "user-read-recently-played",
    "top_tracks": "user-top-read", "top_artists": "user-top-read",
    "playlists": "playlist-read-private", "playlist": "playlist-read-private",
}

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
DEFAULTS = {
    "client_id": "",
    "refresh_token": "",
    "theme": "NES",
    "cover_filter": True,
    "dither": True,
    "scanlines": False,
    "device_id": "",
    "pad": {},
    "view": "now",
    "lyrics_offset": 300,
    "auth_time": 0,          # quando hai fatto il login (lo scrive get_token.py)
    "lang": "",              # lingua dell'interfaccia (vuoto = si sceglie al primo avvio)
    "scope": "",             # permessi concessi (li scrive get_token.py)
}
CFG = {}
CFG_LOCK = threading.Lock()


def load_cfg():
    CFG.update(DEFAULTS)
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            CFG.update(json.load(f))
    except (OSError, ValueError):
        pass


def save_cfg():
    with CFG_LOCK:
        tmp = CFG_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(CFG, f, indent=2)
            os.replace(tmp, CFG_PATH)
        except OSError:
            pass


# ----------------------------------------------------------------------------
# TEMI
# ----------------------------------------------------------------------------
NES_PAL = [
    (0, 0, 0), (124, 124, 124), (188, 188, 188), (252, 252, 252),
    (0, 0, 252), (0, 88, 248), (0, 120, 248), (60, 188, 252), (164, 228, 252),
    (104, 68, 252), (152, 120, 248), (216, 184, 248),
    (148, 0, 132), (216, 0, 204), (248, 120, 248),
    (168, 0, 32), (228, 0, 88), (248, 88, 152),
    (168, 16, 0), (248, 56, 0), (248, 120, 88), (252, 160, 68),
    (172, 124, 0), (248, 184, 0), (248, 216, 120), (240, 208, 176),
    (80, 48, 0), (136, 20, 0), (0, 104, 0), (0, 168, 0),
    (88, 216, 84), (184, 248, 24), (0, 168, 68), (88, 248, 152),
    (0, 136, 136), (0, 232, 216), (0, 64, 88),
]

C64_PAL = [
    (0, 0, 0), (255, 255, 255), (136, 57, 50), (103, 182, 189),
    (139, 79, 150), (85, 160, 73), (64, 49, 141), (191, 206, 114),
    (139, 84, 41), (87, 66, 0), (184, 105, 98), (80, 80, 80),
    (120, 120, 120), (148, 224, 137), (120, 105, 196), (159, 159, 159),
]

QR_MIN_CONTRAST = 6.0   # soglia di sicurezza per la scansione (WCAG AA "normale" e' 4.5)


def _srgb_lin(v):
    v = v / 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _luminance(c):
    r, g, b = c
    return 0.2126 * _srgb_lin(r) + 0.7152 * _srgb_lin(g) + 0.0722 * _srgb_lin(b)


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    la, lb = max(la, lb), min(la, lb)
    return (la + 0.05) / (lb + 0.05)


def _blend(c, target, t):
    return tuple(max(0, min(255, round(c[i] + (target[i] - c[i]) * t))) for i in range(3))


def qr_theme_colors(T):
    """(scuro, chiaro) per il QR: colori del tema, alzati di contrasto solo se serve.

    Si parte dalla coppia testo/sfondo migliore del tema (bg o panel, quella
    piu' leggibile); se non basta per una scansione affidabile, i due colori
    vengono spostati - insieme, di poco - verso il nero e il bianco, fino a
    raggiungere QR_MIN_CONTRAST. Niente piu' box bianco fisso: si adatta al
    tema e resta invisibile quando il tema e' gia' leggibile da solo.
    """
    text = T["text"]
    alt = T["bg"] if _contrast(text, T["bg"]) >= _contrast(text, T["panel"]) else T["panel"]
    # un QR "invertito" (modulo scuro piu' chiaro dello sfondo) non lo legge quasi
    # nessuno scanner: il modulo scuro deve essere sempre il colore oggettivamente
    # piu' scuro dei due, non per forza quello che il tema chiama "text".
    dark, light = (text, alt) if _luminance(text) <= _luminance(alt) else (alt, text)
    if _contrast(dark, light) >= QR_MIN_CONTRAST:
        return dark, light
    to_dark, to_light = (0, 0, 0), (255, 255, 255)
    for i in range(1, 21):
        t = i / 20
        d, l = _blend(dark, to_dark, t), _blend(light, to_light, t)
        if _contrast(d, l) >= QR_MIN_CONTRAST:
            return d, l
    return (0, 0, 0), (255, 255, 255)


THEMES = [
    {   # NES: palette a 37 colori della PPU, dithering ordinato
        "name": "NES", "kind": "pal", "pal": NES_PAL, "spread": 44, "contrast": 1.12,
        "cover_px": 56,
        "bg": (0, 0, 0), "bg2": None, "panel": (0, 0, 188), "text": (252, 252, 252),
        "dim": (124, 124, 124), "accent": (248, 184, 0), "hi": (216, 40, 0),
        "hi_text": (252, 252, 252), "bar_fill": (88, 216, 84), "bar_bg": (60, 60, 60),
        "frame": (252, 252, 252), "shadow": (0, 0, 188),
    },
    {   # GAME BOY: 4 verdi
        "name": "GAME BOY", "kind": "mono",
        "pal": [(15, 56, 15), (48, 98, 48), (120, 158, 20), (155, 188, 15)],
        "cover_px": 56,
        "bg": (155, 188, 15), "bg2": None, "panel": (120, 158, 20), "text": (15, 56, 15),
        "dim": (48, 98, 48), "accent": (15, 56, 15), "hi": (15, 56, 15),
        "hi_text": (155, 188, 15), "bar_fill": (15, 56, 15), "bar_bg": (104, 144, 22),
        "frame": (15, 56, 15), "shadow": (48, 98, 48),
    },
    {   # GAME BOY POCKET: 4 grigi
        "name": "GB POCKET", "kind": "mono",
        "pal": [(16, 16, 16), (88, 88, 88), (168, 168, 168), (240, 240, 240)],
        "cover_px": 56,
        "bg": (240, 240, 240), "bg2": None, "panel": (200, 200, 200), "text": (16, 16, 16),
        "dim": (110, 110, 110), "accent": (16, 16, 16), "hi": (16, 16, 16),
        "hi_text": (240, 240, 240), "bar_fill": (16, 16, 16), "bar_bg": (200, 200, 200),
        "frame": (16, 16, 16), "shadow": (168, 168, 168),
    },
    {   # PS1: poca profondita' colore + dithering 4x4, risoluzione piu' alta
        "name": "PS1", "kind": "poster", "levels": 8, "contrast": 1.08,
        "cover_px": 112,
        "bg": (6, 6, 30), "bg2": (30, 30, 110), "panel": (40, 40, 120), "text": (224, 224, 240),
        "dim": (128, 128, 176), "accent": (248, 208, 48), "hi": (72, 104, 208),
        "hi_text": (255, 255, 255), "bar_fill": (80, 168, 255), "bar_bg": (24, 24, 64),
        "frame": (192, 192, 208), "shadow": (0, 0, 0),
    },
    {   # C64: schermata di boot blu / azzurro
        "name": "C64", "kind": "pal", "pal": C64_PAL, "spread": 60, "contrast": 1.12,
        "cover_px": 56,
        "bg": (64, 49, 141), "bg2": None, "panel": (48, 36, 110), "text": (160, 150, 235),
        "dim": (140, 126, 214), "accent": (191, 206, 114), "hi": (160, 150, 235),
        "hi_text": (64, 49, 141), "bar_fill": (148, 224, 137), "bar_bg": (80, 66, 160),
        "frame": (160, 150, 235), "shadow": (32, 24, 90),
    },
]

for _t in THEMES:
    # risoluzione "pixel" della copertina a schermo intero (deve dividere 240)
    _t.setdefault("full_px", 120 if _t["kind"] == "poster" else 80)


def theme_index(name):
    for i, t in enumerate(THEMES):
        if t["name"] == name:
            return i
    return 0


# ----------------------------------------------------------------------------
# FILTRO 8-BIT PER LE COPERTINE (solo pygame, niente numpy)
# ----------------------------------------------------------------------------
BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def _nearest(pal, r, g, b):
    best, bd = pal[0], 1 << 30
    for p in pal:
        dr, dg, db = r - p[0], g - p[1], b - p[2]
        d = 2 * dr * dr + 4 * dg * dg + 3 * db * db
        if d < bd:
            bd, best = d, p
    return best


def _clamp255(v):
    return 0 if v < 0 else 255 if v > 255 else v


def quantize(small, px, T, dither):
    buf = pygame.image.tostring(small, "RGB")
    out = bytearray(px * px * 3)
    kind = T["kind"]
    contrast = T.get("contrast", 1.1)
    if kind == "mono":
        pal = T["pal"]
        lum = [(buf[i] * 299 + buf[i + 1] * 587 + buf[i + 2] * 114) // 1000
               for i in range(0, len(buf), 3)]
        s = sorted(lum)
        lo, hi = s[len(s) * 2 // 100], s[-1 - len(s) * 2 // 100]
        if hi - lo < 24:
            hi = lo + 24
        n = len(pal) - 1
        for i, l in enumerate(lum):
            y, x = divmod(i, px)
            v = (l - lo) / float(hi - lo)
            v = 0.0 if v < 0 else 1.0 if v > 1 else v
            pos = v * n
            base = int(pos)
            if dither:
                lvl = base + (1 if (pos - base) > (BAYER[y & 3][x & 3] + 0.5) / 16.0 else 0)
            else:
                lvl = int(pos + 0.5)
            c = pal[min(lvl, n)]
            o = i * 3
            out[o], out[o + 1], out[o + 2] = c
    elif kind == "poster":
        L = T["levels"]
        step = 255.0 / (L - 1)
        for i in range(px * px):
            y, x = divmod(i, px)
            thr = (BAYER[y & 3][x & 3] + 0.5) / 16.0 if dither else 0.5
            for k in range(3):
                c = _clamp255((buf[i * 3 + k] - 128) * contrast + 128)
                q = int(c / step + thr)
                out[i * 3 + k] = int(round(min(q, L - 1) * step))
    else:
        pal = T["pal"]
        cache = T.setdefault("_cache", {})
        spread = T.get("spread", 48)
        for i in range(px * px):
            y, x = divmod(i, px)
            d = ((BAYER[y & 3][x & 3] + 0.5) / 16.0 - 0.5) * spread if dither else 0
            o = i * 3
            r = _clamp255((buf[o] - 128) * contrast + 128 + d)
            g = _clamp255((buf[o + 1] - 128) * contrast + 128 + d)
            b = _clamp255((buf[o + 2] - 128) * contrast + 128 + d)
            key = (int(r) >> 3, int(g) >> 3, int(b) >> 3)
            c = cache.get(key)
            if c is None:
                c = cache[key] = _nearest(pal, (key[0] << 3) + 4, (key[1] << 3) + 4, (key[2] << 3) + 4)
            out[o], out[o + 1], out[o + 2] = c
    return pygame.image.fromstring(bytes(out), (px, px), "RGB")


def make_cover(raw, size=COVER, px=None):
    """Copertina originale -> Surface size x size con il filtro del tema attivo."""
    T = THEMES[theme_index(CFG["theme"])]
    if px is None:
        px = T["cover_px"]
    w, h = raw.get_size()
    side = min(w, h)
    sq = pygame.Surface((side, side), 0, 32)
    sq.blit(raw, (0, 0), pygame.Rect((w - side) // 2, (h - side) // 2, side, side))
    if not CFG["cover_filter"]:
        return pygame.transform.smoothscale(sq, (size, size))
    small = pygame.transform.smoothscale(sq, (px, px))
    out = quantize(small, px, T, CFG["dither"])
    if px != size:
        out = pygame.transform.scale(out, (size, size))   # nearest = pixel netti
    return out


def make_covers(raw):
    T = THEMES[theme_index(CFG["theme"])]
    return make_cover(raw, COVER, T["cover_px"]), make_cover(raw, FULL, T["full_px"])


def ambient_bg(raw):
    """Sfondo per la vista copertina a schermo intero: la copertina vera e
    propria, sfocata (downscale + upscale, come lo sfondo "ambient" di
    Spotify), con un leggero scurimento uniforme sopra solo per leggibilita'.
    Scurire in modo uniforme non cambia la tinta (stesso fattore su R,G,B),
    quindi il colore resta quello reale della copertina."""
    if raw is None:
        return None
    try:
        w, h = raw.get_size()
        side = min(w, h)
        sq = pygame.Surface((side, side), 0, 32)
        sq.blit(raw, (0, 0), pygame.Rect((w - side) // 2, (h - side) // 2, side, side))
        # due passaggi di downscale/upscale = sfocatura morbida "vera", non
        # una semplice media dei bordi: i colori restano quelli della foto.
        blurred = pygame.transform.smoothscale(sq, (24, 24))
        blurred = pygame.transform.smoothscale(blurred, (64, 64))
        blurred = pygame.transform.smoothscale(blurred, (W, H))
        bg = blurred.convert()
        dark = pygame.Surface((W, H)).convert()
        dark.set_alpha(80)     # leggero scurimento (~31%), stessa tinta
        dark.fill((0, 0, 0))
        bg.blit(dark, (0, 0))
    except Exception:
        return None
    return bg


def decode_image(data):
    try:
        return pygame.image.load(io.BytesIO(data), "cover.jpg")
    except Exception:
        from PIL import Image  # fallback opzionale
        im = Image.open(io.BytesIO(data)).convert("RGB")
        return pygame.image.fromstring(im.tobytes(), im.size, "RGB")


# ----------------------------------------------------------------------------
# SPOTIFY API (solo libreria standard)
# ----------------------------------------------------------------------------
class AuthError(Exception):
    pass


def http(method, url, headers=None, data=None, timeout=10):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, body, e.headers


class Spotify:
    def __init__(self):
        self.token = ""
        self.exp = 0.0

    def refresh(self):
        if not CFG.get("client_id") or not CFG.get("refresh_token"):
            raise AuthError("NO LOGIN")
        data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "refresh_token": CFG["refresh_token"],
            "client_id": CFG["client_id"],
        }).encode()
        st, body, _ = http("POST", TOKEN_URL,
                           {"Content-Type": "application/x-www-form-urlencoded"}, data)
        if st in (400, 401):
            raise AuthError("LOGIN EXPIRED")
        if st != 200:
            raise IOError("token endpoint %d" % st)
        j = json.loads(body.decode("utf-8"))
        self.token = j["access_token"]
        self.exp = time.time() + int(j.get("expires_in", 3600)) - 60
        if j.get("refresh_token") and j["refresh_token"] != CFG["refresh_token"]:
            CFG["refresh_token"] = j["refresh_token"]
            save_cfg()

    def call(self, method, path, params=None, body=None, _retry=True):
        if time.time() >= self.exp:
            self.refresh()
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Authorization": "Bearer " + self.token}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        elif method in ("PUT", "POST"):
            data = b""          # Spotify vuole Content-Length: 0
        st, raw, hdr = http(method, url, headers, data)
        if st == 401 and _retry:
            self.exp = 0
            return self.call(method, path, params, body, False)
        if st == 429:
            try:
                time.sleep(min(int(hdr.get("Retry-After", "2")), 8))
            except ValueError:
                time.sleep(2)
        j = None
        if raw:
            try:
                j = json.loads(raw.decode("utf-8"))
            except ValueError:
                j = None
        return st, j

    def call_paged(self, path, params):
        """GET con 'limit' che si autoriduce se Spotify risponde 400: da inizio
        2026 Spotify ha abbassato senza preavviso il limite massimo consentito
        su piu' endpoint di lista (confermato per /search, segnalato da piu'
        sviluppatori anche per /artists/{id}/albums). Se il limite richiesto
        viene rifiutato, ritentiamo con un valore piu' basso invece di mostrare
        un errore evitabile.

        Se e' presente un parametro "market" e la risposta torna vuota (o in
        errore), ritentiamo senza: a seconda dell'account, "market" puo' far
        sparire risultati che invece esistono (es. nessun country associato,
        o catalogo non disponibile in quel mercato specifico ma disponibile
        globalmente). Usiamo il primo risultato non vuoto tra i due."""
        st, j = self.call("GET", path, params)
        lim = params.get("limit") if params else None
        if st == 400 and lim and lim > 10:
            params = dict(params, limit=10)
            st, j = self.call("GET", path, params)
        empty = not (st == 200 and (j or {}).get("items"))
        if empty and params and params.get("market"):
            p2 = {k: v for k, v in params.items() if k != "market"}
            st2, j2 = self.call("GET", path, p2)
            if st2 == 200 and (j2 or {}).get("items"):
                return st2, j2
        return st, j


def api_error(st, j):
    """Ritorna (reason, message) da una risposta d'errore Spotify."""
    err = (j or {}).get("error") if isinstance(j, dict) else None
    if isinstance(err, dict):
        return err.get("reason", ""), err.get("message", "")
    return "", ""


# ----------------------------------------------------------------------------
# STATO CONDIVISO + WORKER (thread di rete)
# ----------------------------------------------------------------------------
class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.player = None       # dict o None
        self.fetched = 0.0
        self.online = True
        self.devices = None      # None = in caricamento
        self.playlists = None
        self.toast_msg = ""
        self.toast_until = 0.0
        self.cover = None
        self.cover_full = None
        self.cover_bg = None
        self.cover_ver = 0
        self.lyrics = None       # dict {id, status, synced/plain}
        self.browse = {}         # risposte della navigazione libreria, per id richiesta
        self.fatal = ""

    def toast(self, msg, secs=3.0):
        self.toast_msg = msg
        self.toast_until = time.time() + secs


def pick_image(images):
    if not images:
        return ""
    good = [i for i in images if (i.get("width") or 0) >= 200]
    if good:
        return min(good, key=lambda i: i.get("width") or 0).get("url", "")
    return images[0].get("url", "")


def parse_player(j):
    it = j.get("item") or {}
    if it.get("type") == "episode":
        show = it.get("show") or {}
        artist, album = show.get("publisher", ""), show.get("name", "")
        artist1 = artist
        images = it.get("images") or show.get("images") or []
    else:
        artist = ", ".join(a.get("name", "") for a in it.get("artists", []))
        artist1 = ((it.get("artists") or [{}])[0]).get("name", "")
        alb = it.get("album") or {}
        album, images = alb.get("name", ""), alb.get("images") or []
    dev = j.get("device") or {}
    vol = dev.get("volume_percent")
    if dev.get("supports_volume") is False:
        vol = None
    return {
        "id": it.get("id") or it.get("uri") or "",
        "uri": it.get("uri") or "",
        "title": it.get("name") or "",
        "artist": artist, "album": album, "artist1": artist1,
        "kind": it.get("type") or "track",
        "dur": it.get("duration_ms") or 0,
        "prog": j.get("progress_ms") or 0,
        "playing": bool(j.get("is_playing")),
        "shuffle": bool(j.get("shuffle_state")),
        "repeat": j.get("repeat_state") or "off",
        "dev_name": dev.get("name") or "", "dev_id": dev.get("id") or "",
        "vol": vol, "img": pick_image(images), "inactive": False,
    }


# ----------------------------------------------------------------------------
# TESTI - LRCLIB (archivio libero, testi sincronizzati). Spotify non li espone
# nelle API ufficiali, quindi li cerchiamo qui per titolo/artista/durata.
# ----------------------------------------------------------------------------
_LRC = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")


def parse_lrc(text):
    out = []
    for line in (text or "").splitlines():
        stamps = _LRC.findall(line)
        if not stamps:
            continue
        txt = _LRC.sub("", line).strip()
        for m, sec in stamps:
            out.append((int((int(m) * 60 + float(sec.replace(":", "."))) * 1000), txt))
    out.sort(key=lambda x: x[0])
    return out


def clean_title(t):
    orig = t or ""
    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", orig)      # (feat. X) [Remastered]
    t = re.sub(r"\s+-\s+.*$", "", t)                    # - Remastered 2011
    return t.strip() or orig


def _lr_get(url):
    st, body, _ = http("GET", url, {"User-Agent": UA, "Accept": "application/json"}, None, 8)
    if st == 200:
        return json.loads(body.decode("utf-8"))
    if st == 404:
        return None
    raise IOError("lrclib %d" % st)


LYRICS_OVH = "https://api.lyrics.ovh/v1"


def _fetch_lrclib(p, dur, artist, title):
    j = _lr_get(LRCLIB + "/get?" + urllib.parse.urlencode(
        {"track_name": title, "artist_name": artist,
         "album_name": p.get("album") or "", "duration": dur}))
    if not j:    # ricerca piu' larga con titolo ripulito, scegliendo per durata
        res = _lr_get(LRCLIB + "/search?" + urllib.parse.urlencode(
            {"track_name": clean_title(title), "artist_name": artist})) or []
        good = [r for r in res if isinstance(r, dict) and abs((r.get("duration") or 0) - dur) <= 6] \
            if isinstance(res, list) else []
        good.sort(key=lambda r: (not r.get("syncedLyrics"), abs((r.get("duration") or 0) - dur)))
        j = good[0] if good else None
    if not j:
        return None
    if j.get("instrumental"):
        return {"status": "instrumental"}
    synced = parse_lrc(j.get("syncedLyrics") or "")
    if synced:
        return {"status": "ok", "synced": synced, "plain": None}
    plain = []
    for line in (j.get("plainLyrics") or "").splitlines():
        line = line.strip()
        if line or (plain and plain[-1]):
            plain.append(line)
    while plain and not plain[-1]:
        plain.pop()
    if plain:
        return {"status": "ok", "synced": None, "plain": plain}
    return None


def _fetch_lyrics_ovh(artist, title):
    """Sorgente di riserva (solo testo semplice, senza sincronizzazione):
    usata solo quando LRCLIB non ha proprio il brano, per i pochi artisti
    che li mancano."""
    url = "%s/%s/%s" % (LYRICS_OVH, urllib.parse.quote(artist), urllib.parse.quote(clean_title(title)))
    try:
        j = _lr_get(url)
    except Exception:
        return None
    if not j:
        return None
    plain = []
    for line in (j.get("lyrics") or "").replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line or (plain and plain[-1]):
            plain.append(line)
    while plain and not plain[-1]:
        plain.pop()
    if plain:
        return {"status": "ok", "synced": None, "plain": plain}
    return None


def fetch_lyrics(p):
    tid = p["id"]
    dur = int(round((p.get("dur") or 0) / 1000.0))
    artist = p.get("artist1") or p.get("artist") or ""
    title = p.get("title") or ""
    res = _fetch_lrclib(p, dur, artist, title)
    if not res and artist and title:
        res = _fetch_lyrics_ovh(artist, title)
    if not res:
        return {"id": tid, "status": "none"}
    res["id"] = tid
    return res


# ----------------------------------------------------------------------------
# NAVIGAZIONE LIBRERIA (sezione SPOTIFY del menu)
# ----------------------------------------------------------------------------
class BrowseError(Exception):
    """Messaggio nel formato 'TITOLO|dettaglio' mostrato a schermo."""


def _need(st, j):
    if st == 200 and j is not None:
        return j
    if st == 401:
        raise AuthError("LOGIN EXPIRED")
    _, msg = api_error(st, j)
    if st == 403 and "scope" in msg.lower():
        raise BrowseError(tr("err_perm"))
    if st == 403:
        raise BrowseError(tr("err_na"))
    if st == 404:
        raise BrowseError(tr("err_404"))
    if st == 429:
        raise BrowseError(tr("err_429"))
    raise BrowseError(tr("err_n", st))


def _names(o):
    return ", ".join((a or {}).get("name", "") for a in (o.get("artists") or []))


def n_track(t):
    if not t or not str(t.get("uri", "")).startswith("spotify:track:"):
        return None                       # salta episodi e file locali
    return {"t": "track", "name": t.get("name") or "?", "sub": _names(t), "uri": t["uri"], "id": t.get("id", "")}


def n_artist(a):
    if not a:
        return None
    return {"t": "artist", "name": a.get("name") or "?", "id": a.get("id", ""), "uri": a.get("uri", ""),
            "sub": ", ".join((a.get("genres") or [])[:2]) or tr("artist_tag")}


def n_album(a):
    if not a:
        return None
    sub = (_names(a) + "  " + (a.get("release_date") or "")[:4]).strip()
    return {"t": "album", "name": a.get("name") or "?", "sub": sub, "uri": a.get("uri", ""), "id": a.get("id", "")}


def n_playlist(p):
    if not p:
        return None
    return {"t": "playlist", "name": p.get("name") or "?", "id": p.get("id", ""), "uri": p.get("uri", ""),
            "sub": (p.get("owner") or {}).get("display_name") or ""}


def _nxt(j, off):
    return off + len(j.get("items") or []) if j.get("next") else None


def _head(label, uri):
    return [{"t": "playall", "name": label, "sub": "", "uri": uri}]


class Worker(threading.Thread):
    def __init__(self, S):
        super().__init__(daemon=True)
        self.S = S
        self.api = Spotify()
        self.q = queue.Queue()
        self.running = True
        self.raw_cover = None
        self.cover_url = None
        self.lyr_cache = {}

    def cmd(self, *a):
        self.q.put(a)

    def stop(self):
        self.running = False

    # -- loop ---------------------------------------------------------------
    def run(self):
        next_poll = 0.0
        while self.running:
            try:
                c = self.q.get(timeout=0.1)
            except queue.Empty:
                c = None
            try:
                if c:
                    self.handle(c)
                    next_poll = time.time() + 0.45
                if time.time() >= next_poll:
                    self.poll()
                    p = self.S.player
                    next_poll = time.time() + (1.5 if p and p["playing"] else 3.0)
            except AuthError as e:
                self.S.fatal = str(e)
                return
            except Exception:
                self.S.online = False
                next_poll = time.time() + 4.0

    # -- polling ------------------------------------------------------------
    def poll(self):
        S = self.S
        st, j = self.api.call("GET", "/me/player", {"additional_types": "episode"})
        S.online = True
        if st == 200 and j:
            p = parse_player(j)
            S.player, S.fetched = p, time.time()
            if p["img"] != self.cover_url:
                self.load_cover(p["img"])
        elif st == 204:
            prev = S.player
            S.player = dict(prev, playing=False, inactive=True) if prev else None
            S.fetched = time.time()
        elif st >= 400:
            self.report(st, j)

    def load_cover(self, url):
        self.cover_url = url
        self.raw_cover = None
        if url:
            try:
                st, body, _ = http("GET", url)
                if st == 200:
                    self.raw_cover = decode_image(body)
            except AuthError:
                raise
            except Exception:
                self.raw_cover = None
        self.rebuild_cover()

    def rebuild_cover(self):
        small, full = make_covers(self.raw_cover) if self.raw_cover is not None else (None, None)
        bg = ambient_bg(self.raw_cover)
        with self.S.lock:
            self.S.cover, self.S.cover_full, self.S.cover_bg = small, full, bg
            self.S.cover_ver += 1

    # -- testi --------------------------------------------------------------
    def lyrics_async(self, p):
        S = self.S
        if not p or not p.get("id"):
            return
        tid = p["id"]
        cur = S.lyrics
        if cur and cur.get("id") == tid and cur.get("status") != "error":
            return
        if p.get("kind", "track") != "track":
            S.lyrics = {"id": tid, "status": "none"}
            return
        if tid in self.lyr_cache:
            S.lyrics = self.lyr_cache[tid]
            return
        S.lyrics = {"id": tid, "status": "loading"}
        threading.Thread(target=self._lyr_job, args=(dict(p),), daemon=True).start()

    def _lyr_job(self, p):
        try:
            res = fetch_lyrics(p)
        except Exception:
            res = {"id": p["id"], "status": "error"}
        if res["status"] != "error":
            if len(self.lyr_cache) > 40:
                self.lyr_cache.pop(next(iter(self.lyr_cache)))
            self.lyr_cache[p["id"]] = res
        cur = self.S.lyrics
        if cur and cur.get("id") == p["id"]:
            self.S.lyrics = res

    # -- navigazione libreria -------------------------------------------------
    def play_body(self, body):
        st, j = self.api.call("PUT", "/me/player/play", body=body)
        if st == 404 and self.ensure_device(play=False):
            st, j = self.api.call("PUT", "/me/player/play", body=body)
        if st not in (200, 202, 204):
            self.report(st, j)

    def browse(self, rid, spec, token):
        try:
            items, nxt = self._browse(spec, token)
            res = {"items": items, "next": nxt, "error": ""}
        except BrowseError as e:
            res = {"items": [], "next": None, "error": str(e)}
        except AuthError:
            raise
        except Exception:
            res = {"items": [], "next": None, "error": tr("err_net")}
        self.S.browse[rid] = res
        for k in list(self.S.browse)[:-30]:
            self.S.browse.pop(k, None)

    def _browse(self, spec, token):
        kind, call, get = spec[0], self.api.call, self.api.call_paged
        off = token if isinstance(token, int) else 0
        clean_list = lambda seq: [x for x in seq if x]  # noqa: E731
        if kind == "saved_tracks":
            j = _need(*get("/me/tracks", {"limit": 50, "offset": off}))
            return clean_list(n_track((i or {}).get("track")) for i in j.get("items") or []), _nxt(j, off)
        if kind == "playlists":
            j = _need(*get("/me/playlists", {"limit": 50, "offset": off}))
            return clean_list(n_playlist(p) for p in j.get("items") or []), _nxt(j, off)
        if kind == "followed":
            params = {"type": "artist", "limit": 50}
            if token:
                params["after"] = token
            a = _need(*get("/me/following", params)).get("artists") or {}
            nxt = (a.get("cursors") or {}).get("after") if a.get("next") else None
            return clean_list(n_artist(i) for i in a.get("items") or []), nxt
        if kind == "saved_albums":
            j = _need(*get("/me/albums", {"limit": 50, "offset": off}))
            return clean_list(n_album((i or {}).get("album")) for i in j.get("items") or []), _nxt(j, off)
        if kind == "recent":
            j = _need(*get("/me/player/recently-played", {"limit": 50}))
            seen, out = set(), []
            for i in j.get("items") or []:
                t = n_track((i or {}).get("track"))
                if t and t["uri"] not in seen:
                    seen.add(t["uri"])
                    out.append(t)
            return out, None
        if kind in ("top_tracks", "top_artists"):
            what = "tracks" if kind == "top_tracks" else "artists"
            j = _need(*get("/me/top/" + what,
                           {"limit": 50, "offset": off, "time_range": "medium_term"}))
            fn = n_track if what == "tracks" else n_artist
            return clean_list(fn(i) for i in j.get("items") or []), _nxt(j, off)
        if kind == "playlist":
            _, pid, uri = spec
            head = _head(tr("play_playlist"), uri) if token is None else []
            st, j = get("/playlists/%s/items" % pid,
                        {"limit": 50, "offset": off, "additional_types": "track"})
            if st == 401:
                raise AuthError("LOGIN EXPIRED")
            if st != 200 or not j:      # playlist non tue: Spotify non ne mostra i brani
                if token is not None:
                    return [], None
                return head + [{"t": "info", "name": tr("pl_unavailable"), "sub": tr("pl_unavailable_sub")}], None
            entries = [(x or {}).get("item") or (x or {}).get("track") for x in j.get("items") or []]
            out = clean_list(n_track(e) for e in entries)
            if token is None and not out:
                out = [{"t": "info", "name": tr("pl_none"), "sub": tr("pl_unavailable_sub")}]
            return head + out, _nxt(j, off)
        if kind == "artist":
            _, aid, uri = spec
            # "market" e' obbligatorio in pratica: senza market e senza un
            # country associato all'account (Spotify da inizio 2026 non lo
            # espone piu' in automatico), l'endpoint torna 0 risultati senza
            # errore. "from_token" = usa il mercato dell'utente loggato.
            j = _need(*get("/artists/%s/albums" % aid,
                           {"include_groups": "album,single", "market": "from_token",
                            "limit": 50, "offset": off}))
            head = _head(tr("play_artist"), uri) if token is None else []
            return head + clean_list(n_album(a) for a in j.get("items") or []), _nxt(j, off)
        if kind == "album":
            _, alid, uri = spec
            j = _need(*get("/albums/%s/tracks" % alid,
                           {"market": "from_token", "limit": 50, "offset": off}))
            head = _head(tr("play_album"), uri) if token is None else []
            return head + clean_list(n_track(t) for t in j.get("items") or []), _nxt(j, off)
        if kind == "search":
            j = _need(*call("GET", "/search", {"q": spec[1], "type": "track,artist,album,playlist", "limit": 10}))
            groups = ((tr("grp_tracks"), n_track, "tracks"), (tr("grp_artists"), n_artist, "artists"),
                      (tr("grp_albums"), n_album, "albums"), (tr("grp_playlists"), n_playlist, "playlists"))
            out = []
            for label, fn, key in groups:
                lst = clean_list(fn(x) for x in (j.get(key) or {}).get("items") or [])
                if lst:
                    out.append({"t": "nav", "name": label, "sub": str(len(lst)), "go": ("static", label, lst)})
            return out or [{"t": "info", "name": tr("no_results"), "sub": ""}], None
        raise BrowseError(tr("err_unknown"))

    # -- comandi ------------------------------------------------------------
    def report(self, st, j):
        reason, msg = api_error(st, j)
        if reason == "PREMIUM_REQUIRED":
            self.S.toast(tr("toast_premium"))
        elif reason == "NO_ACTIVE_DEVICE":
            self.S.toast(tr("toast_nodev"))
        elif st == 403:
            self.S.toast((msg or tr("toast_forbidden")).upper()[:36])
        elif st == 429:
            self.S.toast(tr("toast_429"))
        elif st >= 500:
            self.S.toast(tr("toast_server"))
        else:
            self.S.toast(tr("toast_err", st))

    def ensure_device(self, play=False):
        st, j = self.api.call("GET", "/me/player/devices")
        devs = (j or {}).get("devices", []) if st == 200 else []
        devs = [d for d in devs if d.get("id") and not d.get("is_restricted")]
        if not devs:
            self.S.toast(tr("toast_open_spotify"), 4)
            return False
        dev = (next((d for d in devs if d["id"] == CFG.get("device_id")), None)
               or next((d for d in devs if d.get("is_active")), None) or devs[0])
        st, j = self.api.call("PUT", "/me/player", body={"device_ids": [dev["id"]], "play": play})
        if st not in (200, 202, 204):
            self.report(st, j)
            return False
        time.sleep(0.7)
        return True

    def simple(self, method, path, params=None, body=None):
        st, j = self.api.call(method, path, params, body)
        if st in (200, 202, 204):
            return True
        reason, msg = api_error(st, j)
        if st == 404 or reason == "NO_ACTIVE_DEVICE":
            if self.ensure_device(play=False):
                st, j = self.api.call(method, path, params, body)
                if st in (200, 202, 204):
                    return True
            else:
                return False
        if st == 403 and "restriction" in msg.lower():
            return False    # es. "gia' in pausa": ignora
        self.report(st, j)
        return False

    def handle(self, c):
        name, a = c[0], c[1:]
        if name == "play":
            st, j = self.api.call("PUT", "/me/player/play")
            if st == 404:
                self.ensure_device(play=True)
            elif st not in (200, 202, 204):
                if not (st == 403 and "restriction" in api_error(st, j)[1].lower()):
                    self.report(st, j)
        elif name == "pause":
            self.simple("PUT", "/me/player/pause")
        elif name == "next":
            self.simple("POST", "/me/player/next")
        elif name == "prev":
            self.simple("POST", "/me/player/previous")
        elif name == "seek":
            self.simple("PUT", "/me/player/seek", {"position_ms": a[0]})
        elif name == "volume":
            self.simple("PUT", "/me/player/volume", {"volume_percent": a[0]})
        elif name == "shuffle":
            self.simple("PUT", "/me/player/shuffle", {"state": "true" if a[0] else "false"})
        elif name == "repeat":
            self.simple("PUT", "/me/player/repeat", {"state": a[0]})
        elif name == "devices":
            st, j = self.api.call("GET", "/me/player/devices")
            self.S.devices = (j or {}).get("devices", []) if st == 200 else []
        elif name == "transfer":
            dev_id, play = a
            st, j = self.api.call("PUT", "/me/player", body={"device_ids": [dev_id], "play": bool(play)})
            if st in (200, 202, 204):
                CFG["device_id"] = dev_id
                save_cfg()
                if play:
                    # Alcuni target Spotify Connect (soprattutto i client
                    # desktop) accettano il trasferimento ma ignorano il
                    # flag "play" nello stesso body e restano in pausa.
                    # Verifichiamo lo stato subito dopo e, se non risulta
                    # in riproduzione, forziamo un /play esplicito.
                    time.sleep(0.8)
                    st2, j2 = self.api.call("GET", "/me/player")
                    if not (st2 == 200 and j2 and j2.get("is_playing")):
                        self.api.call("PUT", "/me/player/play")
                self.S.toast(tr("toast_dev_set"))
            else:
                self.report(st, j)
        elif name == "browse":
            self.browse(a[0], a[1], a[2])
        elif name == "play_ctx":
            body = {"context_uri": a[0]}
            if a[1]:
                body["offset"] = {"uri": a[1]}
            self.play_body(body)
        elif name == "play_uris":
            self.play_body({"uris": list(a[0])[:50]})
        elif name == "queue":
            if self.simple("POST", "/me/player/queue", {"uri": a[0]}):
                self.S.toast(tr("toast_queued"), 2)
        elif name == "lyrics":
            self.lyrics_async(self.S.player)
        elif name == "recover":
            self.rebuild_cover()


# ----------------------------------------------------------------------------
# DEMO (nessuna rete): serve per provare grafica e comandi su PC
# ----------------------------------------------------------------------------
DEMO_TRACKS = [
    ("Neon Skyline", "The Pixel Kids", "Insert Coin", 214000, 210),
    ("Bosco Incantato Della Notte Infinita", "Chiptune Orchestra", "Overworld Themes", 187000, 120),
    ("Blue Hour", "Synth & Sun", "After Hours", 245000, 20),
]


def demo_cover(hue_shift):
    s = pygame.Surface((300, 300), 0, 32)
    for y in range(300):
        t = y / 300.0
        c = pygame.Color(0)
        c.hsva = ((hue_shift + 60 * t) % 360, 70, 95 - 45 * t, 100)
        pygame.draw.line(s, c, (0, y), (299, y))
    sun = pygame.Color(0)
    sun.hsva = ((hue_shift + 40) % 360, 55, 100, 100)
    pygame.draw.circle(s, sun, (150, 130), 78)
    for i in range(6):
        pygame.draw.rect(s, (20, 10, 50), (60, 140 + i * 14, 180, 3 + i * 2))
    for x in range(0, 300, 30):
        pygame.draw.line(s, (255, 255, 255), (150, 200), (x * 1.0, 300), 2)
    return s


DEMO_LINES = [
    "Neon rain on a quiet street", "Pixels glow beneath my feet", "Press start on a brand new night",
    "Every color turns to light", "", "Jump the gap and grab the coin",
    "Chiptune hearts in perfect tune", "Level up when the sun comes through",
    "Player one, I'm here for you", "", "Insert coin, insert coin", "Take me to the final zone",
]


def demo_lyrics(i, tid):
    if i == 0:
        return {"id": tid, "status": "ok", "plain": None,
                "synced": [(6000 + k * 7000, t) for k, t in enumerate(DEMO_LINES)]}
    if i == 1:
        return {"id": tid, "status": "ok", "synced": None,
                "plain": DEMO_LINES + ["", "A very long line that just keeps going so we can check the wrapping"]}
    return {"id": tid, "status": "none"}


def demo_browse(spec, token):
    kind = spec[0]
    ok = lambda items, nxt=None: {"items": items, "next": nxt, "error": ""}  # noqa: E731
    names = ["Neon Skyline", "Blue Hour", "Chiptune Heart", "Pixel Rain", "Level Up", "Insert Coin",
             "Final Zone", "Sunset Drive", "Player Two", "Bonus Stage", "Warp Pipe", "High Score"]

    def trk(i):
        return {"t": "track", "name": names[i % 12] + (" %d" % (i // 12 + 1) if i >= 12 else ""),
                "sub": "Demo Artist %d" % (i % 4 + 1), "uri": "spotify:track:d%d" % i, "id": "d%d" % i}

    def alb(i):
        return {"t": "album", "name": ["Overworld", "Boss Rush", "Continue?", "Save Point", "Credits"][i % 5] + " Vol.%d" % (i + 1),
                "sub": "Demo Artist %d  %d" % (i % 4 + 1, 2015 + i), "uri": "spotify:album:a%d" % i, "id": "a%d" % i}

    def art(i):
        return {"t": "artist", "name": ["The Pixel Kids", "Synth & Sun", "Chiptune Orchestra", "8 Bit Weekend"][i % 4] + ("" if i < 4 else " %d" % i),
                "sub": "chiptune, synthwave" if i % 2 else "ARTISTA", "uri": "spotify:artist:r%d" % i, "id": "r%d" % i}

    def pl(i):
        return {"t": "playlist", "name": ["Daily Mix 1", "Gym Hits", "Chiptune Essentials", "Road Trip", "Focus",
                                          "Cena con gli amici", "Una playlist dal titolo lunghissimo che non finisce mai"][i % 7],
                "sub": "Marco", "uri": "spotify:playlist:p%d" % i, "id": "p%d" % i}

    if kind == "saved_tracks":
        start = token or 0
        cnt = 30 if not token else 15
        return ok([trk(start + i) for i in range(cnt)], start + cnt if not token else None)
    if kind in ("recent", "top_tracks"):
        return ok([trk(i) for i in range(12)])
    if kind == "playlists":
        return ok([pl(i) for i in range(7)])
    if kind in ("followed", "top_artists"):
        return ok([art(i) for i in range(9)])
    if kind == "saved_albums":
        return ok([alb(i) for i in range(8)])
    if kind == "playlist":
        return ok(_head("RIPRODUCI PLAYLIST", spec[2]) + [trk(i) for i in range(10)])
    if kind == "artist":
        return ok(_head("RIPRODUCI ARTISTA", spec[2]) + [alb(i) for i in range(5)])
    if kind == "album":
        return ok(_head("RIPRODUCI ALBUM", spec[2]) + [trk(i) for i in range(9)])
    if kind == "search":
        return ok([{"t": "nav", "name": "BRANI", "sub": "5", "go": ("static", "BRANI", [trk(i) for i in range(5)])},
                   {"t": "nav", "name": "ARTISTI", "sub": "3", "go": ("static", "ARTISTI", [art(i) for i in range(3)])},
                   {"t": "nav", "name": "ALBUM", "sub": "4", "go": ("static", "ALBUM", [alb(i) for i in range(4)])},
                   {"t": "nav", "name": "PLAYLIST", "sub": "2", "go": ("static", "PLAYLIST", [pl(i) for i in range(2)])}])
    return {"items": [], "next": None, "error": "ERRORE|Demo."}


class DemoWorker(threading.Thread):
    def __init__(self, S):
        super().__init__(daemon=True)
        self.S = S
        self.running = True
        self.i = 0
        self.p = None
        self.raws = [demo_cover(h) for h in (DEMO_TRACKS[0][4], DEMO_TRACKS[1][4], DEMO_TRACKS[2][4])]
        self.load(0)

    def load(self, i):
        self.i = i % len(DEMO_TRACKS)
        t = DEMO_TRACKS[self.i]
        prev = self.p or {}
        self.p = {"id": str(self.i), "uri": "spotify:track:demo%d" % self.i,
                  "title": t[0], "artist": t[1], "album": t[2], "dur": t[3],
                  "prog": 0, "playing": prev.get("playing", True), "shuffle": prev.get("shuffle", False),
                  "repeat": prev.get("repeat", "off"), "dev_name": "DEMO PC", "dev_id": "d1",
                  "vol": prev.get("vol", 60), "img": "demo%d" % self.i, "inactive": False}
        self.publish()
        self.rebuild_cover()

    def publish(self):
        self.S.player = dict(self.p)
        self.S.fetched = time.time()

    def rebuild_cover(self):
        small, full = make_covers(self.raws[self.i])
        bg = ambient_bg(self.raws[self.i])
        with self.S.lock:
            self.S.cover, self.S.cover_full, self.S.cover_bg = small, full, bg
            self.S.cover_ver += 1

    def stop(self):
        self.running = False

    def cmd(self, *a):
        n = a[0]
        p = self.p
        if n == "play":
            p["playing"] = True
        elif n == "pause":
            p["playing"] = False
        elif n == "next":
            self.load(self.i + 1)
            return
        elif n == "prev":
            self.load(self.i - 1)
            return
        elif n == "seek":
            p["prog"] = a[1]
        elif n == "volume":
            p["vol"] = a[1]
        elif n == "shuffle":
            p["shuffle"] = bool(a[1])
        elif n == "repeat":
            p["repeat"] = a[1]
        elif n == "devices":
            self.S.devices = [
                {"id": "d1", "name": "Demo PC", "type": "Computer", "is_active": True},
                {"id": "d2", "name": "Salotto Echo", "type": "Speaker", "is_active": False},
                {"id": "d3", "name": "iPhone di Marco", "type": "Smartphone", "is_active": False},
            ]
        elif n == "browse":
            self.S.browse[a[1]] = demo_browse(a[2], a[3])
            return
        elif n in ("play_ctx", "play_uris"):
            self.S.toast("DEMO: AVVIO RIPRODUZIONE")
            return
        elif n == "queue":
            self.S.toast("DEMO: AGGIUNTO IN CODA", 2)
            return
        elif n == "transfer":
            self.S.toast("DEMO: DISPOSITIVO IMPOSTATO")
        elif n == "lyrics":
            self.S.lyrics = demo_lyrics(self.i, self.p["id"])
            return
        elif n == "recover":
            self.rebuild_cover()
            return
        self.publish()

    def run(self):
        last = time.time()
        while self.running:
            time.sleep(0.25)
            now = time.time()
            if self.p["playing"]:
                self.p["prog"] += int((now - last) * 1000)
                if self.p["prog"] >= self.p["dur"]:
                    self.load(self.i + 1)
            last = now
            self.publish()


# ----------------------------------------------------------------------------
# TESTO / ICONE
# ----------------------------------------------------------------------------
_TR = {ord(k): v for k, v in {
    "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
    "\u2014": "-", "\u2026": "...", "\u00a0": " ", "\u2022": "*",
}.items()}


def clean(s):
    # Il font 8-bit ha latino, greco e cirillico (vedi i18n.GLYPH_RANGES); il resto -> "?"
    s = str(s or "").translate(_TR)
    out = []
    for ch in s:
        o = ord(ch)
        if o < 32:
            continue
        u = ch.upper()
        if len(u) != 1:
            u = ch                      # es. "ß".upper() = "SS": teniamo "ß" (il font ce l'ha)
        out.append(u if i18n.has_glyph(ord(u)) else "?")
    s = "".join(out)
    while "??" in s:
        s = s.replace("??", "?")
    return s


def load_font(size):
    if os.path.exists(FONT_PATH):
        try:
            return pygame.font.Font(FONT_PATH, size)
        except Exception:
            pass
    return pygame.font.Font(None, int(size * 1.3))


ICONS = {
    "play": ["#.......", "###.....", "#####...", "#######.", "#######.", "#####...", "###.....", "#......."],
    "pause": [".##..##.", ".##..##.", ".##..##.", ".##..##.", ".##..##.", ".##..##.", ".##..##.", ".##..##."],
    "next": ["#.....##", "##....##", "###...##", "####..##", "####..##", "###...##", "##....##", "#.....##"],
}
ICONS["prev"] = [r[::-1] for r in ICONS["next"]]
NOTE = [
    "................", "......########..", "......########..", "......##....##..",
    "......##....##..", "......##....##..", "......##....##..", "......##....##..",
    "...####...####..", "..#####..#####..", "..#####..#####..", "...###....###...",
]

WIZ_STEPS = [          # (azione, chiave della traduzione)
    ("up", "wiz_up"), ("down", "wiz_down"), ("left", "wiz_left"), ("right", "wiz_right"),
    ("a", "wiz_a"), ("b", "wiz_b"), ("x", "wiz_x"), ("y", "wiz_y"),
    ("l", "wiz_l"), ("r", "wiz_r"), ("start", "wiz_start"), ("select", "wiz_select"),
]

KEY_DEFAULTS = {
    "key:up": "up", "key:down": "down", "key:left": "left", "key:right": "right",
    "key:z": "a", "key:x": "b", "key:a": "x", "key:s": "y", "key:q": "l", "key:w": "r",
    "key:return": "start", "key:right shift": "select", "key:backspace": "select",
}
JOY_DEFAULTS = {
    "hat:0:up": "up", "hat:0:down": "down", "hat:0:left": "left", "hat:0:right": "right",
    "axis:0:-1": "left", "axis:0:1": "right", "axis:1:-1": "up", "axis:1:1": "down",
}
# Mappa del controller "GO-Super Gamepad" della R36S (dArkOSRE).
# VERIFICATI sulla tua console (da Sticker Printer): D-pad, A, B, START, SELECT.
# PROBABILI (standard di questo pad, non ancora provati): X=2, Y=3, L1=4, R1=5.
# Se qualcuno non risponde: Menu > CONFIGURA TASTI.
PAD_GO_SUPER = {
    "up": "btn:8", "down": "btn:9", "left": "btn:10", "right": "btn:11",
    "a": "btn:1", "b": "btn:0", "start": "btn:13", "select": "btn:12",
    "x": "btn:2", "y": "btn:3", "l": "btn:4", "r": "btn:5",
}
REPEATABLE = ("up", "down", "left", "right")


class Input:
    def __init__(self):
        self.map = {}
        self.hat = {}
        self.axis = {}
        self.held = {}
        self.next_rep = {}
        self.default_pad = None
        self.reload()

    def reload(self):
        self.map = dict(KEY_DEFAULTS)
        pad = CFG.get("pad") or self.default_pad or {}
        if pad:
            for act, tok in pad.items():
                self.map[tok] = act
        else:
            self.map.update(JOY_DEFAULTS)
        self.held.clear()
        self.next_rep.clear()

    def tokens(self, ev):
        t, out = ev.type, []
        if t in (pygame.KEYDOWN, pygame.KEYUP):
            out.append(("key:" + pygame.key.name(ev.key), t == pygame.KEYDOWN))
        elif t in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
            out.append(("btn:%d" % ev.button, t == pygame.JOYBUTTONDOWN))
        elif t == pygame.JOYHATMOTION:
            x, y = ev.value
            for d, act in (("left", x < 0), ("right", x > 0), ("up", y > 0), ("down", y < 0)):
                k = (ev.hat, d)
                if self.hat.get(k, False) != act:
                    self.hat[k] = act
                    out.append(("hat:%d:%s" % (ev.hat, d), act))
        elif t == pygame.JOYAXISMOTION:
            for sign in (-1, 1):
                act = ev.value * sign > 0.6
                k = (ev.axis, sign)
                if self.axis.get(k, False) != act:
                    self.axis[k] = act
                    out.append(("axis:%d:%d" % (ev.axis, sign), act))
        return out

    def press(self, act, now):
        self.held[act] = now
        if act in REPEATABLE:
            self.next_rep[act] = now + 0.38

    def release(self, act):
        self.held.pop(act, None)
        self.next_rep.pop(act, None)

    def repeats(self, now):
        out = []
        for act in list(self.next_rep):
            if now >= self.next_rep[act]:
                out.append(act)
                self.next_rep[act] = now + 0.08
        return out


# ----------------------------------------------------------------------------
# APP
# ----------------------------------------------------------------------------
class App:
    def __init__(self, worker, S, window=False, demo=False):
        pygame.display.init()
        pygame.font.init()
        pygame.joystick.init()
        pygame.display.set_caption("Spotify Deck")
        try:
            pygame.mouse.set_visible(False)
        except Exception:
            pass
        # Stessa chiamata dell'app Sticker Printer, che sulla R36S funziona.
        self.screen = pygame.display.set_mode((640, 480))
        sw, sh = self.screen.get_size()
        self.scale = max(1, min(sw // W, sh // H))
        self.ox, self.oy = (sw - W * self.scale) // 2, (sh - H * self.scale) // 2
        self.cv = pygame.Surface((W, H)).convert()
        self.scan = None
        self.joys = []
        for i in range(pygame.joystick.get_count()):
            try:
                j = pygame.joystick.Joystick(i)
                j.init()
                self.joys.append(j)
            except pygame.error:
                pass
        self.f8, self.f16 = load_font(8), load_font(16)
        self.worker, self.S, self.demo = worker, S, demo
        self.inp = Input()
        self.known_pad = any("go-super" in j.get_name().lower() for j in self.joys)
        if self.known_pad:
            self.inp.default_pad = PAD_GO_SUPER
            self.inp.reload()
        self.running = True
        self.T = THEMES[theme_index(CFG["theme"])]
        self.bg = self.placeholder = None
        self.apply_theme(rebuild=False)
        self.cover_ver = -1
        self.cover_surf = None
        self.scr = "now"
        self.cur, self.scroll = 0, 0
        self.ovr = {}
        self.seek_ovr = None
        self.pend_vol = self.pend_seek = None
        self.premute = 0
        self.flash = ("", 0.0)
        self.mq = {}
        self.view = CFG.get("view") if CFG.get("view") in VIEWS else "now"
        self.cover_full_surf = None
        self.cover_bg_surf = None
        self.osd_until, self.last_pid, self.ly_req = 0.0, "", ""
        self.ly_pos, self.ly_last = 0.0, None
        self.stack, self.req_seq = [], 0
        self.kb_text, self.kb_r, self.kb_c = "", 0, 0
        self.kb_layers, self.kb_layer = i18n.kb_layers(KB_ROWS), 0
        self.langs, self.lang_first, self.lang_pending = [], False, False
        self.home, self.wiz_menu = "now", False       # dove tornare a fine primo avvio
        self.qr_surf, self.qr_theme = None, None        # cache: rigenerata solo se cambia il tema
        self.wiz_i, self.wiz_map, self.wiz_cool = 0, {}, 0.0
        left = self.login_days_left()
        if not demo and left is not None and left < 14:
            S.toast(tr("login_expires", max(left, 0)) if left > 0 else tr("login_expired"), 6)
        if self.joys and not CFG.get("pad") and not self.known_pad and not demo:
            self.start_wizard()      # pad sconosciuto: chiede i tasti al primo avvio

    # -- tema ---------------------------------------------------------------
    def apply_theme(self, rebuild=True):
        self.T = THEMES[theme_index(CFG["theme"])]
        T = self.T
        bg = pygame.Surface((W, H)).convert()
        if T["bg2"]:
            for y in range(0, H, 8):
                t = y / float(H)
                col = tuple(int(T["bg"][k] + (T["bg2"][k] - T["bg"][k]) * t) for k in range(3))
                bg.fill(col, (0, y, W, 8))
        else:
            bg.fill(T["bg"])
        self.bg = bg
        ph = pygame.Surface((COVER, COVER)).convert()
        ph.fill(T["panel"])
        for r, row in enumerate(NOTE):
            for c, ch in enumerate(row):
                if ch == "#":
                    ph.fill(T["dim"], (24 + c * 4, 32 + r * 4, 4, 4))
        self.placeholder = ph
        pf = pygame.Surface((FULL, FULL)).convert()
        pf.fill(T["panel"])
        for r, row in enumerate(NOTE):
            for c, ch in enumerate(row):
                if ch == "#":
                    pf.fill(T["dim"], (56 + c * 8, 72 + r * 8, 8, 8))
        self.placeholder_full = pf
        if rebuild:
            self.worker.cmd("recover")

    def set_theme(self, idx):
        CFG["theme"] = THEMES[idx % len(THEMES)]["name"]
        save_cfg()
        self.apply_theme()

    # -- testo --------------------------------------------------------------
    def txt(self, s, x, y, color, font=None, align="l"):
        s = clean(s)
        if not s:
            return
        surf = (font or self.f8).render(s, False, color)
        if align == "r":
            x -= surf.get_width()
        elif align == "c":
            x -= surf.get_width() // 2
        self.cv.blit(surf, (x, y))

    def fit(self, s, maxw, font=None):
        font = font or self.f8
        s = clean(s)
        if font.size(s)[0] <= maxw:
            return s
        while s and font.size(s + "..")[0] > maxw:
            s = s[:-1]
        return s + ".."

    def marquee(self, s, font, x, y, w, color, slot, now):
        s = clean(s)
        ent = self.mq.get(slot)
        if not ent or ent[0] != s:
            ent = self.mq[slot] = [s, now]
        if not s:
            return
        surf = font.render(s, False, color)
        tw, h = surf.get_size()
        if tw <= w:
            self.cv.blit(surf, (x, y))
            return
        gap = 32
        t = now - ent[1] - 1.2
        off = 0 if t < 0 else int(t * 26) % (tw + gap)
        self.cv.set_clip((x, y, w, h))
        self.cv.blit(surf, (x - off, y))
        self.cv.blit(surf, (x - off + tw + gap, y))
        self.cv.set_clip(None)

    def icon(self, name, x, y, scale, color):
        for r, row in enumerate(ICONS[name]):
            for c, ch in enumerate(row):
                if ch == "#":
                    self.cv.fill(color, (x + c * scale, y + r * scale, scale, scale))

    # -- stato locale con override ottimistico -------------------------------
    def eff(self, key, default, now):
        o = self.ovr.get(key)
        if o and now < o[1]:
            return o[0]
        P = self.S.player
        return P.get(key, default) if P else default

    def progress(self, now):
        P = self.S.player
        if not P:
            return 0, 0
        dur = P["dur"]
        if self.seek_ovr and now < self.seek_ovr[2]:
            base, t0 = self.seek_ovr[0], self.seek_ovr[1]
        else:
            base, t0 = P["prog"], self.S.fetched
        if self.eff("playing", False, now):
            base += (now - t0) * 1000
        return max(0, min(int(base), dur)), dur

    @staticmethod
    def fmt(ms):
        s = int(ms // 1000)
        return "%d:%02d" % (s // 60, s % 60)

    # -- azioni ---------------------------------------------------------------
    def open_scr(self, name):
        self.scr = name
        self.cur = self.scroll = 0
        if name == "devices":
            self.S.devices = None
            self.worker.cmd("devices")

    def start_wizard(self, from_menu=False):
        self.scr = "wizard"
        self.wiz_menu = from_menu
        self.wiz_i, self.wiz_map, self.wiz_cool = 0, {}, time.time() + 0.6

    def on_action(self, a, now, rep=False):
        if self.S.fatal or self.scr == "nologin":
            if a in ("a", "b", "start"):
                self.running = False
            return
        if a == "start" and "select" in self.inp.held or a == "select" and "start" in self.inp.held:
            self.running = False
            return
        if self.scr == "now":
            self.act_now(a, now, rep)
        elif self.scr == "browse" and self.stack:
            self.act_browse(a, now)
        elif self.scr == "kbd":
            self.act_kbd(a, now)
        else:
            self.act_list(a, now)

    def act_now(self, a, now, rep):
        P = self.S.player
        w = self.worker
        if a in ("a", "l", "r") and not rep:
            self.osd_until = now + 3.0
        if a == "a" and not rep:
            playing = self.eff("playing", False, now)
            if P is None or P.get("inactive"):
                w.cmd("play")
                self.ovr["playing"] = (True, now + 2.5)
            elif playing:
                w.cmd("pause")
                self.ovr["playing"] = (False, now + 2.5)
            else:
                w.cmd("play")
                self.ovr["playing"] = (True, now + 2.5)
            self.flash = ("play", now + 0.18)
        elif a in ("l", "r") and not rep:
            w.cmd("prev" if a == "l" else "next")
            self.seek_ovr = None
            self.flash = ("prev" if a == "l" else "next", now + 0.18)
        elif a in ("up", "down"):
            vol = self.eff("vol", None, now)
            if vol is None:
                self.S.toast(tr("vol_unavailable"), 1.5)
                return
            v = max(0, min(100, vol + (5 if a == "up" else -5)))
            self.ovr["vol"] = (v, now + 2.5)
            self.pend_vol = (v, now + 0.2)
        elif a in ("left", "right") and P and P["dur"]:
            if self.seek_ovr and now < self.seek_ovr[2]:
                base = self.seek_ovr[0] + (now - self.seek_ovr[1]) * 1000 * (1 if self.eff("playing", False, now) else 0)
            else:
                base = self.progress(now)[0]
            tgt = max(0, min(P["dur"] - 500, base + (10000 if a == "right" else -10000)))
            self.seek_ovr = (tgt, now, now + 2.5)
            self.pend_seek = (tgt, now + 0.4)
        elif a == "x" and not rep and P:
            v = not self.eff("shuffle", False, now)
            self.ovr["shuffle"] = (v, now + 2.5)
            w.cmd("shuffle", v)
        elif a == "y" and not rep and P:
            cur = self.eff("repeat", "off", now)
            nxt = {"off": "context", "context": "track", "track": "off"}.get(cur, "off")
            self.ovr["repeat"] = (nxt, now + 2.5)
            w.cmd("repeat", nxt)
        elif a == "b" and not rep:
            self.set_view(VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)], now)
        elif a == "start" and not rep:
            self.open_scr("menu")
        elif a == "select" and not rep:
            self.set_theme(theme_index(CFG["theme"]) + 1)
            self.S.toast(tr("theme_toast", self.T["name"]), 1.5)

    def set_view(self, v, now):
        self.view = v
        CFG["view"] = v
        save_cfg()
        if v == "lyrics":
            self.ly_req = ""
        elif v == "cover":
            self.osd_until = now + 3.0
        self.S.toast(tr({"now": "view_now", "cover": "view_cover", "lyrics": "view_lyrics"}[v]), 1.2)

    # -- sezione SPOTIFY: navigazione libreria -----------------------------------
    def login_days_left(self):
        at = CFG.get("auth_time") or 0
        return int(LOGIN_DAYS - (time.time() - at) / 86400.0) if at else None

    def home_items(self):
        nav = lambda name, go, sub="": {"t": "nav", "name": name, "sub": sub, "go": go}  # noqa: E731
        items = [
            nav(tr("home_search"), "kbd", tr("home_search_sub")),
            nav(tr("home_liked"), ("saved_tracks",), tr("home_liked_sub")),
            nav(tr("home_playlists"), ("playlists",), tr("home_playlists_sub")),
            nav(tr("home_followed"), ("followed",)),
            nav(tr("home_albums"), ("saved_albums",)),
            nav(tr("home_recent"), ("recent",)),
            nav(tr("home_top_tracks"), ("top_tracks",), tr("home_top_sub")),
            nav(tr("home_top_artists"), ("top_artists",), tr("home_top_sub")),
        ]
        left = self.login_days_left()
        if left is not None:
            items.append({"t": "info", "name": tr("home_login_row", max(left, 0)),
                          "sub": tr("home_login_row_sub")})
        return items

    def open_spec(self, title, spec):
        if spec == "kbd":
            self.scr = "kbd"
            return
        kind = spec[0]
        pg = {"title": title, "spec": spec, "items": None, "next": None, "error": "", "cur": 0, "scroll": 0,
              "req": None, "append": False, "ctx": spec[2] if kind in ("playlist", "album") else None}
        if kind == "home":
            pg["items"] = self.home_items()
        elif kind == "static":
            pg["items"] = spec[2]
        else:
            need, granted = SCOPE_FOR.get(kind), (CFG.get("scope") or "").split()
            if need and granted and need not in granted:
                pg["items"] = []
                pg["error"] = tr("err_perm")
            else:
                self.request_page(pg, None)
        self.stack.append(pg)
        self.scr = "browse"

    def request_page(self, pg, token):
        self.req_seq += 1
        pg["req"], pg["append"] = self.req_seq, token is not None
        self.worker.cmd("browse", self.req_seq, pg["spec"], token)

    def after_play(self, name, now):
        self.scr = "now"
        self.ovr["playing"] = (True, now + 3.0)
        self.osd_until = now + 3.0
        self.S.toast(tr("toast_start", name), 2.5)

    def browse_select(self, pg, now):
        it = pg["items"][pg["cur"]]
        t = it["t"]
        if t == "nav":
            self.open_spec(it["name"], it["go"])
        elif t == "more":
            if pg["req"] is None:
                self.request_page(pg, pg["next"])
        elif t == "playall":
            self.worker.cmd("play_ctx", it["uri"], None)
            self.after_play(pg["title"], now)
        elif t == "track":
            if pg["ctx"]:
                self.worker.cmd("play_ctx", pg["ctx"], it["uri"])
            else:
                self.worker.cmd("play_uris", [x["uri"] for x in pg["items"][pg["cur"]:] if x["t"] == "track"][:50])
            self.after_play(it["name"], now)
        elif t in ("artist", "album", "playlist"):
            self.open_spec(it["name"], (t, it["id"], it["uri"]))

    def act_browse(self, a, now):
        pg = self.stack[-1]
        items = pg["items"] or []
        n = len(items)
        if a == "up" and n:
            pg["cur"] = (pg["cur"] - 1) % n
        elif a == "down" and n:
            pg["cur"] = (pg["cur"] + 1) % n
        elif a == "left" and n:
            pg["cur"] = max(0, pg["cur"] - 8)
        elif a == "right" and n:
            pg["cur"] = min(n - 1, pg["cur"] + 8)
        elif a == "b":
            self.stack.pop()
            self.scr = "browse" if self.stack else "menu"
            return
        elif a == "start":
            self.scr = "now"
            return
        elif a == "a" and n:
            self.browse_select(pg, now)
        elif a == "x" and n and items[pg["cur"]]["t"] == "track":
            self.worker.cmd("queue", items[pg["cur"]]["uri"])
        if pg["cur"] < pg["scroll"]:
            pg["scroll"] = pg["cur"]
        elif pg["cur"] >= pg["scroll"] + 8:
            pg["scroll"] = pg["cur"] - 7

    def kb_submit(self):
        q = self.kb_text.strip()
        if q:
            self.open_spec(tr("search_title", q), ("search", q))

    def act_kbd(self, a, now):
        rows = self.kb_layers[self.kb_layer]
        R = len(rows)
        r, c = self.kb_r, self.kb_c
        if a in ("l", "r") and len(self.kb_layers) > 1:      # L1/R1: cambia alfabeto
            self.kb_layer = (self.kb_layer + (1 if a == "r" else -1)) % len(self.kb_layers)
            return
        if a in ("left", "right"):
            c = (c + (1 if a == "right" else -1)) % (3 if r == R else 10)
        elif a in ("up", "down"):
            nr = (r + (1 if a == "down" else -1)) % (R + 1)
            if nr == R:
                c = min(2, c * 3 // 10)
            elif r == R:
                c = (1, 4, 8)[c]
            r = nr
        elif a == "a":
            if r < R:
                if len(self.kb_text) < KB_MAX:
                    self.kb_text += rows[r][c]
            elif c == 0:
                if len(self.kb_text) < KB_MAX:
                    self.kb_text += " "
            elif c == 1:
                self.kb_text = self.kb_text[:-1]
            else:
                self.kb_submit()
        elif a == "x":
            if len(self.kb_text) < KB_MAX:
                self.kb_text += " "
        elif a == "b":
            if self.kb_text:
                self.kb_text = self.kb_text[:-1]
            else:
                self.scr = "browse"
        elif a == "y":
            self.kb_text = ""
        elif a == "start":
            self.kb_submit()
        elif a == "select":
            self.scr = "browse"
        self.kb_r, self.kb_c = r, c

    def rows(self):
        if self.scr == "menu":
            onoff = lambda b: "< %s >" % tr("on" if b else "off")  # noqa: E731
            return [
                (tr("menu_spotify"), ">"),
                (tr("menu_devices"), ""),
                (tr("menu_theme"), "< %s >" % self.T["name"]),
                (tr("menu_cover"), onoff(CFG["cover_filter"])),
                (tr("menu_dither"), onoff(CFG["dither"])),
                (tr("menu_scanlines"), onoff(CFG["scanlines"])),
                (tr("menu_sync"), "< %+.1f%s >" % (CFG["lyrics_offset"] / 1000.0, tr("sec"))),
                (tr("menu_keys"), ""),
                (tr("menu_lang"), "< %s >" % dict(i18n.available()).get(i18n.current(), i18n.current())),
                (tr("menu_info"), ">"),
                (tr("menu_exit"), ""),
            ]
        if self.scr == "lang":
            return [(name, "*" if code == i18n.current() else "") for code, name in self.langs]
        if self.scr == "devices":
            d = self.S.devices
            if d is None:
                return None
            return [(x.get("name", "?"), tr("active") if x.get("is_active") else str(x.get("type", ""))[:9].upper())
                    for x in d]
        return []

    def act_list(self, a, now):
        if self.scr == "wizard":
            return
        if self.scr == "lang" and self.lang_first and a in ("b", "start"):
            return                      # al primo avvio la lingua va scelta
        rows = self.rows()
        n = len(rows) if rows else 0
        if a == "up" and n:
            self.cur = (self.cur - 1) % n
        elif a == "down" and n:
            self.cur = (self.cur + 1) % n
        elif a in ("b", "start"):
            self.scr = "now" if self.scr == "menu" or a == "start" else "menu"
            self.cur = self.scroll = 0
            return
        elif a in ("a", "left", "right") and n:
            if self.scr == "menu":
                self.menu_do(a)
            elif self.scr == "lang":
                if a == "a":
                    self.pick_language()
                    return
            elif self.scr == "devices" and a == "a":
                d = self.S.devices[self.cur]
                # Scegliere un dispositivo da qui e' un'azione esplicita:
                # proviamo sempre ad avviare la riproduzione li', invece di
                # dipendere dallo stato "playing" corrente (spesso False,
                # es. se prima non c'era nessun dispositivo attivo).
                self.worker.cmd("transfer", d["id"], True)
                self.scr = "now"
        vis = 12
        if self.cur < self.scroll:
            self.scroll = self.cur
        elif self.cur >= self.scroll + vis:
            self.scroll = self.cur - vis + 1

    # -- lingua ---------------------------------------------------------------
    def apply_language(self, code):
        code = i18n.set_language(code)
        CFG["lang"] = code
        save_cfg()
        self.mq.clear()                 # cache dei testi scorrevoli
        self.stack = []                 # le pagine gia' caricate hanno i testi nella vecchia lingua
        self.kb_layers, self.kb_layer = i18n.kb_layers(KB_ROWS), 0
        self.kb_r = self.kb_c = 0

    def ask_language(self, first=False):
        self.langs = i18n.available()
        self.lang_first = first
        self.scr = "lang"
        codes = [c for c, _ in self.langs]
        self.cur = codes.index(i18n.current()) if i18n.current() in codes else 0
        self.scroll = max(0, self.cur - 11)

    def pick_language(self):
        self.apply_language(self.langs[self.cur][0])
        first, self.lang_first = self.lang_first, False
        self.scr = self.home if first else "menu"
        self.cur = self.scroll = 0
        if self.scr == "menu":
            self.cur = 8                # torna sulla riga LINGUA

    def cycle_language(self, step):
        codes = [c for c, _ in i18n.available()]
        i = codes.index(i18n.current()) if i18n.current() in codes else 0
        self.apply_language(codes[(i + step) % len(codes)])

    def go_home(self):
        """Fine di wizard / scelta lingua: passa al passo successivo del primo avvio."""
        if self.lang_pending:
            self.lang_pending = False
            self.ask_language(first=True)
        else:
            self.scr = self.home

    def menu_do(self, a):
        i = self.cur
        if i == 0 and a == "a":
            self.stack = []
            self.open_spec("SPOTIFY", ("home",))
        elif i == 1 and a == "a":
            self.open_scr("devices")
        elif i == 2:
            self.set_theme(theme_index(CFG["theme"]) + (-1 if a == "left" else 1))
        elif i == 3:
            CFG["cover_filter"] = not CFG["cover_filter"]
            save_cfg()
            self.worker.cmd("recover")
        elif i == 4:
            CFG["dither"] = not CFG["dither"]
            save_cfg()
            self.worker.cmd("recover")
        elif i == 5:
            CFG["scanlines"] = not CFG["scanlines"]
            save_cfg()
        elif i == 6:
            step = -100 if a == "left" else 100
            CFG["lyrics_offset"] = max(-2000, min(3000, CFG["lyrics_offset"] + step))
            save_cfg()
        elif i == 7 and a == "a":
            self.start_wizard(True)
        elif i == 8:
            if a == "a":
                self.ask_language()
            else:
                self.cycle_language(-1 if a == "left" else 1)
        elif i == 9 and a == "a":
            self.scr = "info"
        elif i == 10 and a == "a":
            self.running = False

    # -- wizard tasti ---------------------------------------------------------
    def wizard_feed(self, toks, now):
        for tok, down in toks:
            if not down:
                continue
            if tok == "key:escape":
                if self.wiz_menu:
                    self.scr = "menu"
                else:
                    self.go_home()
                return
            if tok.startswith("key:") or now < self.wiz_cool or tok in self.wiz_map.values():
                continue
            self.wiz_map[WIZ_STEPS[self.wiz_i][0]] = tok
            self.wiz_i += 1
            self.wiz_cool = now + 0.4
            if self.wiz_i >= len(WIZ_STEPS):
                CFG["pad"] = dict(self.wiz_map)
                save_cfg()
                self.inp.reload()
                self.S.toast(tr("toast_keys_saved"), 2)
                if self.wiz_menu:
                    self.scr = "now"
                else:
                    self.go_home()
            return

    # -- loop -----------------------------------------------------------------
    def handle_events(self, now):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
                continue
            toks = self.inp.tokens(ev)
            if self.scr == "wizard":
                self.wizard_feed(toks, now)
                continue
            for tok, down in toks:
                act = self.inp.map.get(tok)
                if not act:
                    continue
                if down:
                    self.inp.press(act, now)
                    self.on_action(act, now)
                else:
                    self.inp.release(act)
        if self.scr != "wizard":
            for act in self.inp.repeats(now):
                self.on_action(act, now, rep=True)

    def update(self, now):
        if self.pend_vol and now >= self.pend_vol[1]:
            self.worker.cmd("volume", self.pend_vol[0])
            self.pend_vol = None
        if self.pend_seek and now >= self.pend_seek[1]:
            self.worker.cmd("seek", int(self.pend_seek[0]))
            self.pend_seek = None
        if self.S.cover_ver != self.cover_ver:
            with self.S.lock:
                c, cf, cbg, self.cover_ver = self.S.cover, self.S.cover_full, self.S.cover_bg, self.S.cover_ver
            self.cover_surf = c.convert() if c is not None else None
            self.cover_full_surf = cf.convert() if cf is not None else None
            self.cover_bg_surf = cbg.convert() if cbg is not None else None
        P = self.S.player
        pid = P["id"] if P else ""
        if pid != self.last_pid:
            self.last_pid = pid
            self.osd_until = now + 3.5          # mostra info brano sulla copertina
        if self.view == "lyrics" and self.scr == "now" and P and pid and pid != self.ly_req and P.get("title"):
            self.ly_req = pid
            self.worker.cmd("lyrics")
        for pg in self.stack:                       # risposte della libreria
            rid = pg["req"]
            if rid is None or rid not in self.S.browse:
                continue
            res = self.S.browse.pop(rid)
            pg["req"] = None
            if res["error"]:
                if pg["append"]:
                    self.S.toast(res["error"].split("|")[0], 2.5)
                else:
                    pg["items"], pg["error"] = [], res["error"]
                continue
            if pg["append"]:
                pg["items"] = [x for x in pg["items"] if x["t"] != "more"] + res["items"]
            else:
                pg["items"] = res["items"]
            pg["next"] = res["next"]
            if pg["next"] is not None:
                pg["items"].append({"t": "more", "name": tr("load_more")})

    # -- disegno --------------------------------------------------------------
    def bar_top(self, title, right=""):
        T = self.T
        self.cv.fill(T["panel"], (0, 0, W, 16))
        self.cv.fill(T["dim"], (0, 16, W, 1))
        avail = 304 - ((self.f8.size(clean(right))[0] + 8) if right else 0)
        self.txt(self.fit(title, avail), 8, 4, T["accent"])
        if right:
            self.txt(right, 312, 4, T["text"], align="r")

    def bar_bottom(self, msg, now, hi=False):
        T = self.T
        self.cv.fill(T["hi"] if hi else T["panel"], (0, 224, W, 16))
        self.txt(self.fit(msg, 312), W // 2, 228, T["hi_text"] if hi else T["dim"], align="c")

    def draw_message(self, title, lines):
        T = self.T
        self.cv.blit(self.bg, (0, 0))
        self.bar_top("SPOTIFY DECK")
        self.txt(title, W // 2, 52, T["accent"], self.f16, "c")
        for i, l in enumerate(lines):
            self.txt(l, W // 2, 96 + i * 14, T["text"], align="c")
        self.bar_bottom(tr("msg_exit"), 0)

    def qr_surface(self):
        """QR di INFO_URL come pygame.Surface, in cache finche' il tema non cambia."""
        if self.qr_surf is None or self.qr_theme != self.T["name"]:
            dark, light = qr_theme_colors(self.T)
            mat = qr.generate(INFO_URL)
            n = len(mat)
            scale = max(2, min(6, 132 // n))
            surf = pygame.Surface((n * scale, n * scale))
            surf.fill(light)
            for r in range(n):
                for c in range(n):
                    if mat[r][c]:
                        surf.fill(dark, (c * scale, r * scale, scale, scale))
            self.qr_surf, self.qr_theme = surf, self.T["name"]
        return self.qr_surf

    def draw_info(self, now):
        # Il QR porta dritti al profilo: non serve un link "cliccabile" (la
        # console non ha un browser), basta inquadrarlo con un telefono.
        T = self.T
        self.cv.blit(self.bg, (0, 0))
        self.bar_top("SPOTIFY DECK")
        qs = self.qr_surface()
        qx, qy = (W - qs.get_width()) // 2, 22
        self.cv.blit(qs, (qx, qy))
        y = qy + qs.get_height() + 14
        self.txt(tr("info_made_by"), W // 2, y, T["dim"], align="c")
        self.txt("@diavoleriee", W // 2, y + 14, T["accent"], self.f16, "c")
        self.bar_bottom(tr("info_hint"), now)

    def draw_player(self, now):
        T, cv, S = self.T, self.cv, self.S
        P = S.player
        cv.blit(self.bg, (0, 0))
        # barra alta
        cv.fill(T["panel"], (0, 0, W, 16))
        cv.fill(T["dim"], (0, 16, W, 1))
        cv.fill(T["bar_fill"] if S.online else (210, 50, 50), (8, 5, 6, 6))
        self.txt("SPOTIFY DECK", 20, 4, T["accent"])
        dev = P["dev_name"] if P and P.get("dev_name") else ""
        self.txt(self.fit(tr("offline") if not S.online else dev, 168), 312, 4, T["text"], align="r")
        # copertina
        cv.fill(T["shadow"], (20, 32, COVER + 4, COVER + 4))
        cv.fill(T["frame"], (16, 28, COVER + 4, COVER + 4))
        cv.blit(self.cover_surf if self.cover_surf is not None else self.placeholder, (18, 30))
        # colonna destra
        playing = self.eff("playing", False, now)
        x0 = 144
        self.icon("play" if playing else "pause", x0, 30, 1, T["accent"])
        self.txt(tr("now_playing") if playing else tr("paused"), x0 + 12, 30, T["accent"])
        for i in range(4):
            hgt = 2 + 2 * int((math.sin(now * 7 + i * 1.9) + 1) * 1.5) if playing else 2
            cv.fill(T["accent"], (287 + i * 7, 38 - hgt, 4, hgt))
        if P and P["title"]:
            title, artist, album = P["title"], P["artist"], P["album"]
        else:
            title, artist, album = tr("nothing_playing"), tr("press_a_start"), ""
        self.marquee(title, self.f16, x0, 48, 168, T["text"], "t", now)
        self.marquee(artist, self.f8, x0, 72, 168, T["accent"], "a", now)
        self.marquee(album, self.f8, x0, 86, 168, T["dim"], "b", now)
        # volume
        vol = self.eff("vol", None, now)
        self.txt(tr("vol_tag"), x0, 108, T["text"])
        n = 0 if vol is None else int(round(vol * 12 / 100.0))
        for i in range(12):
            cv.fill(T["bar_fill"] if i < n else T["bar_bg"], (x0 + 32 + i * 8, 108, 7, 8))
        self.txt("--" if vol is None else str(vol), 312, 108, T["text"], align="r")
        # shuffle / repeat
        sh = self.eff("shuffle", False, now)
        rp = self.eff("repeat", "off", now)
        rep_x = max(x0 + 48, x0 + self.f8.size(clean(tr("shuffle_tag")))[0] + 10)
        for label, on, x in ((tr("shuffle_tag"), sh, x0),
                             (tr("repeat1_tag") if rp == "track" else tr("repeat_tag"), rp != "off", rep_x)):
            wtag = self.f8.size(label)[0] + 6
            if on:
                cv.fill(T["hi"], (x - 3, 124, wtag, 12))
                self.txt(label, x, 126, T["hi_text"])
            else:
                self.txt(label, x, 126, T["dim"])
        # progress
        pos, dur = self.progress(now)
        self.txt(self.fmt(pos), 16, 156, T["text"])
        self.txt(self.fmt(dur), 304, 156, T["dim"], align="r")
        cv.fill(T["frame"], (16, 166, 288, 12))
        cv.fill(T["bar_bg"], (18, 168, 284, 8))
        fw = int(284 * (pos / float(dur))) // 4 * 4 if dur else 0
        if fw:
            cv.fill(T["bar_fill"], (18, 168, fw, 8))
        # controlli
        fl = self.flash[0] if now < self.flash[1] else ""
        col = lambda n: T["accent"] if fl == n else T["text"]  # noqa: E731
        self.icon("prev", 100, 194, 2, col("prev"))
        self.icon("pause" if playing else "play", 148, 190, 3, col("play"))
        self.icon("next", 204, 194, 2, col("next"))
        # barra bassa
        if now < S.toast_until:
            self.bar_bottom(self.fit(S.toast_msg, 304), now, hi=True)
        else:
            hints = [tr("hint_1"), tr("hint_2"), tr("hint_3"), tr("hint_4"), tr("hint_5")]
            self.bar_bottom(hints[int(now / 3.0) % len(hints)], now)

    # -- vista copertina a schermo intero -------------------------------------
    def draw_cover(self, now):
        T, cv, S = self.T, self.cv, self.S
        P = S.player
        has = bool(P and P.get("title"))
        cv.blit(self.cover_bg_surf if self.cover_bg_surf is not None else self.bg, (0, 0))
        cv.blit(self.cover_full_surf if self.cover_full_surf is not None else self.placeholder_full, (40, 0))
        # volume verticale: solo per qualche istante, quando premi davvero su/giu
        vo = self.ovr.get("vol")
        if vo and now < vo[1]:
            vol = vo[0]
            self.txt("VOL", 20, 6, T["text"], align="c")
            self.txt(str(vol), 20, 18, T["accent"], align="c")
            n = int(round(vol / 10.0))
            for i in range(10):
                cv.fill(T["bar_fill"] if i < n else T["bar_bg"], (12, 202 - i * 18, 16, 14))
        # progresso in basso (sottile, sopra il bordo della copertina)
        pos, dur = self.progress(now)
        self.txt(self.fmt(pos), 2, 224, T["text"])
        self.txt(self.fmt(dur), 318, 224, T["dim"], align="r")
        cv.fill(T["frame"], (0, 233, W, 1))
        cv.fill(T["bar_bg"], (0, 234, W, 6))
        fw = int(W * (pos / float(dur))) // 4 * 4 if dur else 0
        if fw:
            cv.fill(T["bar_fill"], (0, 234, fw, 6))
        # info brano a comparsa (cambio brano / tasti / niente in riproduzione)
        if now < self.osd_until or not has:
            y0 = 193
            cv.fill(T["frame"], (40, y0, 240, 2))
            cv.fill(T["panel"], (40, y0 + 2, 240, 38))
            if has:
                self.marquee(P["title"], self.f8, 48, y0 + 6, 224, T["text"], "ot", now)
                self.marquee(P["artist"], self.f8, 48, y0 + 18, 224, T["accent"], "oa", now)
                self.marquee(P["album"], self.f8, 48, y0 + 30, 224, T["dim"], "ob", now)
            else:
                self.txt(tr("nothing_playing"), 160, y0 + 10, T["accent"], align="c")
                self.txt(tr("press_a_start"), 160, y0 + 24, T["dim"], align="c")
        if now < S.toast_until:
            self.bar_bottom(self.fit(S.toast_msg, 304), now, hi=True)

    # -- vista testo -------------------------------------------------------------
    def wrap(self, s, maxw):
        s = clean(s)
        if not s:
            return [""]
        lines, cur = [], ""
        for wd in s.split(" "):
            if not wd:
                continue
            t = (cur + " " + wd) if cur else wd
            if self.f8.size(t)[0] <= maxw:
                cur = t
                continue
            if cur:
                lines.append(cur)
            while self.f8.size(wd)[0] > maxw and len(wd) > 1:
                k = len(wd)
                while k > 1 and self.f8.size(wd[:k])[0] > maxw:
                    k -= 1
                lines.append(wd[:k])
                wd = wd[k:]
            cur = wd
        if cur:
            lines.append(cur)
        return lines or [""]

    def lyrics_rows(self, ly):
        if "rows" in ly:
            return
        src = ly["synced"] if ly.get("synced") else [(None, t) for t in ly.get("plain") or []]
        rows, first, count = [], [], []
        for i, (_, txt) in enumerate(src):
            wr = self.wrap(txt, 292)
            first.append(len(rows))
            count.append(len(wr))
            rows += [(i, x) for x in wr]
        ly["rows"], ly["first"], ly["count"] = rows, first, count
        ly["times"] = [t for t, _ in src]

    def draw_lyrics(self, now):
        T, cv, S = self.T, self.cv, self.S
        P = S.player
        ly = S.lyrics
        valid = bool(ly and P and ly.get("id") == P.get("id"))
        status = ly["status"] if valid else ("loading" if P and P.get("id") else "idle")
        cv.blit(self.bg, (0, 0))
        right = ""
        if valid and status == "ok":
            right = tr("ly_sync") if ly.get("synced") else tr("ly_nosync")
        self.bar_top(self.fit(P["title"] if P and P.get("title") else tr("ly_title"), 216), right)
        pos, dur = self.progress(now)
        RH, mid = 12, 113
        cv.set_clip((0, 20, W, 186))
        if valid and status == "ok":
            self.lyrics_rows(ly)
            rows, synced = ly["rows"], bool(ly.get("synced"))
            idx = -1
            if synced:
                idx = bisect.bisect_right(ly["times"], pos + CFG["lyrics_offset"]) - 1
                k = max(idx, 0)
                target = ly["first"][k] + ly["count"][k] / 2.0
            else:
                frac = 0.0 if not dur else max(0.0, min(1.0, (pos / float(dur) - 0.05) / 0.88))
                target = frac * len(rows)
            if self.ly_last != ly["id"]:
                self.ly_pos, self.ly_last = target, ly["id"]
            else:
                d = target - self.ly_pos
                self.ly_pos = target if abs(d) < 0.02 else self.ly_pos + d * 0.25
            if idx >= 0:
                y = mid + int(round((ly["first"][idx] - self.ly_pos) * RH))
                cv.fill(T["hi"], (8, y, 304, ly["count"][idx] * RH))
            lo = max(0, int(self.ly_pos) - 10)
            for r in range(lo, min(len(rows), int(self.ly_pos) + 11)):
                li, txt = rows[r]
                y = mid + int(round((r - self.ly_pos) * RH)) + 2
                if y - 2 < 22 or y + 10 > 204:
                    continue                    # niente righe tagliate a meta'
                cur = synced and li == idx
                if cur and not txt:
                    txt = "..."
                if not txt:
                    continue
                col = T["hi_text"] if cur else (T["dim"] if synced and li < idx else T["text"])
                self.txt(txt, W // 2, y, col, align="c")
        else:
            l1, l2 = {
                "loading": (tr("ly_loading"), "." * (1 + int(now * 3) % 3)),
                "none": (tr("ly_none"), tr("ly_none_sub")),
                "instrumental": (tr("ly_instr"), tr("ly_instr_sub")),
                "error": (tr("ly_err"), tr("ly_err_sub")),
                "idle": (tr("nothing_playing"), tr("press_a_start")),
            }[status]
            self.txt(l1, W // 2, 92, T["accent"], self.f16 if len(l1) <= 17 else self.f8, "c")
            self.txt(l2, W // 2, 116, T["dim"], align="c")
        cv.set_clip(None)
        # progresso + barra bassa
        cv.fill(T["frame"], (16, 208, 288, 10))
        cv.fill(T["bar_bg"], (18, 210, 284, 6))
        fw = int(284 * (pos / float(dur))) // 4 * 4 if dur else 0
        if fw:
            cv.fill(T["bar_fill"], (18, 210, fw, 6))
        if now < S.toast_until:
            self.bar_bottom(self.fit(S.toast_msg, 304), now, hi=True)
        else:
            cv.fill(T["panel"], (0, 224, W, 16))
            self.txt(self.fmt(pos), 8, 228, T["text"])
            self.txt(self.fmt(dur), 312, 228, T["dim"], align="r")
            self.txt(tr("ly_hint"), W // 2, 228, T["dim"], align="c")

    def draw_browse(self, now):
        T, cv, S = self.T, self.cv, self.S
        pg = self.stack[-1]
        items = pg["items"]
        cv.blit(self.bg, (0, 0))
        n = len(items) if items else 0
        more = pg["next"] is not None
        real = n - (1 if more else 0)
        right = "%d/%d%s" % (min(pg["cur"] + 1, real), real, "+" if more else "") if real > 0 else ""
        self.bar_top(self.fit(pg["title"], 208), right)
        if items is None:
            self.txt(tr("browse_loading"), W // 2, 100, T["accent"], self.f16, "c")
            self.txt("." * (1 + int(now * 3) % 3), 132, 126, T["dim"])
        elif pg["error"]:
            l1, _, l2 = pg["error"].partition("|")
            self.txt(l1, W // 2, 80, T["accent"], self.f16 if len(l1) <= 17 else self.f8, "c")
            for i, ln in enumerate(self.wrap(l2, 288)[:4]):
                self.txt(ln, W // 2, 108 + i * 12, T["dim"], align="c")
        elif not items:
            self.txt(tr("browse_empty"), W // 2, 108, T["accent"], self.f16, "c")
        else:
            RH = 24
            for i in range(8):
                idx = pg["scroll"] + i
                if idx >= n:
                    break
                it, y, sel = items[idx], 22 + i * RH, idx == pg["cur"]
                if sel:
                    cv.fill(T["hi"], (8, y, 304, RH - 2))
                tc = T["hi_text"] if sel else T["text"]
                dc = T["hi_text"] if sel else T["dim"]
                name, t, x = it["name"], it["t"], 16
                if t == "more":
                    name = tr("list_loading") if pg["req"] is not None else tr("load_more")
                    tc = T["hi_text"] if sel else T["accent"]
                elif t == "playall":
                    tc = T["hi_text"] if sel else T["accent"]
                    self.icon("play", 16, y + 6, 1, tc)
                    x = 30
                elif t == "info":
                    tc = dc
                sub = it.get("sub", "") if t not in ("more", "playall") else ""
                ty = y + 2 if sub else y + 7
                w = 296 - (x - 16)
                if sel:
                    self.marquee(name, self.f8, x, ty, w, tc, "bn", now)
                    if sub:
                        self.marquee(sub, self.f8, x, y + 12, w, dc, "bs", now)
                else:
                    self.txt(self.fit(name, w), x, ty, tc)
                    if sub:
                        self.txt(self.fit(sub, w), x, y + 12, dc)
            if pg["scroll"] > 0:
                cv.fill(T["accent"], (314, 22, 4, 4))
            if pg["scroll"] + 8 < n:
                cv.fill(T["accent"], (314, 210, 4, 4))
        if now < S.toast_until:
            self.bar_bottom(self.fit(S.toast_msg, 304), now, hi=True)
        else:
            is_track = bool(items) and pg["cur"] < len(items) and items[pg["cur"]]["t"] == "track"
            self.bar_bottom(tr("browse_hint_track") if is_track else tr("browse_hint"), now)

    def draw_kbd(self, now):
        T, cv = self.T, self.cv
        cv.blit(self.bg, (0, 0))
        self.bar_top(tr("kb_title"), "%d/%d" % (len(self.kb_text), KB_MAX))
        cv.fill(T["frame"], (16, 24, 288, 28))
        cv.fill(T["panel"], (18, 26, 284, 24))
        self.txt(self.kb_text[-16:] + ("_" if int(now * 2) % 2 == 0 else " "), 24, 30, T["text"], self.f16)
        kb_rows = self.kb_layers[self.kb_layer]
        for r, row in enumerate(kb_rows):
            for c, ch in enumerate(row):
                x, y = 20 + c * 28, 60 + r * 26
                sel = (r, c) == (self.kb_r, self.kb_c)
                cv.fill(T["hi"] if sel else T["dim"], (x, y, 26, 24))
                cv.fill(T["hi"] if sel else T["panel"], (x + 2, y + 2, 22, 20))
                self.txt(ch, x + 13, y + 4, T["hi_text"] if sel else T["text"], self.f16, "c")
        for c, label in enumerate((tr("kb_space"), tr("kb_del"), tr("kb_go"))):
            x, y = 20 + c * 96, 172
            sel = (self.kb_r, self.kb_c) == (len(kb_rows), c)
            cv.fill(T["hi"] if sel else T["dim"], (x, y, 88, 24))
            cv.fill(T["hi"] if sel else T["panel"], (x + 2, y + 2, 84, 20))
            self.txt(self.fit(label, 80), x + 44, y + 8, T["hi_text"] if sel else T["text"], align="c")
        if len(self.kb_layers) > 1:
            self.txt(tr("kb_layer_hint", self.kb_layer + 1, len(self.kb_layers)), W // 2, 204, T["dim"], align="c")
        if now < self.S.toast_until:
            self.bar_bottom(self.fit(self.S.toast_msg, 304), now, hi=True)
        else:
            self.bar_bottom(tr("kb_hint"), now)

    def draw_list(self, title, now):
        T, cv = self.T, self.cv
        rows = self.rows()
        cv.blit(self.bg, (0, 0))
        self.bar_top(title)
        if rows is None:
            self.txt(tr("list_loading"), W // 2, 110, T["accent"], align="c")
        elif not rows:
            self.txt(tr("list_empty"), W // 2, 104, T["accent"], align="c")
            self.txt(tr("devices_hint") if self.scr == "devices" else "", W // 2, 122, T["dim"], align="c")
        else:
            for i in range(12):
                idx = self.scroll + i
                if idx >= len(rows):
                    break
                y = 24 + i * 16
                label, val = rows[idx]
                sel = idx == self.cur
                if sel:
                    cv.fill(T["hi"], (8, y, 304, 14))
                col = T["hi_text"] if sel else T["text"]
                maxw = 288 - (self.f8.size(clean(val))[0] + 16 if val else 0)
                self.txt(self.fit(label, maxw), 16, y + 3, col)
                if val:
                    self.txt(val, 304, y + 3, col if sel else T["dim"], align="r")
            if self.scroll > 0:
                cv.fill(T["accent"], (314, 22, 4, 4))
            if self.scroll + 12 < len(rows):
                cv.fill(T["accent"], (314, 214, 4, 4))
        if now < self.S.toast_until:
            self.bar_bottom(self.fit(self.S.toast_msg, 304), now, hi=True)
        else:
            self.bar_bottom(tr("lang_hint") if self.scr == "lang" else tr("list_hint"), now)

    def draw_wizard(self, now):
        T, cv = self.T, self.cv
        cv.blit(self.bg, (0, 0))
        self.bar_top(tr("wiz_title"), "%d/%d" % (min(self.wiz_i + 1, len(WIZ_STEPS)), len(WIZ_STEPS)))
        self.txt(tr("wiz_press"), W // 2, 70, T["text"], align="c")
        label = tr(WIZ_STEPS[min(self.wiz_i, len(WIZ_STEPS) - 1)][1])
        self.txt(label, W // 2, 100, T["accent"], self.f16 if len(label) <= 15 else self.f8, "c")
        for i in range(len(WIZ_STEPS)):
            cv.fill(T["bar_fill"] if i < self.wiz_i else T["bar_bg"], (40 + i * 20, 150, 16, 8))
        self.bar_bottom(tr("wiz_esc"), now)

    def present(self):
        s = self.scale
        self.screen.fill((0, 0, 0))
        if s == 1:
            self.screen.blit(self.cv, (self.ox, self.oy))
        else:
            self.screen.blit(pygame.transform.scale(self.cv, (W * s, H * s)), (self.ox, self.oy))
        if CFG["scanlines"]:
            if self.scan is None:
                sw, sh = self.screen.get_size()
                self.scan = pygame.Surface((sw, sh), pygame.SRCALPHA)
                for y in range(0, sh, 2):
                    self.scan.fill((0, 0, 0, 70), (0, y, sw, 1))
            self.screen.blit(self.scan, (0, 0))
        pygame.display.flip()

    def draw(self, now):
        if self.S.fatal:
            self.draw_message(tr("fatal_title"), trl("fatal_lines"))
        elif self.scr == "nologin":
            self.draw_message(tr("nologin_title"), trl("nologin_lines"))
        elif self.scr == "now":
            {"now": self.draw_player, "cover": self.draw_cover, "lyrics": self.draw_lyrics}[self.view](now)
        elif self.scr == "wizard":
            self.draw_wizard(now)
        elif self.scr == "browse" and self.stack:
            self.draw_browse(now)
        elif self.scr == "kbd":
            self.draw_kbd(now)
        elif self.scr == "info":
            self.draw_info(now)
        else:
            self.draw_list({"menu": tr("menu_title"), "devices": tr("devices_title"),
                            "lang": tr("lang_title")}.get(self.scr, tr("menu_title")), now)
        self.present()

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            now = time.time()
            self.handle_events(now)
            self.update(now)
            self.draw(now)
            clock.tick(FPS)
        self.worker.stop()
        pygame.quit()


def main():
    load_cfg()
    demo = "--demo" in sys.argv
    forced = ""                          # --lang xx : prova una lingua senza salvarla
    if "--lang" in sys.argv:
        k = sys.argv.index("--lang")
        forced = i18n.normalize(sys.argv[k + 1] if k + 1 < len(sys.argv) else "")
    lang = i18n.normalize(CFG.get("lang"))
    i18n.set_language(forced or lang or i18n.detect() or i18n.DEFAULT)
    S = Shared()
    if demo:
        pygame.display.init()
        pygame.font.init()
        worker = DemoWorker(S)
    else:
        worker = Worker(S)
    app = App(worker, S, window="--window" in sys.argv, demo=demo)
    if not demo and (not CFG.get("client_id") or not CFG.get("refresh_token")):
        app.home = "nologin"
        if app.scr != "wizard":          # pad sconosciuto: prima i tasti, poi il messaggio
            app.scr = "nologin"
    else:
        worker.start()
    if not lang and not forced and not demo:
        app.lang_pending = True          # primo avvio: scelta della lingua
        if app.scr != "wizard":
            app.go_home()
    app.run()


if __name__ == "__main__":
    main()
