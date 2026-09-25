SPOTIFY DECK  -  telecomando Spotify 8-bit per R36S
====================================================
La console comanda Spotify (play, pausa, brano, volume, seek, shuffle, repeat,
scelta dispositivo, playlist). L'audio esce dal dispositivo che scegli (PC,
telefono, speaker...). Serve Spotify PREMIUM (limite delle API Spotify).

1) CREA L'APP SPOTIFY (gratis, 2 minuti)
   - developer.spotify.com/dashboard  ->  Create app
   - Redirect URI (identico!):  http://127.0.0.1:8888/callback
   - Spunta "Web API", salva, copia il Client ID.

2) LOGIN (su PC o Mac con python3)
   python3 get_token.py IL_TUO_CLIENT_ID
   Si apre il browser: accedi e premi Accetta. Si crea config.json.
   (Alternativa: python3 get_token.py --manual  e incolli l'URL finale.)
   ATTENZIONE: da luglio 2026 Spotify fa scadere il login dopo 6 MESI.
   L'app ti avvisa 2 settimane prima (e in Menu > SPOTIFY vedi i giorni
   rimasti). Quando serve rilancia get_token.py e ricopia config.json.
   Va rifatto anche quando l'app chiede nuovi permessi (es. la sezione
   SPOTIFY con la libreria, o "AGGIUNGI AI PREFERITI" nel menu).

3) COPIA SULLA R36S  (stesso schema di Sticker Printer)
   - Metti  "Spotify Deck.sh"  E  la cartella  spotify_deck/  (con dentro
     config.json) insieme, nella cartella Tools:  /roms2/tools/  (o /roms/tools/).
   - In EmulationStation vai su Tools > "Spotify Deck".
   - Non serve venv ne' pip: usa solo il pygame di sistema (python3-pygame),
     che hai gia' installato per Sticker Printer. Driver video: kmsdrm.
   - Serve il WiFi attivo sulla console.
   - Il pad "GO-Super Gamepad" e' gia' mappato (D-pad, A, B, Start, Select
     verificati). X, Y, L1, R1 sono i valori standard di questo pad ma non
     ancora provati: se uno non risponde, Menu > CONFIGURA TASTI.

COMANDI
   A            play / pausa
   L1 / R1      brano precedente / successivo
   SU / GIU     volume +/- (tieni premuto per scorrere)
   SX / DX      indietro / avanti di 10 secondi
   X            shuffle        Y  repeat (off > tutto > brano)
   B            cambia VISTA:  player > copertina a tutto schermo > testo
   SELECT       cambia tema al volo
   START        menu (aggiungi ai preferiti, dispositivi, playlist, tema, ecc.)
   START+SELECT esci
   (tutti i comandi funzionano in tutte le viste)

VISTE
   PLAYER    copertina + titolo + volume + barra
   COPERTINA copertina 240x240 filtrata 8-bit, volume a sinistra, stato a
             destra, barra sottile in fondo. Titolo/artista compaiono per
             qualche secondo al cambio brano o quando premi A, L1, R1.
   TESTO     testo del brano, riga corrente evidenziata e scorrimento
             automatico. Se il testo non e' sincronizzato scorre in modo
             approssimato in base ai minuti del brano.
             Spotify non da' i testi nelle sue API: vengono da LRCLIB
             (lrclib.net, archivio libero). Non c'e' per tutti i brani.
             Se le righe arrivano troppo presto/tardi: Menu > SYNC TESTO.
   L'ultima vista usata viene ricordata al prossimo avvio.

MENU > SPOTIFY  (libreria: START, poi SPOTIFY)
   CERCA               tastiera a schermo: D-pad muove, A scrive, B cancella,
                       X spazio, Y svuota, START cerca. Risultati divisi in
                       brani / artisti / album / playlist (max 10 ciascuno:
                       e' il limite imposto da Spotify).
   BRANI PREFERITI     i tuoi "Mi piace"
   PLAYLIST            le tue e quelle che segui
   ARTISTI SEGUITI     > artista > album e singoli > brani
   ALBUM SALVATI       > brani
   ASCOLTATI DI RECENTE, TOP BRANI, TOP ARTISTI (ultimi ~6 mesi)
   Nelle liste:  SU/GIU scorri,  SX/DX salta di 8,  A apri/riproduci,
                 X aggiungi in coda,  B indietro,  START torna al player.
   Le liste lunghe caricano 50 alla volta ("CARICA ALTRI" in fondo; se Spotify
   rifiuta quel numero l'app ritenta da sola con pagine piu' piccole).
   Riprodurre un brano da una lista continua con i brani successivi.
   Limiti di Spotify (2026): dei brani di una playlist SI VEDE l'elenco solo
   per le TUE playlist; per quelle di altri c'e' solo "RIPRODUCI PLAYLIST".
   I "brani piu' famosi" di un artista non esistono piu' nelle API: dall'artista
   si vedono gli album e c'e' "RIPRODUCI ARTISTA".
   Se un permesso manca compare "PERMESSI MANCANTI": rifai get_token.py.

TEMI:  NES, GAME BOY, GB POCKET, PS1, C64

MENU > INFO
   Una schermata con un QR code che porta al profilo Instagram
   dell'autore (instagram.com/diavoleriee). E' generato interamente
   dall'app stessa (file qr.py, incluso, nessuna libreria esterna):
   non passa da nessun servizio di shortlink, quindi non scade mai e
   funziona anche se il progetto viene abbandonato o spostato altrove.
   Si inquadra con la fotocamera del telefono come un QR qualunque.
   I colori seguono il tema attivo (si fonde con lo sfondo, niente
   riquadro bianco) e si alzano automaticamente di contrasto solo se
   il tema da solo non basterebbe per una scansione affidabile.

LINGUE
   L'app parla: italiano, inglese, spagnolo, francese, tedesco, portoghese,
   russo. Al primissimo avvio la console chiede quale usare; si cambia
   quando vuoi da Menu > LINGUA (o dalla riga LINGUA nel wizard dei tasti,
   coi tasti SX/DX). La lingua e' salvata in config.json (campo "lang"):
   se non e' salvata, la console prova a indovinarla da sola dal sistema,
   sennò usa l'inglese.
   Anche get_token.py (quello che lanci sul PC) e' nella tua lingua in
   automatico; per forzarne una diversa (es. se il PC e' in un'altra
   lingua ma vuoi la console in italiano):
       python3 get_token.py --lang it IL_TUO_CLIENT_ID
   Codici disponibili: en it es fr de pt ru.
   La tastiera di ricerca (Menu > SPOTIFY > CERCA) ha piu' "pagine" di
   tasti: quella base (A-Z, come sulla console), una con gli accenti
   della lingua scelta, e una con l'alfabeto cirillico (utile per cercare
   brani/artisti in russo o simili). Si cambia pagina con L1/R1 mentre
   scrivi.
   AGGIUNGERE UNA LINGUA: e' pensato per essere semplice anche senza
   programmare. Nella cartella spotify_deck c'e' lang/en.json: copialo
   come lang/xx.json (xx = codice della lingua, es. "nl" per l'olandese),
   traduci i valori (lascia %d/%s e il carattere "|" dove ci sono), e la
   lingua compare da sola nel menu. Per controllare che sia a posto:
       python3 check_lang.py xx
   (dice se manca qualcosa, se un testo e' troppo lungo per lo schermo, o
   se usa lettere che il font 8-bit non ha — es. il font non ha il
   giapponese, il cinese, l'arabo, l'ebraico ne' le lingue indiane).
Menu > COPERTINA 8-BIT / DITHERING / SCANLINES CRT per regolare il look.

PROVA SU PC (senza Spotify):
   pip install pygame
   python3 spotify_deck.py --demo
   (frecce = D-pad, Z=A, X=B, A=X, S=Y, Q=L1, W=R1, Invio=Start, Backspace=Select)

VOCE NEL MENU PRINCIPALE (sistema a se', come PS1/NES/ecc.)
   Al primissimo avvio, "Spotify Deck.sh" lancia anche install_es_entry.py,
   che crea in EmulationStation un sistema "Spotify" tutto suo, allo stesso
   livello di PS1, NES eccetera (non dentro Tools, non dentro Movies), con
   una cartella dedicata (<roms>/spotify di default) che contiene un solo
   "gioco" (Spotify.sh, che rilancia questo stesso launcher) e le due
   immagini fornite come copertina e marquee. Dopo il primo avvio, riavvia
   EmulationStation (o la console) UNA VOLTA per vederlo comparire.
   Se vuoi un nome diverso da "spotify"/"Spotify", apri
   spotify_deck/install_es_entry.py e cambia SYSTEM_NAME / SYSTEM_FULLNAME
   in cima al file (se un sistema con quel nome esiste gia' in
   es_systems.cfg, non viene toccato: viene solo aggiunta/aggiornata la
   voce Spotify nel suo gamelist.xml).
   Il file es_systems.cfg viene cercato in questi percorsi, nell'ordine (il
   primo che esiste e' quello usato): <roms>/.emulationstation/es_systems.cfg,
   ~/.emulationstation/es_systems.cfg, /etc/emulationstation/es_systems.cfg.
   Prima di modificarlo ne salva una copia (es_systems.cfg.bak-spotifydeck).
   Per rifare l'installazione da capo (es. dopo aver cambiato nome sistema):
   cancella spotify_deck/.es_entry_installed e rilancia l'app.

PROBLEMI
   - Se non parte guarda log.txt nella cartella.
   - Schermo nero senza errori: EmulationStation tiene il DRM. Lancia da SSH:
       sudo systemctl stop emulationstation.service
       cd /roms2/tools/spotify_deck && SDL_VIDEODRIVER=kmsdrm python3 spotify_deck.py
       sudo systemctl start emulationstation.service
   - "NESSUN DISPOSITIVO ATTIVO": apri Spotify sul PC/telefono e fai partire
     un brano una volta, poi Menu > Dispositivi.
   - Il volume non funziona su alcuni dispositivi (es. iPhone): limite di Spotify.
   - Riconfigura i tasti da Menu > CONFIGURA TASTI.
