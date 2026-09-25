# Spotify Deck

Un telecomando Spotify 8-bit per R36S (e handheld ArkOS/dArkOS simili). Comanda play/pausa, volume, avanti/indietro nel brano, shuffle, repeat, dispositivo e playlist dalla console; l'audio esce dal dispositivo che scegli (PC, telefono, speaker...). Serve **Spotify Premium** (limite imposto dalle API di Spotify, non da questa app).

🇬🇧 *Read this guide in English: [README.md](README.md)*

![Spotify Deck su un R36S](docs/screenshot.png)

## Funzioni

- Play/pausa, brano precedente/successivo, volume, seek ±10s, shuffle, repeat
- Ricerca, brani preferiti, playlist (tue e seguite), artisti seguiti, album salvati, ascoltati di recente, top brani/artisti
- Testi sincronizzati (via [LRCLIB](https://lrclib.net), un archivio libero — non disponibile per tutti i brani)
- 5 temi: NES, Game Boy, Game Boy Pocket, PS1, C64 — con dithering 8-bit e scanlines CRT opzionali
- 7 lingue: italiano, inglese, spagnolo, francese, tedesco, portoghese, russo
- Compare in EmulationStation come **sistema a sé stante**, allo stesso livello di PS1, NES ecc. — non sepolto in un sottomenu Tools (vedi [Primo avvio](#primo-avvio--registrazione-automatica) più sotto)

## Requisiti

- Un R36S o handheld ArkOS/dArkOS compatibile
- Wi-Fi attivo sulla console
- Python 3 con `python3-pygame` installato sulla console (pacchetto di sistema — niente `venv`/`pip` sul dispositivo)
- Un account Spotify Developer gratuito e un account **Spotify Premium** per la riproduzione
- Un PC o Mac con Python 3, usato una volta sola per generare il token di accesso

## Prima di copiare qualsiasi cosa sulla SD

Ti serve un token dell'API Spotify *prima* che l'app sia utilizzabile sulla console: generalo su un computer, poi copia il file risultante sulla SD.

### 1. Crea l'app Spotify (gratis, ~2 minuti)

1. Vai su [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → **Create app**.
2. Redirect URI (deve essere identico): `http://127.0.0.1:8888/callback`
3. Spunta **Web API**, salva, copia il **Client ID**.

### 2. Login (sul tuo PC/Mac, con Python 3 installato)

```bash
python3 get_token.py IL_TUO_CLIENT_ID
```

Si apre il browser: accedi e premi **Accetta**. Viene creato `config.json` nella stessa cartella.

Alternativa, se il browser non riesce a raggiungere console/PC automaticamente:

```bash
python3 get_token.py --manual
```
(incolla l'URL finale di redirect quando richiesto)

> **Attenzione:** da luglio 2026 Spotify fa scadere questo login dopo **6 mesi**. L'app ti avvisa due settimane prima (e in Menu → SPOTIFY vedi i giorni rimasti). Quando scade, rilancia `get_token.py` e ricopia il nuovo `config.json`. Va rifatto anche quando l'app chiede un nuovo permesso (es. la sezione SPOTIFY con la libreria, o "AGGIUNGI AI PREFERITI" nel menu).

`get_token.py` segue automaticamente la lingua del tuo PC; per forzarne una diversa (es. PC in inglese ma vuoi la console in italiano):

```bash
python3 get_token.py --lang it IL_TUO_CLIENT_ID
```
Codici disponibili: `en it es fr de pt ru`.

## Installazione sulla console

Stesso schema di altri tool basati su pygame (es. Sticker Printer):

1. Copia **`Spotify Deck.sh`** e la cartella **`spotify_deck/`** insieme, senza modificarli, nella cartella `tools` della console: `/roms2/tools/` (oppure `/roms/tools/`).
2. Copia il `config.json` generato al passo 2 sopra dentro `spotify_deck/` (accanto a `spotify_deck.py`).
3. Non rinominare il launcher e non spostarlo in una sottocartella — l'app calcola alcuni percorsi dalla posizione di `Spotify Deck.sh` rispetto alla cartella `tools`, quindi tienilo direttamente dentro `tools/`.

Non serve `venv` né `pip install` sulla console: usa solo il `python3-pygame` di sistema. Driver video: `kmsdrm`.

## Primo avvio & registrazione automatica

Al **primo** avvio (da EmulationStation → Tools → "Spotify Deck"), il launcher lancia anche `install_es_entry.py`, che:

- crea un sistema EmulationStation dedicato chiamato **Spotify**, allo stesso livello di PS1, NES ecc. (non dentro Tools, non dentro Movies);
- crea una cartella corrispondente (`<roms>/spotify` di default) con dentro un solo "gioco" (`Spotify.sh`, che rilancia semplicemente l'app vera) più copertina e marquee;
- registra il sistema in `es_systems.cfg` (facendo prima un backup, `es_systems.cfg.bak-spotifydeck`);
- scrive un file marker (`spotify_deck/.es_entry_installed`) così lo fa una volta sola.

**Dopo il primissimo avvio, riavvia EmulationStation (o riavvia la console) una volta** perché il nuovo sistema venga rilevato.

Se hai già un sistema dedicato con un nome diverso, o vuoi rinominarlo, modifica `SYSTEM_NAME` / `SYSTEM_FULLNAME` in cima a `spotify_deck/install_es_entry.py` — se un sistema con quel nome esiste già in `es_systems.cfg`, viene lasciato intatto (viene solo aggiunta/aggiornata la voce del gioco). Per rifare la registrazione da capo, cancella `spotify_deck/.es_entry_installed` e rilancia l'app.

## Comandi

| Tasto | Azione |
|---|---|
| A | Play / pausa |
| L1 / R1 | Brano precedente / successivo |
| Su / Giù | Volume +/- (tieni premuto per scorrere) |
| Sinistra / Destra | Indietro / avanti di 10 secondi |
| X | Shuffle |
| Y | Repeat (off → tutto → brano) |
| B | Cambia vista: player → copertina a tutto schermo → testo |
| Select | Cambia tema al volo |
| Start | Menu (aggiungi ai preferiti, dispositivi, playlist, tema, ecc.) |
| Start + Select | Esci |

Tutti i comandi funzionano in tutte le viste. Il pad "GO-Super Gamepad" è già mappato (D-pad, A, B, Start, Select verificati). X, Y, L1, R1 usano i valori standard di questo pad ma non sono stati verificati del tutto: se uno non risponde, Menu → CONFIGURA TASTI.

Il menu si apre con **Start**:

![Menu](docs/04_menu.png)

## Viste

- **Player** — copertina + titolo + volume + barra di avanzamento

  ![Vista player](docs/01_player.png)

- **Copertina** — copertina 240×240 a tutto schermo con filtro 8-bit, volume a sinistra, stato a destra, barra sottile in fondo. Titolo/artista compaiono per qualche secondo al cambio brano o quando premi A, L1, R1.

  ![Vista copertina a tutto schermo](docs/02_copertina.png)

- **Testo** — testo del brano, riga corrente evidenziata, scorrimento automatico. Se il testo non è sincronizzato scorre in modo approssimato in base ai minuti del brano. I testi vengono da LRCLIB (non disponibili per tutti i brani). Se le righe arrivano troppo presto/tardi: Menu → SYNC TESTO.

  ![Vista testo sincronizzato](docs/03_testo.png)

L'ultima vista usata viene ricordata al prossimo avvio.

## Menu → Spotify (la tua libreria)

- **Cerca** — tastiera a schermo (D-pad muove, A scrive, B cancella, X spazio, Y svuota, Start cerca). Risultati divisi in brani/artisti/album/playlist, max 10 ciascuno (limite imposto da Spotify).

  ![Tastiera di ricerca](docs/05_ricerca.png)

- **Brani preferiti**, **Playlist** (tue + seguite), **Artisti seguiti** → album e singoli → brani, **Album salvati** → brani, **Ascoltati di recente**, **Top brani**, **Top artisti** (ultimi ~6 mesi).
- Nelle liste: Su/Giù scorri, Sinistra/Destra salta di 8, A apri/riproduci, X aggiungi in coda, B indietro, Start torna al player.

  ![Esempio di lista risultati](docs/06_libreria.png)

- Le liste lunghe caricano 50 alla volta ("CARICA ALTRI" in fondo).
- Limiti di Spotify (2026): l'elenco dei brani di una playlist si vede solo per le **tue** playlist; per quelle di altri c'è solo "RIPRODUCI PLAYLIST". I "brani più famosi" di un artista non esistono più nelle API: si vedono gli album e c'è "RIPRODUCI ARTISTA".
- Se un permesso manca compare "PERMESSI MANCANTI": rifai `get_token.py`.

## Temi

NES, Game Boy, Game Boy Pocket, PS1, C64. Menu → COPERTINA 8-BIT / DITHERING / SCANLINES CRT per regolare il look. Gli screenshot di questa guida usano il tema NES.

## Menu → Info

Una schermata con un QR code verso l'Instagram dell'autore, generato interamente dall'app stessa (`qr.py`, nessun servizio esterno, quindi non scade mai). I colori seguono il tema attivo e alzano automaticamente il contrasto solo se serve per una scansione affidabile.

![Schermata Info con QR](docs/07_info.png)

## Lingue

Italiano, inglese, spagnolo, francese, tedesco, portoghese, russo. Al primissimo avvio la console chiede quale usare; si cambia quando vuoi da Menu → LINGUA. Salvata in `config.json` (campo `"lang"`); se non impostata, la console prova a indovinarla dal sistema, altrimenti usa l'inglese.

Anche `get_token.py` (sul PC) segue automaticamente la tua lingua — vedi [Setup](#1-crea-lapp-spotify-gratis-2-minuti) sopra per forzarne una diversa.

La tastiera di ricerca ha più "pagine" di tasti: una base (A–Z), una con gli accenti della lingua scelta, e una con l'alfabeto cirillico (per cercare brani/artisti in russo). Si cambia pagina con L1/R1 mentre scrivi.

### Aggiungere una lingua

Non serve programmare:

1. Copia `spotify_deck/lang/en.json` come `spotify_deck/lang/xx.json` (`xx` = codice lingua, es. `nl` per l'olandese).
2. Traduci i valori (lascia `%d`/`%s` e il carattere `|` dove presenti).
3. La lingua compare da sola nel menu.
4. Controlla che sia a posto: `python3 check_lang.py xx` — segnala chiavi mancanti, testo troppo lungo per lo schermo, o lettere che il font 8-bit non ha (niente giapponese, cinese, arabo, ebraico né lingue indiane).

## Prova su PC (senza Spotify)

```bash
pip install pygame
python3 spotify_deck.py --demo
```
Frecce = D-pad, Z=A, X=B, A=X, S=Y, Q=L1, W=R1, Invio=Start, Backspace=Select.

## Problemi

- **Non parte:** guarda `spotify_deck/log.txt` nella cartella dell'app.
- **Schermo nero senza errori:** EmulationStation tiene il DRM. Lancia da SSH:
  ```bash
  sudo systemctl stop emulationstation.service
  cd /roms2/tools/spotify_deck && SDL_VIDEODRIVER=kmsdrm python3 spotify_deck.py
  sudo systemctl start emulationstation.service
  ```
- **"NESSUN DISPOSITIVO ATTIVO":** apri Spotify sul PC/telefono e fai partire un brano una volta, poi Menu → Dispositivi.
- **Il volume non funziona su alcuni dispositivi** (es. iPhone): limite delle API di Spotify, non risolvibile lato app.
- **Il sistema Spotify non compare in EmulationStation:** hai riavviato EmulationStation/la console dopo il primissimo avvio? Controlla le righe `[install_es_entry]` in `spotify_deck/log.txt`: dicono esattamente cos'ha fatto, incluso il percorso di `es_systems.cfg` usato.
- Riconfigura i tasti quando vuoi da Menu → CONFIGURA TASTI.

## Disinstallare

1. Rimuovi il blocco `<system>...</system>` con `<name>spotify</name>` da `es_systems.cfg` (oppure ripristina il backup `.bak-spotifydeck` creato accanto).
2. Cancella la cartella `<roms>/spotify`.
3. Cancella `Spotify Deck.sh` e la cartella `spotify_deck/` da `tools/`.
4. Riavvia EmulationStation.
