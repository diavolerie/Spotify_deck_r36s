#!/usr/bin/env python3
"""
install_es_entry.py

Al primo avvio crea la voce "Spotify" come sistema A SE' STANTE in
EmulationStation (nome interno di default "movies", nome mostrato
"MOVIES"), cosi' compare nel menu principale allo stesso livello di
ps1/nes/ecc. invece che dentro Tools.

Se il sistema "movies" esiste gia' in es_systems.cfg (es. lo hai creato
tu a mano) NON lo tocca: si limita ad aggiungere/aggiornare la voce del
gioco "Spotify" nel suo gamelist.xml e a (ri)copiare le immagini.

Le modifiche a es_systems.cfg e gamelist.xml sono fatte con inserimenti
di testo mirati (niente parser XML che riscrive tutto il file), cosi'
non tocca commenti, formattazione o altre voci gia' presenti.

Richiamato da "Spotify Deck.sh" prima di lanciare spotify_deck.py.
Sicuro da rilanciare ad ogni avvio: se e' gia' tutto a posto non fa nulla
(vedi file marker .es_entry_installed).
"""

import os
import shutil

# ---------------------------------------------------------------- CONFIG --
# Sistema a se' stante, allo stesso livello di ps1/nes/ecc. Se hai gia' un
# nome diverso in mente, cambialo solo qui.
SYSTEM_NAME      = "spotify"     # <name> interno in es_systems.cfg
SYSTEM_FULLNAME  = "Spotify"     # nome mostrato in EmulationStation
GAME_NAME        = "Spotify"
# Tema da usare per l'icona/grafica del sistema nel carosello principale.
# Di default uguale al nome del sistema: se il TUO tema attivo non ha una
# grafica dedicata a "spotify" comparira' con l'aspetto generico/di default
# del tema (le immagini del gioco, copertina e marquee, si vedono comunque).
# Puoi cambiarlo in un tema che sai gia' supportato, es. "ports".
SYSTEM_THEME     = SYSTEM_NAME
ROM_FILENAME     = "Spotify.sh"
IMAGE_FILENAME   = "Spotify-image.png"     # icona tonda (boxart/copertina)
MARQUEE_FILENAME = "Spotify-marquee.png"   # scritta "Spotify" (logo/marquee)

# --------------------------------------------------------------- PATHS ----
HERE = os.path.dirname(os.path.abspath(__file__))      # dove sta davvero questo script
TOOLS_DIR = os.path.dirname(HERE)                       # cartella che contiene "Spotify Deck.sh"


def detect_roms_root():
    """
    /roms o /roms2 e' la cartella che contiene ps1, nes, tools, ecc.
    Non la deduciamo risalendo dalla posizione di questo script: puo' stare
    annidato in sottocartelle dentro tools, e "tools" stesso puo' essere un
    link a un percorso tutto diverso (es. /opt/system/Tools su dArkOSRE).
    Controlliamo invece direttamente i percorsi standard ArkOS/dArkOS.
    """
    scored = []
    for root in ("/roms2", "/roms"):
        if not os.path.isdir(root):
            continue
        try:
            entries = set(os.listdir(root))
        except OSError:
            entries = set()
        # cartelle "vere" di sistema, escluse tools/.emulationstation/temi/questo stesso sistema
        real_systems = entries - {"tools", ".emulationstation", "themes", SYSTEM_NAME}
        scored.append((len(real_systems), root))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]
    return "/roms"  # ultima spiaggia, se ne' /roms ne' /roms2 esistono


ROMS_ROOT = detect_roms_root()                          # /roms o /roms2, quello vero

LAUNCHER_SH = os.path.join(TOOLS_DIR, "Spotify Deck.sh")
ICON_SRC    = os.path.join(HERE, "assets", "background_icon.png")
MARQUEE_SRC = os.path.join(HERE, "assets", "system.png")

SYSTEM_DIR = os.path.join(ROMS_ROOT, SYSTEM_NAME)
IMAGES_DIR = os.path.join(SYSTEM_DIR, "images")
ROM_PATH   = os.path.join(SYSTEM_DIR, ROM_FILENAME)
GAMELIST   = os.path.join(SYSTEM_DIR, "gamelist.xml")
MARKER     = os.path.join(HERE, ".es_entry_installed")

# Prova questi percorsi in ordine: il primo che esiste e' quello usato.
ES_SYSTEMS_CANDIDATES = [
    os.path.join(ROMS_ROOT, ".emulationstation", "es_systems.cfg"),
    os.path.expanduser("~/.emulationstation/es_systems.cfg"),
    "/etc/emulationstation/es_systems.cfg",
]


def log(msg):
    print(f"[install_es_entry] {msg}")


def find_es_systems_cfg():
    for path in ES_SYSTEMS_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


AUTOGEN_START = f"<!-- spotify-deck:autogen:{SYSTEM_NAME} -->"
AUTOGEN_END = f"<!-- /spotify-deck:autogen:{SYSTEM_NAME} -->"


def build_system_block():
    return (
        f"  {AUTOGEN_START}\n"
        "  <system>\n"
        f"    <name>{SYSTEM_NAME}</name>\n"
        f"    <fullname>{SYSTEM_FULLNAME}</fullname>\n"
        f"    <path>{SYSTEM_DIR}</path>\n"
        "    <extension>.sh</extension>\n"
        "    <command>bash %ROM%</command>\n"
        "    <platform>pc</platform>\n"
        f"    <theme>{SYSTEM_THEME}</theme>\n"
        "  </system>\n"
        f"  {AUTOGEN_END}\n"
    )


def ensure_system_block(cfg_path):
    with open(cfg_path, "r", encoding="utf-8") as f:
        content = f.read()

    if AUTOGEN_START in content and AUTOGEN_END in content:
        start = content.index(AUTOGEN_START)
        end = content.index(AUTOGEN_END) + len(AUTOGEN_END)
        if f"<path>{SYSTEM_DIR}</path>" in content[start:end]:
            log(f'Sistema "{SYSTEM_NAME}" gia\' presente e corretto in es_systems.cfg.')
            return False
        # Il blocco esiste ma il percorso e' cambiato (es. un run precedente
        # aveva calcolato una cartella sbagliata): lo correggiamo sul posto.
        backup = cfg_path + ".bak-spotifydeck"
        if not os.path.exists(backup):
            shutil.copy2(cfg_path, backup)
            log(f"Backup creato: {backup}")
        content = content[:start] + build_system_block() + content[end:].split("\n", 1)[-1]
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(content)
        log(f'Percorso del sistema "{SYSTEM_NAME}" corretto in es_systems.cfg -> {SYSTEM_DIR}')
        return True

    if f"<name>{SYSTEM_NAME}</name>" in content:
        log(f'ATTENZIONE: esiste gia\' un sistema "{SYSTEM_NAME}" in es_systems.cfg non creato da '
            "questo script (niente firma autogen): lo lascio stare per non rompere nulla. Se e' un "
            "residuo di un test precedente, rimuovi a mano il blocco <system>...</system> con "
            f"<name>{SYSTEM_NAME}</name> e rilancia l'app.")
        return False

    if "</systemList>" not in content:
        log("ATTENZIONE: tag </systemList> non trovato, salto la modifica di es_systems.cfg.")
        return False

    backup = cfg_path + ".bak-spotifydeck"
    if not os.path.exists(backup):
        shutil.copy2(cfg_path, backup)
        log(f"Backup creato: {backup}")

    content = content.replace("</systemList>", build_system_block() + "</systemList>")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f'Sistema "{SYSTEM_NAME}" aggiunto a {cfg_path} (path: {SYSTEM_DIR}).')
    return True


def ensure_rom_and_images():
    os.makedirs(IMAGES_DIR, exist_ok=True)

    with open(ROM_PATH, "w", encoding="utf-8") as f:
        f.write("#!/bin/bash\n")
        f.write(f'exec "{LAUNCHER_SH}"\n')
    os.chmod(ROM_PATH, 0o755)

    img_dst = os.path.join(IMAGES_DIR, IMAGE_FILENAME)
    mq_dst = os.path.join(IMAGES_DIR, MARQUEE_FILENAME)
    if os.path.isfile(ICON_SRC):
        shutil.copy2(ICON_SRC, img_dst)
    else:
        log(f"ATTENZIONE: manca {ICON_SRC}")
    if os.path.isfile(MARQUEE_SRC):
        shutil.copy2(MARQUEE_SRC, mq_dst)
    else:
        log(f"ATTENZIONE: manca {MARQUEE_SRC}")

    return img_dst, mq_dst


def ensure_gamelist_entry():
    game_block = (
        "  <game>\n"
        f"    <path>./{ROM_FILENAME}</path>\n"
        f"    <name>{GAME_NAME}</name>\n"
        "    <desc>Telecomando Spotify per la console.</desc>\n"
        f"    <image>./images/{IMAGE_FILENAME}</image>\n"
        f"    <marquee>./images/{MARQUEE_FILENAME}</marquee>\n"
        "  </game>\n"
    )

    if os.path.isfile(GAMELIST):
        with open(GAMELIST, "r", encoding="utf-8") as f:
            content = f.read()
        if f"<path>./{ROM_FILENAME}</path>" in content:
            log("Voce Spotify gia' presente in gamelist.xml (aggiorno solo le immagini).")
            return
        if "</gameList>" in content:
            content = content.replace("</gameList>", game_block + "</gameList>")
        else:
            content += game_block
    else:
        content = (
            '<?xml version="1.0"?>\n'
            "<gameList>\n"
            f"{game_block}"
            "</gameList>\n"
        )

    with open(GAMELIST, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"Voce Spotify scritta in {GAMELIST}.")


def main():
    if os.path.exists(MARKER):
        return  # gia' installato: non rifare nulla ad ogni avvio

    log(f"ROMS_ROOT rilevato: {ROMS_ROOT}")
    log(f"Cartella sistema Spotify: {SYSTEM_DIR}")

    ensure_rom_and_images()

    cfg_path = find_es_systems_cfg()
    system_added = False
    if cfg_path:
        log(f"es_systems.cfg trovato: {cfg_path}")
        system_added = ensure_system_block(cfg_path)
    else:
        log("es_systems.cfg NON trovato in nessuno di questi percorsi:")
        for p in ES_SYSTEMS_CANDIDATES:
            log(f"  - {p}  (esiste: {os.path.isfile(p)})")
        log("Correggi ES_SYSTEMS_CANDIDATES in cima a questo file con il percorso giusto "
            "(sulla console: find / -name es_systems.cfg 2>/dev/null). Riprovo al prossimo avvio.")

    ensure_gamelist_entry()

    if cfg_path:
        # Marchiamo "fatto" solo se abbiamo trovato es_systems.cfg (che sia stato
        # appena aggiunto o gia' presente): se non lo troviamo, meglio riprovare
        # al prossimo avvio invece di restare bloccati per sempre.
        with open(MARKER, "w", encoding="utf-8") as f:
            f.write("ok\n")

    if system_added:
        log('FATTO. Riavvia EmulationStation (o riavvia la console) UNA VOLTA sola per '
            f'vedere il sistema "{SYSTEM_FULLNAME}" con dentro Spotify.')
    elif cfg_path:
        log("FATTO.")
    else:
        log("Immagini e rom creati, ma il sistema NON e' stato aggiunto a es_systems.cfg "
            "(vedi sopra). Il sistema non comparira' finche' non sistemiamo il percorso.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"Errore non bloccante, l'app parte comunque: {e}")
