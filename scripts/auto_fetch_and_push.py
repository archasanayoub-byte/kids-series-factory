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
  2. Downloads each one straight into videos/to_upload/<filename>, ALSO keeps
     a permanent local-only copy in videos/archive/<filename> (never deleted,
     never pushed to GitHub -- used later to stitch a long-form compilation
     video out of the daily clips), then clears the pending list so nothing
     downloads twice.
  3. Commits and pushes changes to GitHub -- but ONLY inside videos/to_upload,
     videos/uploaded, and uploaded_manifest.json. Deliberately never a blanket
     "git add ." (see SYNC_PATHS below for why), so the GitHub Actions
     publishing schedule picks up new episodes without ever dragging
     unrelated local files along for the ride.
  4. Builds a ready-to-post package for TikTok/Instagram (free-plan Buffer
     workflow) for every episode that already finished publishing on
     YouTube: videos/social_ready/<epN>/video.mp4 + caption.txt. This is
     LOCAL ONLY (never committed to GitHub) -- open the folder, drag the
     video into Buffer, paste the caption, done in ~30 seconds/episode.

Safe to run even if there's nothing pending -- it will just skip straight to
step 3 and push whatever local changes exist in the synced paths (or do
nothing if none).
"""

import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DROP_DIR = ROOT / "videos" / "to_upload"
ARCHIVE_DIR = ROOT / "videos" / "archive"
UPLOADED_DIR = ROOT / "videos" / "uploaded"
SOCIAL_DIR = ROOT / "videos" / "social_ready"
SOCIAL_STATE_PATH = ROOT / "videos" / "social_state.json"
PENDING_PATH = DROP_DIR / "pending_downloads.json"

# The ONLY paths this script ever stages/commits/pushes. Deliberately narrow
# and explicit -- a past version of this script ran a blanket "git add ."
# and it once swept up a large batch of unrelated local-only project files
# (docs, coloring-book assets, a whole separate show's bible files, etc.)
# into a single "add new episode video(s)" commit. That commit then
# diverged from origin (origin already had its own, different versions of
# some of those same paths) and broke the next pull with add/add conflicts.
# Scoping to exactly the folders this script is responsible for makes that
# class of failure impossible going forward.
SYNC_PATHS = ["videos/to_upload", "videos/uploaded", "uploaded_manifest.json"]

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
            try:
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, ARCHIVE_DIR / filename)
                print(f"  -> archived copy at {ARCHIVE_DIR / filename}")
            except Exception as archive_err:  # noqa: BLE001
                print(f"  (warning: could not archive a copy: {archive_err})")
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


EXTRA_HASHTAGS = ["#Reels", "#fyp", "#foryou", "#كرتون_اطفال", "#اطفال"]


def _load_social_state():
    if SOCIAL_STATE_PATH.exists():
        try:
            return json.loads(SOCIAL_STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"done": []}


def _save_social_state(state):
    SOCIAL_STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _build_caption(meta):
    title = meta.get("title", "").strip()
    description = meta.get("description", "")
    # first non-empty line of the description is the real story hook;
    # the rest (call-to-action + #Shorts) is YouTube-specific, so drop it.
    first_line = ""
    for line in description.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            first_line = line
            break

    tags = meta.get("tags", [])
    hashtags = []
    for t in tags:
        token = t.strip().replace(" ", "_")
        if token and token.lower() != "shorts":
            hashtags.append("#" + token)
    for extra in EXTRA_HASHTAGS:
        if extra not in hashtags:
            hashtags.append(extra)

    parts = [title, first_line, "تابعونا لمزيد من حلقات بوبو وفستق يومياً 🎬", " ".join(hashtags)]
    return "\n\n".join(p for p in parts if p)


def prepare_social_content():
    """Build a Buffer-ready (video + caption) package for every episode that
    has already finished publishing on YouTube (its metadata now lives in
    videos/uploaded/) and has a matching raw clip in videos/archive/.
    Never touches git -- purely local staging for manual posting.
    """
    if not UPLOADED_DIR.exists():
        return
    state = _load_social_state()
    done = set(state.get("done", []))
    made_any = False

    for meta_path in sorted(UPLOADED_DIR.glob("*.json")):
        ep_name = meta_path.stem  # e.g. "ep5"
        if ep_name in done:
            continue
        archive_video = ARCHIVE_DIR / f"{ep_name}.mp4"
        if not archive_video.exists():
            # episode published before the archiving feature existed, or
            # archive copy missing for some other reason -- skip quietly.
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        out_dir = SOCIAL_DIR / ep_name
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archive_video, out_dir / "video.mp4")
        (out_dir / "caption.txt").write_text(_build_caption(meta), encoding="utf-8")

        done.add(ep_name)
        made_any = True
        print(f"  -> prepared social post package: {out_dir}")

    if made_any:
        state["done"] = sorted(done)
        _save_social_state(state)
        print(f"Social-ready packages are in {SOCIAL_DIR} -- upload to Buffer whenever you like.")
    else:
        print("No new episodes to prepare for social (nothing published yet, or already done).")


def run(cmd):
    print(f"\n$ {' '.join(cmd)}")
    # IMPORTANT: force utf-8 decoding for the subprocess output. Without this,
    # Python falls back to the Windows system locale codepage (e.g. cp1255 on
    # a Hebrew-locale machine), which crashes with UnicodeDecodeError as soon
    # as git prints any byte sequence that isn't valid in that codepage
    # (common with Arabic commit messages/paths in this repo). errors="replace"
    # is a second safety net so a single bad byte never kills the whole run.
    result = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if (result.stdout or "").strip():
        print(result.stdout.strip())
    if (result.stderr or "").strip():
        print(result.stderr.strip())
    return result.returncode


def _clear_stale_lock():
    """Remove a leftover .git/index.lock from a previous run that crashed or
    was killed mid-operation. This script is the only thing that ever runs
    git automatically in this repo, so a lock file still sitting here when a
    new run starts always means a prior process died without cleaning up --
    never a real concurrent git process -- so it is always safe to delete."""
    lock = ROOT / ".git" / "index.lock"
    if lock.exists():
        try:
            lock.unlink()
            print("  (cleared a leftover .git/index.lock from a previous run)")
        except Exception as e:  # noqa: BLE001
            print(f"  (warning: could not remove stale index.lock: {e})")


def git_sync():
    _clear_stale_lock()
    pull_code = run(["git", "pull", "--no-edit"])
    if pull_code != 0:
        # Do NOT continue to add/commit/push on top of a failed pull -- that
        # is exactly what created a diverged, broken local branch before.
        # Stop here with a clear message instead of silently pressing on.
        print(
            "\ngit pull failed -- stopping here on purpose instead of "
            "committing on top of an out-of-date branch (that always ends "
            "in a rejected push, or worse, a messy diverged history). Fix "
            "whatever the message above says, then just run this script "
            "again -- nothing has been lost, your downloaded video(s) are "
            "still sitting safely in videos/to_upload/."
        )
        return

    print("\n--- preparing TikTok/Instagram (Buffer) packages ---")
    try:
        prepare_social_content()
    except Exception as e:  # noqa: BLE001
        print(f"  (warning: social prep step failed, skipping: {e})")

    _clear_stale_lock()
    run(["git", "add", "--"] + SYNC_PATHS)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--"] + SYNC_PATHS,
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if not (status.stdout or "").strip():
        print("Nothing new to commit.")
        return

    _clear_stale_lock()
    run(["git", "commit", "-m", "auto: add new episode video(s)"])
    code = run(["git", "push"])
    if code != 0:
        # Most likely cause: origin moved ahead between our pull and our push
        # (e.g. the CI bot committed a cleanup in the meantime). Pull once
        # more and retry the push automatically instead of just giving up.
        print("\ngit push failed -- retrying once after a fresh pull...")
        _clear_stale_lock()
        retry_pull_code = run(["git", "pull", "--no-edit"])
        if retry_pull_code != 0:
            print(
                "\ngit pull retry also failed -- a human needs to look at "
                "the repo state (see messages above). Your new commit is "
                "still safe locally, nothing is lost."
            )
            return
        _clear_stale_lock()
        code = run(["git", "push"])
    if code == 0:
        print(
            "\nPushed successfully -- new episodes will publish automatically "
            "at the next scheduled time."
        )
    else:
        print(
            "\ngit push still failed after retry -- check the messages above "
            "(this needs a human to look at the repo state)."
        )


def main():
    print("=== Bobo & Festuk: auto fetch + publish ===\n")
    download_pending()
    print("\n--- syncing with GitHub ---")
    git_sync()
    print("\nDone.")


if __name__ == "__main__":
    main()
