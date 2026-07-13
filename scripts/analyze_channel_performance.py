#!/usr/bin/env python3
"""
analyze_channel_performance.py
--------------------------------
Reads real YouTube performance data (via the YouTube Analytics API, using the
yt-analytics.readonly scope added 12 July 2026) and correlates it with what
we know about each episode (character mix, publish day) from
uploaded_manifest.json.

Writes videos/performance_insights.json with a small set of actionable
fields that other tools in this pipeline read:
  - best_character_mix: which lineup (e.g. "bobo+festuk" vs "bobo+festuk+arnouba")
    has the higher average views/retention so far
  - best_publish_weekday: which day-of-week (0=Monday) has performed best,
    if there's enough data to say anything meaningful
  - top_video / bottom_video: title + url + views, for quick reference
  - all_videos: full per-video ranked list (views, retention %, likes, etc.)
    -- added 13 July 2026 so downstream tools (growth_strategist.py) can do
    their own per-video analysis instead of just the two extremes.
  - retention: average retention % across all analyzed videos, how many
    videos are below the 2026 YouTube Shorts distribution threshold, and
    which specific videos are below it -- added 13 July 2026, see NOTES.
  - notes: short plain-English/Arabic-friendly free text summary

RETENTION THRESHOLD NOTE (added 13 July 2026, verified via web research):
As of 2026, YouTube Shorts ranking is driven primarily by average-view-
percentage (retention), not swipe rate. Shorts under 30 seconds need
roughly 65% average view percentage to get pushed to topic-cluster
distribution (shown to interested non-subscribers); 30-60s Shorts need
roughly 50%. All of this channel's episodes are 15s, so the 65% bar is
the one that applies here. This is a real, cited industry-reporting
figure, not an official published YouTube number, so treat it as a
directional benchmark, not a hard guarantee.

Honesty note: the public YouTube Analytics API does NOT expose hour-of-day
audience-activity data (that level of granularity is only in the YouTube
Studio UI's own "Audience" heatmap, not the reporting API). So this tool
only reasons about day-of-week, not time-of-day. Don't claim more precision
than the data actually supports. Similarly, "swipe away" / impressions-based
click-through is a Shorts-feed-specific metric not exposed by this API --
average-view-percentage is used here as the closest available proxy for
the real retention signal YouTube's algorithm actually uses.

Auth: same mechanism as youtube_upload.py (--token-file, or
$YOUTUBE_TOKEN_JSON, or local token.json). Read-only calls, never modifies
anything on the channel.

Never touches git -- purely reads the repo folder + calls the API, and
writes the one local JSON file above.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

CHANNEL_ID = "UCPvzxSkVEwAf9NMt6qU1muQ"
ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "uploaded_manifest.json"
INSIGHTS_PATH = ROOT / "videos" / "performance_insights.json"

# Every episode in this series is ~15s (kling3_0_turbo, duration=15), which
# falls in the "sub-30-second" Shorts bucket -- see RETENTION THRESHOLD NOTE.
RETENTION_TARGET_PCT = 65.0


def load_credentials(token_file: str | None) -> Credentials:
    raw = None
    if token_file:
        path = Path(token_file)
        if not path.exists():
            print(f"ERROR: token file not found: {path}", file=sys.stderr)
            sys.exit(1)
        raw = path.read_text()
    else:
        import os

        if os.environ.get("YOUTUBE_TOKEN_JSON"):
            raw = os.environ["YOUTUBE_TOKEN_JSON"]
        else:
            default_path = ROOT / "token.json"
            if default_path.exists():
                raw = default_path.read_text()

    if not raw:
        print(
            "ERROR: no credentials found. Provide --token-file, set YOUTUBE_TOKEN_JSON, "
            "or place a token.json next to the project root.",
            file=sys.stderr,
        )
        sys.exit(1)

    info = json.loads(raw)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {}
    return json.loads(MANIFEST_PATH.read_text())


def mix_key(characters: list) -> str:
    if not characters:
        return "unknown"
    return "+".join(sorted(characters))


def main():
    parser = argparse.ArgumentParser(description="Analyze بوبو وفستق channel performance")
    parser.add_argument("--token-file", help="Explicit path to token.json (overrides env/default)")
    parser.add_argument("--days", type=int, default=90, help="Lookback window in days (default 90)")
    args = parser.parse_args()

    manifest = load_manifest()
    if not manifest:
        print("No published episodes in uploaded_manifest.json yet -- nothing to analyze.")
        INSIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        INSIGHTS_PATH.write_text(json.dumps({"notes": "No published episodes yet."}, indent=2, ensure_ascii=False))
        return

    creds = load_credentials(args.token_file)
    youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=args.days)

    try:
        response = (
            youtube_analytics.reports()
            .query(
                ids=f"channel=={CHANNEL_ID}",
                startDate=start_date.isoformat(),
                endDate=end_date.isoformat(),
                metrics="views,estimatedMinutesWatched,averageViewPercentage,subscribersGained,likes",
                dimensions="video",
                sort="-views",
                maxResults=200,
            )
            .execute()
        )
    except HttpError as e:
        print(f"ERROR calling YouTube Analytics API: {e}", file=sys.stderr)
        sys.exit(2)

    rows = response.get("rows", [])
    headers = [h["name"] for h in response.get("columnHeaders", [])]
    if not rows:
        print("YouTube Analytics API returned no rows yet (data can lag ~2 days behind real-time).")
        INSIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        INSIGHTS_PATH.write_text(
            json.dumps({"notes": "Analytics data not available yet (may still be processing)."}, indent=2, ensure_ascii=False)
        )
        return

    # video_id -> {views, minutes_watched, avg_view_pct, subs_gained, likes}
    video_stats = {}
    for row in rows:
        rec = dict(zip(headers, row))
        video_stats[rec["video"]] = rec

    # Build video_id -> {title, characters, uploaded_at (weekday)} from the manifest.
    video_meta = {}
    for _filename, entry in manifest.items():
        vid = entry.get("video_id")
        if not vid:
            continue
        uploaded_at = entry.get("uploaded_at")
        weekday = None
        if uploaded_at:
            try:
                weekday = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00")).weekday()
            except ValueError:
                weekday = None
        video_meta[vid] = {
            "title": entry.get("title", ""),
            "url": entry.get("url", ""),
            "characters": entry.get("characters", []),
            "weekday": weekday,
        }

    # --- Correlate character mix with performance ---
    mix_totals = defaultdict(lambda: {"views": 0.0, "avg_view_pct_sum": 0.0, "count": 0})
    weekday_totals = defaultdict(lambda: {"views": 0.0, "count": 0})
    ranked = []

    for vid, stats in video_stats.items():
        meta = video_meta.get(vid, {"title": vid, "url": "", "characters": [], "weekday": None})
        views = float(stats.get("views", 0) or 0)
        avg_pct = float(stats.get("averageViewPercentage", 0) or 0)

        mkey = mix_key(meta["characters"])
        mix_totals[mkey]["views"] += views
        mix_totals[mkey]["avg_view_pct_sum"] += avg_pct
        mix_totals[mkey]["count"] += 1

        if meta["weekday"] is not None:
            weekday_totals[meta["weekday"]]["views"] += views
            weekday_totals[meta["weekday"]]["count"] += 1

        ranked.append(
            {
                "video_id": vid,
                "title": meta["title"],
                "url": meta["url"],
                "characters": meta["characters"],
                "views": views,
                "average_view_percentage": avg_pct,
                "subscribers_gained": float(stats.get("subscribersGained", 0) or 0),
                "estimated_minutes_watched": float(stats.get("estimatedMinutesWatched", 0) or 0),
                "likes": float(stats.get("likes", 0) or 0),
                "below_retention_target": avg_pct < RETENTION_TARGET_PCT,
            }
        )

    ranked.sort(key=lambda r: r["views"], reverse=True)

    # Best character mix = highest average views per video in that mix (needs >=2 samples to be meaningful).
    mix_summary = {}
    best_mix = None
    best_mix_avg = -1
    for mkey, totals in mix_totals.items():
        count = totals["count"]
        avg_views = totals["views"] / count if count else 0
        avg_view_pct = totals["avg_view_pct_sum"] / count if count else 0
        mix_summary[mkey] = {
            "episode_count": count,
            "average_views": round(avg_views, 1),
            "average_view_percentage": round(avg_view_pct, 1),
        }
        if count >= 2 and avg_views > best_mix_avg:
            best_mix_avg = avg_views
            best_mix = mkey

    weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday_summary = {}
    best_weekday = None
    best_weekday_avg = -1
    for wd, totals in weekday_totals.items():
        count = totals["count"]
        avg_views = totals["views"] / count if count else 0
        weekday_summary[weekday_names[wd]] = {"episode_count": count, "average_views": round(avg_views, 1)}
        if count >= 2 and avg_views > best_weekday_avg:
            best_weekday_avg = avg_views
            best_weekday = weekday_names[wd]

    # --- Retention health vs the 2026 Shorts distribution threshold ---
    retention_values = [r["average_view_percentage"] for r in ranked]
    avg_retention = round(sum(retention_values) / len(retention_values), 1) if retention_values else None
    below_target = [r for r in ranked if r["below_retention_target"]]

    insights = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback_days": args.days,
        "episodes_analyzed": len(ranked),
        "best_character_mix": best_mix,
        "character_mix_breakdown": mix_summary,
        "best_publish_weekday": best_weekday,
        "weekday_breakdown": weekday_summary,
        "top_video": ranked[0] if ranked else None,
        "bottom_video": ranked[-1] if len(ranked) > 1 else None,
        "all_videos": ranked,
        "retention": {
            "target_percentage": RETENTION_TARGET_PCT,
            "average_percentage": avg_retention,
            "videos_below_target_count": len(below_target),
            "videos_below_target": [
                {"title": r["title"], "url": r["url"], "average_view_percentage": r["average_view_percentage"]}
                for r in below_target
            ],
        },
        "notes": (
            "Based on {} published episode(s) with analytics data so far. "
            "Hour-of-day posting-time data is not available via the public YouTube Analytics API "
            "(only YouTube Studio's own Audience tab has that) -- only day-of-week patterns are analyzed here. "
            "Character-mix and weekday recommendations need at least 2 episodes per group to be meaningful; "
            "treat anything below that as too early to act on. Retention target ({}%.) is an industry-reported "
            "2026 benchmark for sub-30s Shorts distribution, not an official YouTube-published number -- "
            "treat it as directional."
        ).format(len(ranked), RETENTION_TARGET_PCT),
    }

    INSIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    INSIGHTS_PATH.write_text(json.dumps(insights, indent=2, ensure_ascii=False))
    print(f"Wrote {INSIGHTS_PATH}")
    print(json.dumps(insights, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
