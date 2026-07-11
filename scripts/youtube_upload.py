#!/usr/bin/env python3
"""
youtube_upload.py
------------------
Uploads a single video to YouTube using a pre-authorized token (no browser,
safe to run in GitHub Actions / CI).

Auth source (checked in this order):
  1. --token-file <path>            (explicit file path)
  2. $YOUTUBE_TOKEN_JSON             (raw JSON string, e.g. from a GitHub secret)
  3. ./token.json                   (local default, for testing on your machine)

Usage examples:

  # Local test
  python scripts/youtube_upload.py \\
      --file videos/ready/ep01.mp4 \\
      --title "Episode 1 - The Great Adventure" \\
      --description "First episode of the series. Subscribe for more!" \\
      --tags "kids,cartoon,series" \\
      --category-id 1 \\
      --privacy unlisted \\
      --thumbnail videos/ready/ep01_thumb.jpg

  # From a metadata JSON file instead of flags
  python scripts/youtube_upload.py --file videos/ready/ep01.mp4 --meta videos/ready/ep01.json

Metadata JSON schema (all fields optional except handled defaults):
  {
    "title": "Episode 1 - The Great Adventure",
    "description": "...",
    "tags": ["kids", "cartoon", "series"],
    "category_id": "1",
    "privacy_status": "unlisted",
    "thumbnail": "ep01_thumb.jpg",
    "playlist_id": "PLxxxxxxxx"
  }

Exit codes: 0 success, 1 config/auth error, 2 upload/API error.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

DEFAULT_CATEGORY_ID = "1"  # "Film & Animation" -- change per your content
DEFAULT_PRIVACY = "unlisted"  # "private" | "unlisted" | "public"


def load_credentials(token_file: str | None) -> Credentials:
    """Load OAuth credentials from an explicit file, an env var, or a local default."""
    raw = None

    if token_file:
        path = Path(token_file)
        if not path.exists():
            print(f"ERROR: token file not found: {path}", file=sys.stderr)
            sys.exit(1)
        raw = path.read_text()
    elif os.environ.get("YOUTUBE_TOKEN_JSON"):
        raw = os.environ["YOUTUBE_TOKEN_JSON"]
    else:
        default_path = Path("token.json")
        if default_path.exists():
            raw = default_path.read_text()

    if not raw:
        print(
            "ERROR: no credentials found. Provide --token-file, set YOUTUBE_TOKEN_JSON, "
            "or place a token.json next to this script.\n"
            "Generate one with scripts/generate_token.py (run locally, one time).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        print("ERROR: credentials content is not valid JSON.", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_authorized_user_info(info, SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return creds


def upload_video(youtube, args) -> str:
    tags = args.tags.split(",") if args.tags else []
    tags = [t.strip() for t in tags if t.strip()]

    body = {
        "snippet": {
            "title": args.title,
            "description": args.description or "",
            "tags": tags,
            "categoryId": str(args.category_id),
        },
        "status": {
            "privacyStatus": args.privacy,
            "selfDeclaredMadeForKids": args.made_for_kids,
        },
    }

    media = MediaFileUpload(args.file, chunksize=-1, resumable=True, mimetype="video/*")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  Upload progress: {int(status.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < 5:
                retry += 1
                wait = 2 ** retry
                print(f"  Transient error ({e.resp.status}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            print(f"ERROR: upload failed: {e}", file=sys.stderr)
            sys.exit(2)

    video_id = response["id"]
    print(f"Uploaded: https://youtu.be/{video_id}")
    return video_id


def set_thumbnail(youtube, video_id: str, thumbnail_path: str):
    if not thumbnail_path:
        return
    path = Path(thumbnail_path)
    if not path.exists():
        print(f"WARNING: thumbnail not found, skipping: {path}", file=sys.stderr)
        return
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(path))).execute()
        print("Thumbnail set.")
    except HttpError as e:
        print(f"WARNING: failed to set thumbnail: {e}", file=sys.stderr)


def add_to_playlist(youtube, video_id: str, playlist_id: str):
    if not playlist_id:
        return
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"Added to playlist {playlist_id}.")
    except HttpError as e:
        print(f"WARNING: failed to add to playlist: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Upload a video to YouTube")
    parser.add_argument("--file", required=True, help="Path to the video file")
    parser.add_argument("--meta", help="Path to a JSON metadata file (overridden by explicit flags)")
    parser.add_argument("--title", help="Video title")
    parser.add_argument("--description", help="Video description")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--category-id", default=DEFAULT_CATEGORY_ID, help="YouTube category ID")
    parser.add_argument(
        "--privacy", default=DEFAULT_PRIVACY, choices=["private", "unlisted", "public"], help="Privacy status"
    )
    parser.add_argument("--made-for-kids", action="store_true", help="Mark video as made for kids")
    parser.add_argument("--thumbnail", help="Path to a custom thumbnail image")
    parser.add_argument("--playlist-id", help="Playlist ID to add the video to")
    parser.add_argument("--token-file", help="Explicit path to token.json (overrides env/default)")
    args = parser.parse_args()

    # Merge in metadata file values for anything not passed as a flag.
    if args.meta:
        meta_path = Path(args.meta)
        if not meta_path.exists():
            print(f"ERROR: metadata file not found: {meta_path}", file=sys.stderr)
            sys.exit(1)
        meta = json.loads(meta_path.read_text())
        args.title = args.title or meta.get("title")
        args.description = args.description or meta.get("description")
        args.tags = args.tags or (",".join(meta.get("tags", [])) if meta.get("tags") else None)
        if "category_id" in meta and args.category_id == DEFAULT_CATEGORY_ID:
            args.category_id = meta["category_id"]
        if "privacy_status" in meta and args.privacy == DEFAULT_PRIVACY:
            args.privacy = meta["privacy_status"]
        args.thumbnail = args.thumbnail or meta.get("thumbnail")
        args.playlist_id = args.playlist_id or meta.get("playlist_id")
        if not args.made_for_kids:
            args.made_for_kids = bool(meta.get("made_for_kids", False))

    if not args.title:
        print("ERROR: --title is required (or set 'title' in --meta JSON).", file=sys.stderr)
        sys.exit(1)

    video_path = Path(args.file)
    if not video_path.exists():
        print(f"ERROR: video file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    creds = load_credentials(args.token_file)
    youtube = build("youtube", "v3", credentials=creds)

    print(f"Uploading '{video_path.name}' as: {args.title}")
    video_id = upload_video(youtube, args)
    set_thumbnail(youtube, video_id, args.thumbnail)
    add_to_playlist(youtube, video_id, args.playlist_id)

    # Emit machine-readable result for the CI workflow to capture.
    print(json.dumps({"video_id": video_id, "url": f"https://youtu.be/{video_id}"}))


if __name__ == "__main__":
    main()
