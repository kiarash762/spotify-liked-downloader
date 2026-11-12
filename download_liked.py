#!/usr/bin/env python3
"""
Spotify Liked Songs Downloader
Fetches liked tracks from your local Spotify client and downloads them in high quality MP3
with metadata and album cover using yt-dlp.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

def get_default_spotify_cli() -> str:
    """Locate spotify_cli executable dynamically from environment or known defaults."""
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        default_cli = Path(appdata) / "Microsoft" / "WindowsApps" / "spotify_cli.exe"
        if default_cli.exists():
            return str(default_cli)
    return "spotify_cli"


def get_default_output_dir() -> str:
    """Return default music directory across systems."""
    user_music = Path.home() / "Music" / "Spotify_Liked"
    return str(user_music)


SPOTIFY_CLI_PATH = get_default_spotify_cli()
DEFAULT_OUTPUT_DIR = get_default_output_dir()
DEFAULT_PROXY = None
DEFAULT_BROWSER = "firefox"


def sanitize_filename(name: str) -> str:
    """Remove invalid Windows filename characters."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
    sanitized = sanitized.strip().strip('.')
    return sanitized if sanitized else "unknown"


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Execute a CLI command and return exit_code, stdout, stderr."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def ensure_spotify_running() -> bool:
    """Ensure Spotify desktop client is running."""
    code, out, _ = run_cmd([SPOTIFY_CLI_PATH, "status"])
    if code == 0 and "running" in out:
        return True

    print("[*] Spotify is not running. Launching Spotify desktop client...")
    run_cmd([SPOTIFY_CLI_PATH, "open"])

    for _ in range(10):
        time.sleep(1)
        code, out, _ = run_cmd([SPOTIFY_CLI_PATH, "status"])
        if code == 0 and "running" in out:
            print("[✓] Spotify is running and ready.")
            return True

    print("[!] Failed to verify Spotify client status.")
    return False


def get_current_username() -> str | None:
    """Retrieve username from Spotify CLI."""
    code, out, err = run_cmd([SPOTIFY_CLI_PATH, "me"])
    if code != 0:
        print(f"[!] Error getting user info: {err}")
        return None
    try:
        data = json.loads(out)
        return data.get("username")
    except json.JSONDecodeError:
        print("[!] Could not parse user info JSON.")
        return None


def get_liked_songs(username: str) -> list[dict]:
    """Retrieve liked songs via collection playlist URI."""
    collection_uri = f"spotify:user:{username}:collection"
    print(f"[*] Fetching liked songs from Spotify ({collection_uri})...")
    code, out, err = run_cmd([SPOTIFY_CLI_PATH, "playlist", "get", collection_uri, "--format", "json"])
    if code != 0:
        print(f"[!] Error fetching collection: {err}")
        return []

    try:
        data = json.loads(out)
        tracks = data.get("tracks", [])
        print(f"[✓] Found {len(tracks)} liked song(s).")
        return tracks
    except json.JSONDecodeError:
        print("[!] Failed to decode playlist JSON response.")
        return []


def get_playlist_bookmarks(liked_uris: set[str]) -> dict[str, dict]:
    """
    Find bookmark tracks in user playlists.
    For each playlist, the last liked track (highest position in the playlist)
    serves as a bookmark and should NOT be unliked.
    Returns: dict mapping track_uri -> {'playlist_name', 'track_name', 'position'}
    """
    code, out, _ = run_cmd([SPOTIFY_CLI_PATH, "library", "list", "--type", "playlist", "--limit", "100", "--format", "json"])
    if code != 0:
        return {}

    try:
        playlists = json.loads(out).get("items", [])
    except Exception:
        return {}

    bookmarks = {}
    print(f"[*] Scanning {len(playlists)} playlist(s) to protect bookmarks...")
    for pl in playlists:
        p_uri = pl.get("uri")
        p_name = pl.get("name", "Unknown Playlist")
        p_code, p_out, _ = run_cmd([SPOTIFY_CLI_PATH, "playlist", "get", p_uri, "--format", "json"])
        if p_code != 0:
            continue
        try:
            p_tracks = json.loads(p_out).get("tracks", [])
        except Exception:
            continue

        liked_in_p = [t for t in p_tracks if t.get("uri") in liked_uris]
        if liked_in_p:
            liked_in_p.sort(key=lambda x: x.get("position", 0))
            last_t = liked_in_p[-1]
            t_uri = last_t.get("uri")
            bookmarks[t_uri] = {
                "playlist_name": p_name,
                "track_name": last_t.get("name"),
                "position": last_t.get("position"),
            }

    return bookmarks


def remove_from_library(track_uri: str) -> bool:
    """Unlike / remove track from Spotify Liked Songs."""
    code, out, err = run_cmd([SPOTIFY_CLI_PATH, "library", "remove", track_uri])
    return code == 0


def load_history(history_file: Path) -> set[str]:
    """Load previously downloaded Spotify track URIs."""
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("downloaded_uris", []))
        except Exception:
            pass
    return set()


def save_history(history_file: Path, downloaded_uris: set[str]):
    """Save downloaded Spotify track URIs to history file."""
    try:
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump({"downloaded_uris": list(downloaded_uris)}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Warning: Could not save history file: {e}")


def download_track(
    track: dict,
    output_dir: Path,
    proxy: str | None = None,
    cookies_browser: str | None = DEFAULT_BROWSER
) -> bool:
    """Download single track audio from YouTube Music/YouTube via yt-dlp."""
    title = track.get("name", "Unknown Title")
    artists = ", ".join(track.get("artists", ["Unknown Artist"]))
    album = track.get("album", "")
    track_uri = track.get("uri", "")

    clean_artist = sanitize_filename(artists)
    clean_title = sanitize_filename(title)
    filename_base = f"{clean_artist} - {clean_title}"
    output_mp3 = output_dir / f"{filename_base}.mp3"

    if output_mp3.exists() and output_mp3.stat().st_size > 100000:
        print(f"[⚡] Already downloaded: {filename_base}.mp3")
        return True

    # Clean artist names for searching (remove punctuation/commas that confuse search)
    search_artists = re.sub(r'[,|/]', ' ', artists).strip()
    search_query = f"{search_artists} {title} audio"
    output_template = str(output_dir / f"{filename_base}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--default-search", "ytsearch1",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--add-metadata",
        "--embed-thumbnail",
        "-o", output_template,
        "--no-playlist",
    ]

    if proxy:
        cmd.extend(["--proxy", proxy])
    if cookies_browser:
        cmd.extend(["--cookies-from-browser", cookies_browser])

    cmd.append(search_query)

    print(f"[*] Downloading: {artists} - {title}...")
    code, stdout, stderr = run_cmd(cmd)

    if code == 0 and output_mp3.exists():
        print(f"[✓] Success: {output_mp3.name}")
        return True
    else:
        print(f"[✗] Failed: {artists} - {title}")
        if stderr:
            # Print brief error
            err_line = stderr.splitlines()[-1] if stderr.splitlines() else "Unknown error"
            print(f"    Reason: {err_line}")
        return False


def handle_cleanup_liked(tracks: list[dict], out_path: Path, bookmarks: dict[str, dict]):
    """Unlike tracks that are already successfully downloaded, protecting bookmarks."""
    history_file = out_path / ".download_history.json"
    downloaded_uris = load_history(history_file)

    print("\n" + "=" * 60)
    print("Running Liked Songs Cleanup for already downloaded tracks...")
    print("=" * 60)

    unliked_count = 0
    protected_count = 0
    not_downloaded_count = 0

    for idx, track in enumerate(tracks, 1):
        uri = track.get("uri", "")
        title = track.get("name", "Unknown")
        artists = ", ".join(track.get("artists", ["Unknown"]))
        clean_name = f"{sanitize_filename(artists)} - {sanitize_filename(title)}.mp3"
        file_exists = (out_path / clean_name).exists() or uri in downloaded_uris

        if not file_exists:
            not_downloaded_count += 1
            continue

        if uri in bookmarks:
            bm = bookmarks[uri]
            print(f"[📌 PROTECTED BOOKMARK] '{title}' in playlist '{bm['playlist_name']}' (pos {bm['position']}) -> Kept in Liked!")
            protected_count += 1
            continue

        ok = remove_from_library(uri)
        if ok:
            print(f"[🗑 UNLIKED] {artists} - {title}")
            unliked_count += 1
        else:
            print(f"[!] Failed to unlike: {artists} - {title}")

    print("\n" + "=" * 60)
    print("Cleanup Summary:")
    print(f"  Unliked from Spotify : {unliked_count}")
    print(f"  Protected bookmarks  : {protected_count}")
    print(f"  Not yet downloaded   : {not_downloaded_count}")
    print("=" * 60)


def main():
    global SPOTIFY_CLI_PATH
    parser = argparse.ArgumentParser(description="Spotify Liked Songs Downloader")
    parser.add_argument("--cli-path", default=SPOTIFY_CLI_PATH, help="Path to spotify_cli executable (default: auto-detected)")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_DIR, help="Destination directory (default: ~/Music/Spotify_Liked)")
    parser.add_argument("-n", "--limit", type=int, default=None, help="Download only the latest N songs")
    parser.add_argument("-p", "--proxy", default=os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY") or DEFAULT_PROXY, help=f"HTTP/SOCKS proxy (default: {DEFAULT_PROXY})")
    parser.add_argument("-b", "--browser", default=DEFAULT_BROWSER, help=f"Browser to extract cookies from (default: {DEFAULT_BROWSER})")
    parser.add_argument("--dry-run", action="store_true", help="Only list songs without downloading")
    parser.add_argument("--reverse", action="store_true", help="Download oldest songs first")
    parser.add_argument("--keep-liked", action="store_true", help="Keep songs in Liked Songs (do not unlike after download)")
    parser.add_argument("--unlike", action="store_true", default=True, help="Unlike/remove song from Liked Songs after downloading (default: True, protecting bookmarks)")
    parser.add_argument("--cleanup-liked", action="store_true", help="Unlike all already-downloaded songs right now (protecting bookmarks)")

    args = parser.parse_args()
    if args.keep_liked:
        args.unlike = False

    SPOTIFY_CLI_PATH = args.cli_path

    out_path = Path(args.output).resolve()
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[!] Error creating directory {out_path}: {e}")
        sys.exit(1)

    if not ensure_spotify_running():
        sys.exit(1)

    username = get_current_username()
    if not username:
        sys.exit(1)

    tracks = get_liked_songs(username)
    if not tracks:
        print("[!] No liked tracks found or failed to load.")
        sys.exit(1)

    bookmarks = {}
    if args.unlike or args.cleanup_liked or args.dry_run:
        liked_uris_set = {t.get("uri") for t in tracks if t.get("uri")}
        bookmarks = get_playlist_bookmarks(liked_uris_set)
        print(f"[✓] Identified {len(bookmarks)} bookmark track(s) across your playlists:")
        for b_uri, b_info in bookmarks.items():
            print(f"    • '{b_info['track_name']}' in '{b_info['playlist_name']}' (pos: {b_info['position']})")
        print("-" * 60)

    if args.cleanup_liked:
        handle_cleanup_liked(tracks, out_path, bookmarks)
        return

    if args.reverse:
        tracks.reverse()

    if args.limit:
        tracks = tracks[:args.limit]

    print(f"[*] Total tracks to process: {len(tracks)}")
    print(f"[*] Output directory: {out_path}")
    print("-" * 60)

    if args.dry_run:
        for idx, t in enumerate(tracks, 1):
            artists = ", ".join(t.get("artists", []))
            uri = t.get("uri", "")
            bm_tag = f" [📌 BOOKMARK: {bookmarks[uri]['playlist_name']}]" if uri in bookmarks else ""
            print(f"{idx:3d}. {artists} - {t.get('name')} [{t.get('album')}]{bm_tag}")
        print("[*] Dry run completed.")
        return

    history_file = out_path / ".download_history.json"
    downloaded_uris = load_history(history_file)

    success_count = 0
    skipped_count = 0
    failed_count = 0
    unliked_count = 0

    for idx, track in enumerate(tracks, 1):
        uri = track.get("uri", "")
        title = track.get("name", "Unknown")
        artists = ", ".join(track.get("artists", ["Unknown"]))

        print(f"\n[{idx}/{len(tracks)}] {artists} - {title}")

        clean_name = f"{sanitize_filename(artists)} - {sanitize_filename(title)}.mp3"
        already_have = (out_path / clean_name).exists() or uri in downloaded_uris

        if already_have:
            print(f"[⚡] Skipped (already downloaded): {clean_name}")
            skipped_count += 1
            ok = True
        else:
            ok = download_track(
                track=track,
                output_dir=out_path,
                proxy=args.proxy if args.proxy else None,
                cookies_browser=args.browser if args.browser else None,
            )

        if ok:
            if not already_have:
                success_count += 1
                if uri:
                    downloaded_uris.add(uri)
                    save_history(history_file, downloaded_uris)

            if args.unlike and uri:
                if uri in bookmarks:
                    bm = bookmarks[uri]
                    print(f"[📌 PROTECTED] Kept in Liked (Bookmark for '{bm['playlist_name']}' pos {bm['position']})")
                else:
                    if remove_from_library(uri):
                        print(f"[🗑 UNLIKED] Removed from Spotify Liked Songs.")
                        unliked_count += 1
                    else:
                        print(f"[!] Failed to remove from Spotify library.")
        else:
            failed_count += 1

    print("\n" + "=" * 60)
    print("Download Summary:")
    print(f"  Total processed : {len(tracks)}")
    print(f"  Downloaded      : {success_count}")
    print(f"  Skipped (exist) : {skipped_count}")
    print(f"  Failed          : {failed_count}")
    if args.unlike:
        print(f"  Unliked songs   : {unliked_count}")
        print(f"  Protected bms   : {len(bookmarks)}")
    print(f"  Output folder   : {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
