#!/usr/bin/env python3
"""
download_coloring_book_assets.py
----------------------------------
One-off helper: downloads the coloring-book cover + page images (generated
via Higgsfield) straight from the raw CDN URLs into
coloring_book/images/ next to this script's project root.

Run this once (double-click download_coloring_book.bat, or
`python scripts\\download_coloring_book_assets.py`), same idea as the
existing run_daily_publish.bat for episode videos -- the CDN is only
reachable from your own PC's network, not from Claude's sandbox.
"""

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "coloring_book" / "images"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

ASSETS = [
    ("00_cover.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210435_fa06ee52-e032-440a-bd1e-642a7dcf707c.png"),
    ("01_honey.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210437_940f905b-f38d-4530-99b2-43fd53759268.png"),
    ("02_acorns.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210447_b5016918-d189-4c0c-a369-d1693b9563f3.png"),
    ("03_flower_hop.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210450_43714966-5af1-4493-a1d3-4b98d0db3be7.png"),
    ("04_picnic.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210451_73d7a4fd-2a57-4c01-a2ee-c92051e47f75.png"),
    ("05_fishing.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_211755_103578b8-77e7-49f6-a631-404741f2cc5f.png"),
    ("06_climbing.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210455_e46bf941-34bd-427d-96d9-dbb46a442f91.png"),
    ("07_kite.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210456_886914ca-6676-4474-8f51-5c6aacaeb075.png"),
    ("08_umbrella.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210458_75caba32-75f4-4315-a44d-0af74a813863.png"),
    ("09_fort.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_212215_6de35caa-21fc-412f-b14b-31a2c321aa9e.png"),
    ("10_reading.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_210500_d421c439-5dcd-4cbe-8377-b600ce247a5e.png"),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=== Downloading coloring book images ===\n")
    ok = 0
    for filename, url in ASSETS:
        target = OUT_DIR / filename
        print(f"Downloading {filename} ...")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as out:
                out.write(resp.read())
            print(f"  -> saved {target}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  !! FAILED: {e}")

    print(f"\nDone. {ok}/{len(ASSETS)} images downloaded to {OUT_DIR}")


if __name__ == "__main__":
    main()
