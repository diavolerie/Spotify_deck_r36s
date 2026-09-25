# Spotify Deck

An 8-bit Spotify remote for the R36S (and similar ArkOS / dArkOS handhelds). Control playback, volume, seek, shuffle, repeat, device and playlists from the console; the audio plays on whichever device you pick (PC, phone, speaker...). Requires **Spotify Premium** (a limitation of the Spotify API, not of this app).

🇮🇹 *Leggi questa guida in italiano: [README.it.md](README.it.md)*

![Spotify Deck running on an R36S](docs/screenshot.png)

## Features

- Play/pause, next/previous track, volume, seek ±10s, shuffle, repeat
- Search, liked songs, playlists (yours and followed), followed artists, saved albums, recently played, top tracks/artists
- Synced lyrics (via [LRCLIB](https://lrclib.net), a free/open archive — not every track has them)
- 5 themes: NES, Game Boy, Game Boy Pocket, PS1, C64 — with optional 8-bit dithering / CRT scanlines
- 7 languages: English, Italian, Spanish, French, German, Portuguese, Russian
- Appears in EmulationStation as its **own system**, alongside PS1, NES, etc. — not buried in a Tools submenu (see [First launch](#first-launch--auto-registration) below)

## Requirements

- An R36S or compatible ArkOS/dArkOS handheld
- Wi-Fi enabled on the console
- Python 3 with `python3-pygame` installed on the console (system package — no `venv`/`pip` needed on-device)
- A free Spotify Developer account and a **Spotify Premium** account for playback
- A PC or Mac with Python 3, used once to generate a login token

## Before you copy anything to the SD card

You need a Spotify API token *before* the app is useful on the console — generate it on a computer first, then copy the resulting file over.

### 1. Create a Spotify app (free, ~2 minutes)

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → **Create app**.
2. Redirect URI (must match exactly): `http://127.0.0.1:8888/callback`
3. Check **Web API**, save, and copy the **Client ID**.

### 2. Log in (on your PC/Mac, with Python 3 installed)

```bash
python3 get_token.py YOUR_CLIENT_ID
```

A browser window opens — log in and click **Accept**. This creates `config.json` in the same folder.

Alternative if the browser can't reach the console/PC automatically:

```bash
python3 get_token.py --manual
```
(paste the final redirect URL when prompted)

> **Note:** as of July 2026, Spotify expires this login after **6 months**. The app warns you two weeks ahead of time (and Menu → SPOTIFY shows the days remaining). When it expires, just rerun `get_token.py` and copy the new `config.json` over. You'll also need to redo it whenever the app requests a new permission scope (e.g. the SPOTIFY library section, or "ADD TO FAVOURITES" in the menu).

`get_token.py` follows your PC's language automatically; to force a specific one (e.g. your PC is in English but you want the console in Italian):

```bash
python3 get_token.py --lang it YOUR_CLIENT_ID
```
Available codes: `en it es fr de pt ru`.

## Installing on the console

Same layout as other pygame-based tools (e.g. Sticker Printer):

1. Copy **`Spotify Deck.sh`** and the **`spotify_deck/`** folder together, unmodified, into the console's `tools` folder: `/roms2/tools/` (or `/roms/tools/`).
2. Copy the `config.json` you generated in step 2 above into `spotify_deck/` (next to `spotify_deck.py`).
3. Don't rename the launcher or move it into a subfolder — the app derives some paths from where `Spotify Deck.sh` sits relative to the `tools` folder, so keep it directly inside `tools/`.

No `venv`, no `pip install` needed on the console: it only uses the system `python3-pygame`. Video driver: `kmsdrm`.

## First launch & auto-registration

The **first time** you run it (from EmulationStation → Tools → "Spotify Deck"), the launcher also runs `install_es_entry.py`, which:

- creates a dedicated EmulationStation system called **Spotify**, at the same level as PS1, NES, etc. (not inside Tools, not inside Movies);
- creates a matching folder (`<roms>/spotify` by default) containing a single "game" (`Spotify.sh`, which just relaunches the real app) plus cover art and a marquee image;
- registers that system in `es_systems.cfg` (a backup, `es_systems.cfg.bak-spotifydeck`, is written first);
- writes a marker file (`spotify_deck/.es_entry_installed`) so it only does this once.

**After the very first launch, restart EmulationStation (or reboot the console) once** so it picks up the new system.

If you already have a dedicated system with a different name, or want to rename it, edit `SYSTEM_NAME` / `SYSTEM_FULLNAME` at the top of `spotify_deck/install_es_entry.py` — if a system with that name already exists in `es_systems.cfg`, it's left untouched (only the game entry is added/updated). To redo the auto-registration from scratch, delete `spotify_deck/.es_entry_installed` and relaunch.

## Controls

| Button | Action |
|---|---|
| A | Play / pause |
| L1 / R1 | Previous / next track |
| Up / Down | Volume +/- (hold to repeat) |
| Left / Right | Seek back / forward 10s |
| X | Shuffle |
| Y | Repeat (off → all → track) |
| B | Switch view: player → full-screen cover → lyrics |
| Select | Cycle theme |
| Start | Menu (add to favourites, devices, playlists, theme, etc.) |
| Start + Select | Quit |

All buttons work in every view. The "GO-Super Gamepad" pad is pre-mapped (D-pad, A, B, Start, Select verified). X, Y, L1, R1 use that pad's standard values but aren't fully verified — if one doesn't respond, use Menu → CONFIGURE BUTTONS.

## Views

- **Player** — cover art + title + volume + progress bar
- **Cover** — full-screen 240×240 cover with an 8-bit filter, volume on the left, status on the right, a thin progress bar at the bottom. Title/artist appear briefly on track change or when you press A, L1, R1.
- **Lyrics** — synced lyrics, current line highlighted, auto-scroll. If a song's lyrics aren't time-synced, it scrolls approximately based on elapsed time. Lyrics come from LRCLIB (not every track has them). If lines feel early/late: Menu → SYNC LYRICS.

The last view you used is remembered on next launch.

## Menu → Spotify (your library)

- **Search** — on-screen keyboard (D-pad moves, A types, B deletes, X space, Y clear, Start search). Results split into tracks/artists/albums/playlists, max 10 each (Spotify's own limit).
- **Liked songs**, **Playlists** (yours + followed), **Followed artists** → albums & singles → tracks, **Saved albums** → tracks, **Recently played**, **Top tracks**, **Top artists** (last ~6 months).
- In lists: Up/Down scroll, Left/Right jump by 8, A open/play, X add to queue, B back, Start return to player.
- Long lists load 50 at a time ("LOAD MORE" at the bottom).
- Spotify limits (2026): you can only see a playlist's track list for **your own** playlists; for others' playlists you only get "PLAY PLAYLIST". An artist's "top tracks" no longer exists in the API — you get albums plus "PLAY ARTIST".
- If a scope is missing you'll see "MISSING PERMISSIONS" — rerun `get_token.py`.

## Themes

NES, Game Boy, Game Boy Pocket, PS1, C64. Menu → 8-BIT COVER / DITHERING / CRT SCANLINES to tweak the look.

## Menu → Info

A QR code linking to the author's Instagram, generated entirely by the app itself (`qr.py`, no external service, so it never expires). Colours follow the active theme and only boost contrast automatically if needed for a reliable scan.

## Languages

English, Italian, Spanish, French, German, Portuguese, Russian. On first boot the console asks which to use; change it anytime from Menu → LANGUAGE. Saved in `config.json` (`"lang"`); if unset, the console tries to guess from the system locale, otherwise falls back to English.

`get_token.py` (run on your PC) also follows your language automatically — see [Setup](#1-create-a-spotify-app-free-2-minutes) above for forcing a specific one.

The search keyboard has multiple "pages": a base one (A–Z), one with your chosen language's accented characters, and a Cyrillic one (for searching Russian tracks/artists). Switch pages with L1/R1 while typing.

### Adding a language

No coding needed:

1. Copy `spotify_deck/lang/en.json` to `spotify_deck/lang/xx.json` (`xx` = language code, e.g. `nl` for Dutch).
2. Translate the values (keep `%d`/`%s` and the `|` character where present).
3. The language appears automatically in the menu.
4. Validate it: `python3 check_lang.py xx` — reports missing keys, text too long for the screen, or characters the 8-bit font doesn't have (it has no Japanese, Chinese, Arabic, Hebrew, or Indic scripts).

## Try it on a PC (no Spotify needed)

```bash
pip install pygame
python3 spotify_deck.py --demo
```
Arrow keys = D-pad, Z=A, X=B, A=X, S=Y, Q=L1, W=R1, Enter=Start, Backspace=Select.

## Troubleshooting

- **Won't start:** check `spotify_deck/log.txt` in the app folder.
- **Black screen, no errors:** EmulationStation is holding the DRM device. Run from SSH:
  ```bash
  sudo systemctl stop emulationstation.service
  cd /roms2/tools/spotify_deck && SDL_VIDEODRIVER=kmsdrm python3 spotify_deck.py
  sudo systemctl start emulationstation.service
  ```
- **"NO ACTIVE DEVICE":** open Spotify on your PC/phone and start a track once, then Menu → Devices.
- **Volume control doesn't work on some devices** (e.g. iPhone): a Spotify API limitation, not fixable here.
- **New Spotify system doesn't appear in EmulationStation:** did you restart EmulationStation/reboot after the very first launch? Check `spotify_deck/log.txt` for the `[install_es_entry]` lines — they say exactly what happened, including the `es_systems.cfg` path it used.
- Reconfigure buttons anytime from Menu → CONFIGURE BUTTONS.

## Uninstalling

1. Remove the `<system>...</system>` block with `<name>spotify</name>` from `es_systems.cfg` (or restore the `.bak-spotifydeck` backup created next to it).
2. Delete the `<roms>/spotify` folder.
3. Delete `Spotify Deck.sh` and the `spotify_deck/` folder from `tools/`.
4. Restart EmulationStation.
