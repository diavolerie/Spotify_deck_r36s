#!/bin/bash
# Launcher per il menu Tools di dArkOS.
# Mettilo in /roms2/tools/ (o /roms/tools/) INSIEME alla cartella spotify_deck/.
# Ogni .sh dentro "tools" compare come voce nel menu Tools di EmulationStation.
#
# Stesso approccio di Sticker Printer: pygame di SISTEMA (python3-pygame) con
# driver video kmsdrm. Non serve venv ne' pip: l'app usa solo pygame.

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)/spotify_deck"

cd "$PROJECT_DIR" || exit 1
: > "$PROJECT_DIR/log.txt"

# Al primissimo avvio crea la voce "Spotify" come sistema a se' stante in
# EmulationStation (vedi install_es_entry.py). Ai lanci successivi non fa nulla.
python3 install_es_entry.py >> "$PROJECT_DIR/log.txt" 2>&1

export SDL_VIDEODRIVER=${SDL_VIDEODRIVER:-kmsdrm}
python3 spotify_deck.py >> "$PROJECT_DIR/log.txt" 2>&1
