# Spotify Liked Songs Downloader

A lightweight Python automation tool that syncs and downloads your **Liked Songs** from Spotify in high-quality audio (MP3 with full ID3 metadata and high-resolution album cover art) using `yt-dlp` and the desktop Spotify client.

Features **Smart Playlist Bookmarking**: prevents removing the last played/liked track of each playlist when auto-unliking tracks.

---

## Features

- **No Official Spotify API Keys Required:** Uses your locally authenticated desktop Spotify client session.
- **Smart Playlist Bookmarking:** If you use liked songs as bookmarks for your playlists, the downloader detects the lowest/latest liked track in each playlist and protects it from being unliked.
- **Auto-Unliking:** Automatically unlikes downloaded tracks once they are safely saved on disk (can be toggled).
- **High Quality Audio & Metadata:** Fetches the best audio source, converts to MP3, and embeds artist, title, album, year, lyrics, and front album cover.
- **Deduplication / History:** Tracks downloaded URIs and checks existing files on disk so tracks are never re-downloaded unnecessarily.
- **Proxy & Anti-Bot Support:** Supports custom HTTP/SOCKS proxies and browser cookie extraction (`firefox`, `chrome`, `edge`) to seamlessly bypass challenges.

---

## Requirements

1. **Python 3.10+**
2. **Spotify Desktop Client** (installed and logged in)
3. **yt-dlp & FFmpeg** installed on your system:
   ```bash
   pip install yt-dlp
   # Ensure ffmpeg is in your system PATH
   ```
4. **spotify_cli** (or local Spotify CLI executable placed in `%LOCALAPPDATA%\Microsoft\WindowsApps\spotify_cli.exe` or specified via `--cli-path`).

---

## Usage

### 1. Basic Run (Download + Smart Unlike)
Simply run the script or double-click `run_downloader.bat` (on Windows):
```bash
python download_liked.py
```

### 2. Dry Run (Preview Tracks & Bookmarks)
Inspect which tracks will be processed and see which ones are protected as bookmarks without downloading:
```bash
python download_liked.py --dry-run
```

### 3. Keep Tracks in Liked Songs
If you prefer to download without unliking tracks:
```bash
python download_liked.py --keep-liked
```

### 4. Custom Output Directory & Limit
```bash
python download_liked.py -o "D:/Music" -n 20
```

### 5. Proxy & Browser Cookies
```bash
python download_liked.py --proxy "http://127.0.0.1:8080" --browser firefox
```

---

## License

MIT License. Feel free to use, modify, and distribute.
