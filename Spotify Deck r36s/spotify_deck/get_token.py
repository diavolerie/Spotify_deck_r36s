#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Login a Spotify -> crea config.json con il refresh token.

ATTENZIONE: da luglio 2026 Spotify fa scadere il login dopo 6 MESI. Quando l'app
ti dice "login scaduto" (o ti avvisa 2 settimane prima) rilancia questo script e
ricopia config.json sulla console. Va rifatto anche quando cambiano i permessi
richiesti (come per la sezione SPOTIFY con la libreria).

Usa il flusso OAuth "Authorization Code + PKCE": non serve il client secret.
Serve solo python3 (nessuna libreria extra).

Prima di lanciarlo:
  1. developer.spotify.com/dashboard -> Create app
  2. Redirect URI da inserire ESATTAMENTE cosi':  http://127.0.0.1:8888/callback
  3. Spunta "Web API" e salva. Copia il "Client ID".

Uso:
  python3 get_token.py                  # apre il browser (PC)
  python3 get_token.py IL_TUO_CLIENT_ID
  python3 get_token.py --manual         # nessun server locale: incolli tu l'URL finale
                                        # (utile se lo lanci sulla console via SSH)
Poi copia config.json nella cartella spotify_deck sulla R36S.
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import i18n
    from i18n import t as tr
except ImportError:            # file lanciato da solo, senza il resto della cartella
    class _Fallback:
        DEFAULT = "en"

        def normalize(self, c):
            return ""

        def detect(self):
            return ""

        def set_language(self, c):
            return "en"
    i18n = _Fallback()

    def tr(key, *a):
        return (key % a) if a else key

REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
          "playlist-read-private playlist-read-collaborative "
          "user-library-read user-follow-read user-read-recently-played user-top-read")
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def pkce_pair():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_url(client_id, challenge, state):
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "scope": SCOPES,
        "redirect_uri": REDIRECT, "code_challenge_method": "S256",
        "code_challenge": challenge, "state": state,
    })


def exchange(client_id, code, verifier):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": client_id, "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(tr("gt_server_err", e.code, e.read().decode(errors="replace")))


def wait_for_code():
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.urlparse(self.path)
            if q.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in urllib.parse.parse_qs(q.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(tr("gt_done_page").encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 8888), Handler)
    srv.timeout = 300
    while "code" not in result and "error" not in result:
        srv.handle_request()
    srv.server_close()
    return result


def main():
    manual = "--manual" in sys.argv
    argv = sys.argv[1:]
    forced = ""
    if "--lang" in argv:
        k = argv.index("--lang")
        forced = i18n.normalize(argv[k + 1]) if k + 1 < len(argv) else ""
        argv = argv[:k] + argv[k + 2:]
    args = [a for a in argv if not a.startswith("--")]
    cfg = {}
    if os.path.exists(CFG_PATH):
        try:
            with open(CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
    i18n.set_language(forced or i18n.normalize(cfg.get("lang")) or i18n.detect() or i18n.DEFAULT)

    client_id = (args[0] if args else cfg.get("client_id") or input(tr("gt_client_prompt"))).strip()
    if not client_id:
        sys.exit(tr("gt_no_client"))

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(8)
    url = build_url(client_id, challenge, state)

    print("\n" + tr("gt_open") + "\n\n" + url + "\n")
    if manual:
        pasted = input(tr("gt_manual")).strip()
        params = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query).items()}
    else:
        try:
            webbrowser.open(url)
        except Exception:
            pass
        print(tr("gt_waiting"))
        params = wait_for_code()

    if params.get("state") != state:
        sys.exit(tr("gt_state_err"))
    if "code" not in params:
        sys.exit(tr("gt_denied", params.get("error", "?")))

    tok = exchange(client_id, params["code"], verifier)
    if not tok.get("refresh_token"):
        sys.exit(tr("gt_no_refresh"))
    cfg.update({"client_id": client_id, "refresh_token": tok["refresh_token"],
                "auth_time": int(time.time()), "scope": tok.get("scope", "")})
    # "lang" non viene toccato qui: se manca, l'app la chiede al primo avvio sulla console.
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print("\n" + tr("gt_ok", CFG_PATH))
    print(tr("gt_copy"))
    print(tr("gt_note"))


if __name__ == "__main__":
    main()
