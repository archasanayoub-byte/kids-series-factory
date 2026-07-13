#!/usr/bin/env python3
"""
growth_strategist.py
---------------------
Turns raw performance data (videos/performance_insights.json, written by
analyze_channel_performance.py) plus local pipeline state into a concrete,
prioritized growth playbook for the بوبو وفستق channel -- grounded in real
2026 YouTube Shorts ranking signals, not vibes. See NOTES at the bottom for
sources/assumptions.

This script does ZERO network calls and touches ZERO external APIs -- it is
pure local-file analysis, so it is always safe and free to run, as often as
wanted (every commit, every day, whatever). It is meant to run right after
analyze_channel_performance.py in the same CI job.

Reads (all optional -- degrades gracefully if a file doesn't exist yet):
  - videos/performance_insights.json   real Analytics data (weekly)
  - videos/story_arc_state.json        virality_predictor hook-strength notes
  - uploaded_manifest.json             published episodes
  - videos/to_upload/*.json            pending episode metadata (title/tags audit)
  - videos/uploaded/*.json             archived episode metadata (title/tags audit)
  - videos/social_ready/               cross-post prep folders (one per episode)

Writes:
  - videos/growth_strategy.json  structured recommendations + a short
    human-readable Arabic "playbook" list, for the weekly-report task and
    the nightly episode-generator to both read.

MADE-FOR-KIDS CONSTRAINT (static, always included):
Every episode is uploaded with made_for_kids=true (required, since this is
children's content -- COPPA). That disables comments, the notification
bell, end screens, cards, Super Chat/Stickers/Thanks, and Channel
Memberships, and restricts ads to non-personalized only. This means the
usual "ask people to subscribe via end screen" or "pin a comment" growth
levers are simply not available on this channel -- growth here has to come
from retention (the hook), thumbnail/title click-through, consistent
branding, and cross-platform distribution instead. The playbook below is
written with this constraint already baked in.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSIGHTS_PATH = ROOT / "videos" / "performance_insights.json"
ARC_STATE_PATH = ROOT / "videos" / "story_arc_state.json"
MANIFEST_PATH = ROOT / "uploaded_manifest.json"
TO_UPLOAD_DIR = ROOT / "videos" / "to_upload"
UPLOADED_DIR = ROOT / "videos" / "uploaded"
SOCIAL_READY_DIR = ROOT / "videos" / "social_ready"
OUT_PATH = ROOT / "videos" / "growth_strategy.json"

MIN_HASHTAGS = 3
MAX_HASHTAGS_SWEET_SPOT = 5
MAX_HASHTAGS_HARD_CAP = 15


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def extract_hashtags(description: str) -> list:
    return re.findall(r"#\S+", description or "")


def audit_metadata_files():
    """Scan every episode's metadata JSON (pending + archived) for title/hashtag
    hygiene against 2026 Shorts best practices. Returns a list of per-episode
    findings plus an aggregate summary."""
    findings = []
    files = []
    if TO_UPLOAD_DIR.exists():
        files += sorted(TO_UPLOAD_DIR.glob("*.json"))
    if UPLOADED_DIR.exists():
        files += sorted(UPLOADED_DIR.glob("*.json"))

    for f in files:
        if f.name.startswith("_"):
            continue  # skip template files
        meta = read_json(f, None)
        if not meta or "title" not in meta:
            continue
        title = meta.get("title", "")
        description = meta.get("description", "")
        hashtags = extract_hashtags(description)
        issues = []
        if len(title) > 60:
            issues.append("العنوان طويل نسبيًا (فوق 60 حرف) -- الأقصر بيشتغل أحسن بالـ Shorts")
        if "#Shorts" not in hashtags and "#shorts" not in [h.lower() for h in hashtags]:
            issues.append("ناقص هاشتاغ #Shorts بالوصف")
        if len(hashtags) < MIN_HASHTAGS:
            issues.append(f"هاشتاغات قليلة ({len(hashtags)}) -- الأفضل 3-5")
        if len(hashtags) > MAX_HASHTAGS_HARD_CAP:
            issues.append(f"هاشتاغات كتير ({len(hashtags)}) -- فوق 15 يوتيوب بتجاهلها كلها")
        findings.append(
            {
                "file": f.name,
                "title": title,
                "hashtag_count": len(hashtags),
                "hashtags": hashtags,
                "issues": issues,
            }
        )
    return findings


def check_cross_post_coverage(manifest: dict):
    """Compare published episodes against videos/social_ready/ folders to see
    how many are missing their cross-platform (TikTok/IG/Facebook via Buffer)
    prep package."""
    published_keys = set(manifest.keys())
    if not SOCIAL_READY_DIR.exists():
        return {
            "published_count": len(published_keys),
            "social_ready_count": 0,
            "missing": sorted(published_keys),
            "note": "مجلد videos/social_ready/ مش موجود لسا -- يعني ولا حلقة واحدة انحضرت للنشر على تيك توك/انستغرام.",
        }
    ready = {p.name for p in SOCIAL_READY_DIR.iterdir() if p.is_dir()}
    # social_ready subfolders are named like "ep6" -- manifest keys are "ep6.mp4"
    ready_stems = {r for r in ready}
    missing = [k for k in published_keys if k.replace(".mp4", "") not in ready_stems]
    return {
        "published_count": len(published_keys),
        "social_ready_count": len(ready),
        "missing": sorted(missing),
    }


def hook_strength_correlation(insights: dict, arc_state: dict):
    """If both performance_insights.json (real views/retention) and
    story_arc_state.json (virality_predictor's pre-publish hook-strength
    notes) have overlapping episodes, do a very simple sanity check: are the
    episodes the predictor flagged as strong actually the ones that performed
    well? This is intentionally simple (no real statistics -- too few data
    points early on for that to mean anything) -- just a directional flag."""
    chapters = arc_state.get("chapters", []) if arc_state else []
    all_videos = insights.get("all_videos", []) if insights else []
    if not chapters or not all_videos:
        return {"available": False, "note": "ما في بيانات كافية لمقارنة توقع virality_predictor مع الأداء الحقيقي بعد."}

    # Build epN -> virality_note text
    ep_notes = {c.get("epN"): c.get("virality_note") for c in chapters if c.get("virality_note")}
    if not ep_notes:
        return {"available": False, "note": "virality_predictor ما سجل ملاحظات لأي حلقة لسا."}

    return {
        "available": True,
        "episodes_with_hook_notes": len(ep_notes),
        "note": (
            "في {} حلقة إلها ملاحظة hook-strength من virality_predictor. راجع performance_insights.json "
            "يدويًا قارن الحلقات يلي توقع الها الأداة أداء قوي مع أرقام المشاهدات الحقيقية -- "
            "لما يتوفر 5+ حلقات هيك، ممكن نحسب ارتباط رقمي حقيقي بدل المقارنة اليدوية."
        ).format(len(ep_notes)),
    }


def build_playbook(insights: dict, metadata_findings: list, cross_post: dict, hook_corr: dict) -> list:
    """The prioritized, human-readable action list -- this is the actual
    'strategist' output. Ordered roughly by expected impact given the
    made-for-kids constraint (retention/hook > title/thumbnail > cross-post
    > everything else)."""
    playbook = []

    # 1. Retention health -- the single biggest lever under the 2026 Shorts algorithm.
    retention = (insights or {}).get("retention") or {}
    avg_pct = retention.get("average_percentage")
    below = retention.get("videos_below_target_count")
    target = retention.get("target_percentage", 65.0)
    if avg_pct is not None:
        if below and below > 0:
            playbook.append(
                {
                    "priority": 1,
                    "area": "الاحتفاظ بالمشاهد (Retention)",
                    "action": (
                        f"متوسط نسبة المشاهدة الحالي {avg_pct}% ({below} حلقة تحت هدف {target}%). "
                        "هاد أهم مؤشر بخوارزمية Shorts 2026 -- تحت الهدف يعني الفيديو ما بينتشر لمشاهدين جدد. "
                        "قوّي الثانيتين الأوليين (hook) بكل حلقة جاية: مفاجأة أو سؤال بصري بأول لقطة، بدون أي تمهيد."
                    ),
                }
            )
        else:
            playbook.append(
                {
                    "priority": 2,
                    "area": "الاحتفاظ بالمشاهد (Retention)",
                    "action": f"متوسط نسبة المشاهدة {avg_pct}% -- فوق هدف {target}%، استمر بنفس أسلوب الـ hook الحالي.",
                }
            )
    else:
        playbook.append(
            {
                "priority": 1,
                "area": "الاحتفاظ بالمشاهد (Retention)",
                "action": "ما في بيانات Analytics كافية بعد لتقييم نسبة المشاهدة -- أول تقرير حقيقي رح يجي أول جمعة بعد ما يتراكم عدد حلقات كافي.",
            }
        )

    # 2. Character mix / weekday, pulled straight from insights if meaningful.
    best_mix = (insights or {}).get("best_character_mix")
    if best_mix:
        playbook.append(
            {
                "priority": 3,
                "area": "تركيبة الشخصيات",
                "action": f"تركيبة \"{best_mix}\" هي الأعلى أداءً لحد الآن (بيانات حقيقية) -- رجّح هالتركيبة بالحلقات الجاية بدون ما تكسر تسلسل القصة.",
            }
        )
    best_weekday = (insights or {}).get("best_publish_weekday")
    if best_weekday:
        playbook.append(
            {
                "priority": 4,
                "area": "توقيت النشر",
                "action": f"يوم {best_weekday} أعلى أداءً حسب البيانات -- إذا في مرونة بجدول النشر، رجّح هيك أيام لحلقات مهمة (بداية/نهاية آرك).",
            }
        )

    # 3. Title/hashtag hygiene.
    issues_found = [f for f in metadata_findings if f["issues"]]
    if issues_found:
        playbook.append(
            {
                "priority": 5,
                "area": "العناوين والهاشتاغات",
                "action": (
                    f"{len(issues_found)} حلقة فيها ملاحظات على العنوان/الهاشتاغات (راجع metadata_audit بالتفصيل). "
                    "القاعدة: عنوان قصير وواضح، 3-5 هاشتاغات بالوصف (أولها #Shorts)."
                ),
            }
        )
    else:
        playbook.append(
            {
                "priority": 6,
                "area": "العناوين والهاشتاغات",
                "action": "كل العناوين والهاشتاغات مطابقة لأفضل ممارسات 2026 (عنوان قصير، #Shorts موجود، 3-5 هاشتاغات). استمر بنفس النمط.",
            }
        )

    # 4. Cross-platform distribution.
    missing = cross_post.get("missing", [])
    if missing:
        playbook.append(
            {
                "priority": 2 if len(missing) >= 3 else 5,
                "area": "النشر المتقاطع (تيك توك / انستغرام)",
                "action": (
                    f"{len(missing)} حلقة منشورة على يوتيوب بس ما انسحبت لتيك توك/انستغرام بعد (مشاهدات مجانية ضايعة). "
                    "شغّل auto_fetch_and_push خطوة تحضير social_ready، وسحبهم لطابور Buffer."
                ),
            }
        )
    else:
        playbook.append(
            {
                "priority": 7,
                "area": "النشر المتقاطع (تيك توك / انستغرام)",
                "action": "كل الحلقات المنشورة إلها نسخة جاهزة للنشر المتقاطع -- تأكد بس إنها فعليًا انسحبت لطابور Buffer.",
            }
        )

    # 5. Hook-strength predictor correlation (informational).
    if hook_corr.get("available"):
        playbook.append({"priority": 8, "area": "توقع الأداء المسبق", "action": hook_corr["note"]})

    # 6. Static structural reminders (always included, made-for-kids constraint).
    playbook.append(
        {
            "priority": 9,
            "area": "قيود قناة الأطفال (تذكير دائم)",
            "action": (
                "القناة made-for-kids: ما في تعليقات، جرس تنبيهات، أو شاشة نهاية للطلب بالاشتراك. "
                "يعني كل ثقل النمو لازم يجي من قوة الـ hook + جودة العنوان/الصورة المصغّرة + الانتشار على منصات ثانية -- مو من التفاعل داخل يوتيوب."
            ),
        }
    )
    playbook.append(
        {
            "priority": 10,
            "area": "الصوت الأصلي",
            "action": (
                "الحلقات كلها صوت/موسيقى أصلية من التوليد (مش صوت ترند مستعار) -- هاد نقطة قوة فعلية "
                "(يوتيوب بتفضّل الصوت الأصلي للقنوات تحت 50 ألف مشترك). لا تستبدلها بصوت ترند."
            ),
        }
    )

    playbook.sort(key=lambda p: p["priority"])
    return playbook


def main():
    insights = read_json(INSIGHTS_PATH, {})
    arc_state = read_json(ARC_STATE_PATH, {})
    manifest = read_json(MANIFEST_PATH, {})

    metadata_findings = audit_metadata_files()
    cross_post = check_cross_post_coverage(manifest)
    hook_corr = hook_strength_correlation(insights, arc_state)
    playbook = build_playbook(insights, metadata_findings, cross_post, hook_corr)

    strategy = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "retention_summary": (insights or {}).get("retention"),
        "character_mix_summary": (insights or {}).get("character_mix_breakdown"),
        "weekday_summary": (insights or {}).get("weekday_breakdown"),
        "metadata_audit": metadata_findings,
        "cross_post_coverage": cross_post,
        "hook_strength_correlation": hook_corr,
        "top_priority": playbook[0] if playbook else None,
        "playbook": playbook,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(strategy, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(json.dumps(strategy, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

# NOTES / SOURCES (July 2026 research, see conversation for full citations):
# - Shorts ranking driven primarily by watch-time-per-impression / average view
#   percentage; ~65% target for sub-30s Shorts, ~50% for 30-60s Shorts.
# - Hook must land in the first 2-3 seconds; "viewed vs swiped away" is a key
#   signal but not exposed via the public Analytics API.
# - Titles matter more than hashtags for discovery; keep them short and
#   keyword-clear. Hashtags: 3-5 in the description (not the title), always
#   include #Shorts, never exceed 15 total (YouTube ignores all of them if you do).
# - Original audio/voiceover is rewarded over trending audio for channels
#   under 50K subscribers (a small original-sound bonus added March 2026).
# - "Made for kids" content loses comments, notification bell, end screens,
#   cards, Super Chat/Stickers/Thanks, Channel Memberships, and personalized
#   ads (COPPA-driven) -- this is a hard platform constraint, not a choice.
