#!/usr/bin/env python3
"""
auto_fetch_and_push.py
-----------------------
Run this (by double-clicking run_daily_publish.bat in the project folder)
any time after the nightly episode-generation task has finished.

It does everything by itself, so nobody has to open PowerShell or type any
git commands by hand:

  1. Reads videos/to_upload/pending_downloads.json (written automatically by
     Claude after generating new episodes) -- a list of
     {"filename": ..., "url": ...} pointing at the raw Higgsfield video files.
  2. Downloads each one straight into videos/to_upload/<filename>, then
     clears the pending list so nothing downloads twice.
  3. Commits and pushes any changes in the project folder to GitHub, so the
     GitHub Actions publishing schedule picks up the new episodes
     automatically at the next 09:00 / 13:00 / 17:00 slot.

Safe to run even if there's nothing pending -- it will just skip straight to
step 3 and push whatever local changes exist (or do nothing if none).
"""

import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DROP_DIR = ROOT / "videos" / "to_upload"
PENDING_PATH = DROP_DIR / "pending_downloads.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def download_pending():
    if not PENDING_PATH.exists():
        print("No pending_downloads.json found -- nothing new to fetch.")
        return

    try:
        pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("pending_downloads.json is empty/invalid, skipping downloads.")
        pending = []

    if not pending:
        print("Pending download list is empty -- nothing new to fetch.")
        return

    still_pending = []
    for item in pending:
        filename = item.get("filename")
        url = item.get("url")
        if not filename or not url:
            continue
        target = DROP_DIR / filename
        if target.exists():
            print(f"{filename} already exists locally, skipping download.")
            continue
        print(f"Downloading {filename} ...")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180) as resp, open(target, "wb") as out:
                out.write(resp.read())
            print(f"  -> saved {target}")
        except Exception as e:  # noqa: BLE001
            print(f"  !! FAILED to download {filename}: {e}")
            still_pending.append(item)

    PENDING_PATH.write_text(
        json.dumps(still_pending, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if still_pending:
        print(f"{len(still_pending)} download(s) failed and will be retried next run.")
    else:
        print("All pending videos downloaded successfully.")


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    return result.returncode


def git_sync():
    run(["git", "pull", "--no-edit"])
    run(["git", "add", "."])
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    )
    if not status.stdout.strip():
        print("Nothing new to commit.")
        return
    run(["git", "commit", "-m", "auto: add new episode video(s)"])
    code = run(["git", "push"])
    if code == 0:
        print(
            "\nPushed successfully -- new episodes will publish automatically "
            "at the next scheduled time."
        )
    else:
        print("\ngit push failed -- check the messages above.")


def main():
    print("=== Bobo & Festuk: auto fetch + publish ===\n")
    download_pending()
    print("\n--- syncing with GitHub ---")
    git_sync()
    print("\nDone.")


if __name__ == "__main__":
    main()
