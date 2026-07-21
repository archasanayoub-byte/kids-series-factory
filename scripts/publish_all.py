#!/usr/bin/env python3
"""
publish_all.py
---------------
Batch runner used by the GitHub Actions workflow.

Scans a "drop folder" (default: videos/to_upload/) for video files that each
have a matching JSON metadata sidecar (same filename, .json extension), and
uploads ONLY THE OLDEST ONE not yet uploaded, then stops. This is what lets
the GitHub Actions schedule act as a drip-feed release queue: every time the
workflow fires (e.g. 3x/day), exactly one episode goes out, oldest first.
Keeps a manifest (uploaded_manifest.json) so re-runs never double-publish.

Set PUBLISH_ALL=1 in the environment to instead upload every pending video
in one run (useful for manual catch-up).

Folder layout expected:
    videos/to_upload/ep01.mp4
    videos/to_upload/ep01.json      <- title/description/tags/etc (see youtube_upload.py)
    videos/to_upload/ep01_thumb.jpg <- optional, referenced from ep01.json as "thumbnail": "ep01_thumb.jpg"

CLOUD-ONLY PIPELINE (added 16 July 2026): the episode-generator scheduled
task cannot reach the Higgsfield CDN from its own sandbox, so it queues
{"filename", "url"} pairs in videos/to_upload/pending_downloads.json instead
of the raw video bytes. Before scanning DROP_DIR, fetch_pending_downloads()
downloads every queued URL directly into DROP_DIR -- this runs inside the
GitHub Actions runner, which has full, unrestricted internet access. This
means publishing no longer depends on the user's own PC being on or running
run_daily_publish.bat: generation (scheduled task) -> queue file (committed
via repo) -> download + publish (GitHub Actions, fully cloud-side).

Before upload, three ffmpeg passes are applied (each fails gracefully -- if
ffmpeg or the relevant asset is missing, the video is published as-is rather
than blocking the run):
  1. add_subscribe_overlay -- burns a "subscribe to the channel" banner
     (assets/subscribe_overlay.png) into the video from second 7 onward.
  2. add_theme_music -- mixes the channel's theme track
     (assets/theme_music.mp3) under the video's existing native audio at
     reduced volume (25%), looped/trimmed to match the episode's length, so
     every published episode carries the same audio signature.
  3. add_next_episode_card -- burns a full-screen "watch more episodes"
     outro card (Bobo & Festuk waving + Arabic CTA) into the final ~1.6
     seconds of the video. Added 22 July 2026 as the compliant substitute
     for a YouTube end screen: end screens are unavailable here for TWO
     independent reasons -- (a) this channel publishes exclusively to
     YouTube Shorts, and Shorts never support end screens/cards regardless
     of audience setting or video length, and (b) every video is correctly
     marked "made for kids" (required -- this channel is clearly directed
     at children), and Made for Kids content has end screens/cards disabled
     by YouTube policy even on regular long-form videos. Baking a card
     directly into the pixels sidesteps both restrictions since it's just
     video content, not a YouTube UI feature -- it isn't clickable, but it's
     the closest thing to "suggest another episode at the end" that YouTube
     allows for this channel. See ensure_next_episode_overlay() for how the
     card image itself gets onto disk.

After a successful upload:
    - the video + thumbnail are deleted (keeps the git repo light -- video
      binaries don't belong in git long-term)
    - the metadata JSON is moved to videos/uploaded/ for a paper trail
    - the video's id/url/timestamp is recorded in uploaded_manifest.json

The GitHub Actions workflow commits the manifest + videos/uploaded/ +
videos/to_upload/ changes back to the repo after this script runs (this
already covers the drained pending_downloads.json queue and any newly
downloaded video files, no workflow changes needed).
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Reuse the single-video upload logic instead of shelling out.
sys.path.insert(0, str(Path(__file__).parent))
from youtube_upload import load_credentials, upload_video, set_thumbnail, add_to_playlist  # noqa: E402

DROP_DIR = Path("videos/to_upload")
UPLOADED_DIR = Path("videos/uploaded")
MANIFEST_PATH = Path("uploaded_manifest.json")
OVERLAY_PATH = Path("assets/subscribe_overlay.png")
MUSIC_PATH = Path("assets/theme_music.mp3")
PENDING_DOWNLOADS_PATH = DROP_DIR / "pending_downloads.json"

NEXT_EP_OVERLAY_PATH = Path("assets/next_episode_overlay.png")
# One-time source for the outro-card image above (Bobo & Festuk waving, with
# an Arabic "تابعونا لمزيد من الحلقات" call-to-action banner), generated via
# Higgsfield nano_banana on 22 July 2026. ensure_next_episode_overlay() below
# downloads it into assets/ the first time this script runs after it was
# generated, then every future run reuses the local copy -- same pattern as
# fetch_pending_downloads() above, needed because this repo's own automation
# can't reach the Higgsfield CDN directly, only the GitHub Actions runner can.
NEXT_EP_OVERLAY_URL = (
    "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/"
    "hf_20260721_211714_df307357-7d2b-4189-9ee4-bc2e0777a1d5.png"
)


class Args:
    """Small shim so we can reuse upload_video()/set_thumbnail() which expect an argparse.Namespace."""

    def __init__(self, file, meta, title_fallback=None):
        self.file = str(file)
        self.title = meta.get("title") or title_fallback or file.stem
        self.description = meta.get("description", "")
        self.tags = ",".join(meta.get("tags", []))
        self.category_id = meta.get("category_id", "1")
        self.privacy = meta.get("privacy_status", "unlisted")
        self.made_for_kids = bool(meta.get("made_for_kids", False))
        self.thumbnail = meta.get("thumbnail")


def fetch_pending_downloads():
    """Download any videos/thumbnails queued in pending_downloads.json.

    The episode-generator scheduled task writes {"filename", "url"} pairs
    here (pointing at Higgsfield CDN URLs) because its own sandbox can't
    reach that CDN. This runner (GitHub Actions) CAN reach it, so this is
    where the actual bytes get pulled down -- no local PC involved.

    Successfully downloaded entries are removed from the queue file.
    Entries that fail are left in place so the next scheduled run retries
    them automatically.
    """
    if not PENDING_DOWNLOADS_PATH.exists():
        return

    try:
        pending = json.loads(PENDING_DOWNLOADS_PATH.read_text())
    except json.JSONDecodeError:
        print(f"WARNING: {PENDING_DOWNLOADS_PATH} is not valid JSON, leaving it untouched.")
        return

    if not pending:
        return

    DROP_DIR.mkdir(parents=True, exist_ok=True)
    remaining = []

    for item in pending:
        filename = item.get("filename")
        url = item.get("url")
        if not filename or not url:
            print(f"WARNING: skipping malformed pending_downloads entry: {item}")
            continue

        dest = DROP_DIR / filename
        if dest.exists():
            print(f"{filename} already present in {DROP_DIR}, skipping download.")
            continue

        print(f"Downloading queued file {filename} ...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            print(f"Downloaded {filename} ({dest.stat().st_size} bytes).")
        except Exception as e:
            print(f"FAILED to download {filename}: {e}")
            remaining.append(item)

    PENDING_DOWNLOADS_PATH.write_text(json.dumps(remaining, indent=2))
    if remaining:
        print(f"{len(remaining)} queued download(s) still pending (will retry next run).")


def ensure_next_episode_overlay():
    """Download the reusable outro-card image (see NEXT_EP_OVERLAY_URL) into
    assets/ the first time it's needed, then leave it alone on every later
    run. Never blocks publishing -- if the download fails, add_next_episode_card()
    just skips the card that run and this function retries on the next one."""
    if NEXT_EP_OVERLAY_PATH.exists():
        return
    try:
        NEXT_EP_OVERLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(NEXT_EP_OVERLAY_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(NEXT_EP_OVERLAY_PATH, "wb") as f:
            shutil.copyfileobj(resp, f)
        print(f"Downloaded next-episode outro card to {NEXT_EP_OVERLAY_PATH}.")
    except Exception as e:
        print(f"Could not download next-episode overlay ({e}), will retry next run.")


def _probe_duration_seconds(video_path: Path):
    """Return the video's duration in seconds via ffprobe, or None if it
    can't be determined (missing ffprobe, unreadable file, etc.)."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def add_next_episode_card(video_path: Path) -> Path:
    """Burn the outro card (see NEXT_EP_OVERLAY_PATH) full-screen into the
    final ~1.6 seconds of the video -- the compliant substitute for a
    YouTube end screen (see the module docstring for why an actual end
    screen isn't possible on this channel). Returns the path to the
    overlaid copy, or the original path unchanged if the asset / ffmpeg /
    ffprobe aren't available, or the clip is too short to safely fit the
    card (never blocks publishing)."""
    if not NEXT_EP_OVERLAY_PATH.exists():
        print(f"No next-episode overlay at {NEXT_EP_OVERLAY_PATH}, publishing without it.")
        return video_path
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH, publishing without next-episode card.")
        return video_path

    duration = _probe_duration_seconds(video_path)
    if duration is None or duration <= 3:
        print("Could not read video duration (or clip too short), skipping next-episode card.")
        return video_path

    card_start = max(duration - 1.6, 0)
    out_path = video_path.with_name(video_path.stem + "_next" + video_path.suffix)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(NEXT_EP_OVERLAY_PATH),
        "-filter_complex",
        f"[1:v]scale=720:1280[card];[0:v][card] overlay=0:0:enable='gte(t,{card_start})'",
        "-c:a", "copy",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr_tail = e.stderr[-500:] if e.stderr else e
        print(f"ffmpeg next-episode card failed ({stderr_tail}), publishing without it.")
        return video_path
    return out_path


def add_subscribe_overlay(video_path: Path) -> Path:
    """Burn the subscribe-nudge banner into the video, appearing from second 7
    onward. Returns the path to the overlaid copy, or the original path
    unchanged if ffmpeg / the overlay asset aren't available (never blocks
    publishing)."""
    if not OVERLAY_PATH.exists():
        print(f"No overlay asset at {OVERLAY_PATH}, publishing without it.")
        return video_path
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH, publishing without overlay.")
        return video_path

    out_path = video_path.with_name(video_path.stem + "_ov" + video_path.suffix)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(OVERLAY_PATH),
        "-filter_complex", "[0:v][1:v] overlay=0:0:enable='gte(t,7)'",
        "-c:a", "copy",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr_tail = e.stderr[-500:] if e.stderr else e
        print(f"ffmpeg overlay failed ({stderr_tail}), publishing without overlay.")
        return video_path
    return out_path


def add_theme_music(video_path: Path) -> Path:
    """Mix the channel's theme music (assets/theme_music.mp3) under the
    video's existing native audio at reduced volume, looped and trimmed to
    match the video's length. Returns the path to the mixed copy, or the
    original path unchanged if ffmpeg / the music asset aren't available
    (never blocks publishing)."""
    if not MUSIC_PATH.exists():
        print(f"No theme music at {MUSIC_PATH}, publishing without it.")
        return video_path
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH, publishing without theme music.")
        return video_path

    out_path = video_path.with_name(video_path.stem + "_mus" + video_path.suffix)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(MUSIC_PATH),
        "-filter_complex",
        "[1:a]volume=0.25[music];"
        "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy",
        "-shortest",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr_tail = e.stderr[-500:] if e.stderr else e
        print(f"ffmpeg theme-music mix failed ({stderr_tail}), publishing without it.")
        return video_path
    return out_path


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(manifest: dict):
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def main():
    fetch_pending_downloads()
    ensure_next_episode_overlay()

    if not DROP_DIR.exists():
        print(f"No drop folder at {DROP_DIR}, nothing to do.")
        return

    UPLOADED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    video_files = sorted(
        p for p in DROP_DIR.iterdir() if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm")
    )

    if not video_files:
        print(f"No video files found in {DROP_DIR}.")
        return

    # Drip-feed mode (default): only the single oldest not-yet-uploaded video
    # is processed per run, so the schedule cadence in the workflow controls
    # the release pace. Set PUBLISH_ALL=1 to process everything in one go.
    if os.environ.get("PUBLISH_ALL") != "1":
        pending = [p for p in video_files if p.name not in manifest]
        video_files = pending[:1]
        if not video_files:
            print("No pending videos to publish (everything already uploaded).")
            return

    creds = load_credentials(None)  # reads YOUTUBE_TOKEN_JSON from env in CI
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)

    uploaded_count = 0
    failed = []

    for video_path in video_files:
        key = video_path.name
        if key in manifest:
            print(f"Skipping {key} (already uploaded: {manifest[key]['url']})")
            continue

        meta_path = video_path.with_suffix(".json")
        if not meta_path.exists():
            print(f"WARNING: no metadata file for {video_path.name} (expected {meta_path.name}), skipping.")
            failed.append(key)
            continue

        meta = json.loads(meta_path.read_text())

        # Apply overlay, then theme music, then the next-episode outro card,
        # in three ffmpeg passes; each is a no-op fallback to its input path
        # if the asset/ffmpeg isn't available.
        overlay_path = add_subscribe_overlay(video_path)
        music_path = add_theme_music(overlay_path)
        upload_path = add_next_episode_card(music_path)
        temp_paths = [p for p in (overlay_path, music_path, upload_path) if p != video_path]

        args = Args(upload_path, meta, title_fallback=video_path.stem)

        # Resolve thumbnail path relative to the drop folder.
        thumb_path = None
        if args.thumbnail:
            candidate = video_path.parent / args.thumbnail
            thumb_path = str(candidate) if candidate.exists() else None

        print(f"\n=== Uploading {video_path.name} ===")
        try:
            video_id = upload_video(youtube, args)
            if thumb_path:
                set_thumbnail(youtube, video_id, thumb_path)
            if meta.get("playlist_id"):
                add_to_playlist(youtube, video_id, meta["playlist_id"])
        except SystemExit:
            print(f"FAILED to upload {video_path.name}")
            failed.append(key)
            for p in temp_paths:
                p.unlink(missing_ok=True)
            continue

        manifest[key] = {
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "title": args.title,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "characters": meta.get("characters", []),
        }
        save_manifest(manifest)  # save incrementally so a crash mid-batch doesn't lose progress
        uploaded_count += 1

        # Clean up: remove the video + thumbnail + temp overlay/music copies, archive the metadata.
        video_path.unlink()
        for p in temp_paths:
            p.unlink(missing_ok=True)
        if thumb_path:
            Path(thumb_path).unlink(missing_ok=True)
        meta_path.rename(UPLOADED_DIR / meta_path.name)

    print(f"\nDone. Uploaded {uploaded_count} video(s).")
    if failed:
        print(f"Failed/skipped (missing metadata or error): {failed}")
        sys.exit(2)


if __name__ == "__main__":
    main()
