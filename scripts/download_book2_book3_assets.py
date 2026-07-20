#!/usr/bin/env python3
"""
download_book2_book3_assets.py
--------------------------------
One-off helper: downloads the cover + page images for the two new coloring
books (Beach, Birthday Party) from the Higgsfield CDN into
coloring_book_beach/images/ and coloring_book_birthday/images/.
Same pattern as download_coloring_book_assets.py -- run via
download_book2_book3.bat since the CDN is only reachable from your own PC.
"""

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

BEACH_DIR = ROOT / "coloring_book_beach" / "images"
BEACH_ASSETS = [
    ("00_cover.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215121_cbed91b2-8919-4b22-b78f-51e752ca5e39.png"),
    ("01_sandcastle.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215131_c255d8f3-d3d2-48dd-81ef-fbd3c963d2db.png"),
    ("02_swimming.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215132_542e71f7-d7d4-44c5-ac68-3ba2f4c6c07d.png"),
    ("03_shells.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215134_a0d982f1-c5f7-4b0e-b3f4-918d6410c177.png"),
    ("04_beachball.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215135_59d1d579-0664-4fa0-a8eb-525353efec73.png"),
    ("05_boat_v2.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215646_834597f0-712d-49ad-8167-527f479f7a2e.png"),
    ("06_icecream.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215144_b7d1fb1a-aad6-411e-a092-b738f1a98214.png"),
    ("07_crab.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215145_6055e047-97eb-489f-8f28-ad73eaef0ae6.png"),
    ("08_umbrella.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215146_aac883bb-c72c-4764-81db-3ff70cf0707a.png"),
    ("09_splashing.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215149_324f4f7d-4f52-49b6-b027-51e47c2e0c03.png"),
    ("10_sunset.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215150_7ccd31c1-eb57-457f-ba1b-c04d5273cbcb.png"),
]

BIRTHDAY_DIR = ROOT / "coloring_book_birthday" / "images"
BIRTHDAY_ASSETS = [
    ("00_cover.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215123_aaaefc59-a1df-4fe0-9044-3ac72237621e.png"),
    ("01_cake.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215158_31e4334c-e568-448b-a7e0-f8c5bb7c0f06.png"),
    ("02_balloons.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215200_029a8672-d8d0-4e8a-bcd8-483ae668586d.png"),
    ("03_present.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215201_9129b8aa-36c1-426a-882a-fe218d37b065.png"),
    ("04_pinata.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215648_c9382c55-b647-4077-826d-5aaacf477fb4.png"),
    ("05_partyhorns.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215650_1f29dcff-ff08-4f3e-a540-5b5089fee0cd.png"),
    ("06_musicalchairs.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215213_d2c63c5d-9a9d-47fb-9655-dc771756f737.png"),
    ("07_favorbags.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215214_bedcfaee-1e8d-4ede-ad73-ae6b548c6688.png"),
    ("08_balloonanimal.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215216_d16ed9d4-0f44-409a-859a-bbcbffc33d31.png"),
    ("09_dancing.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215218_89dee652-d50d-4920-bd7b-cbbc512eb93a.png"),
    ("10_groupphoto.png", "https://d8j0ntlcm91z4.cloudfront.net/user_3GM6oV3kftWV6OyqqZLik3rwgcQ/hf_20260712_215219_4bf2d698-6e47-4cda-a477-47b490bdc68a.png"),
]


def download_all(out_dir, assets, label):
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Downloading {label} ({len(assets)} files) ===")
    ok = 0
    for filename, url in assets:
        target = out_dir / filename
        print(f"Downloading {filename} ...")
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp, open(target, "wb") as out:
                out.write(resp.read())
            print(f"  -> saved {target}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  !! FAILED: {e}")
    print(f"{label}: {ok}/{len(assets)} downloaded.")


def main():
    download_all(BEACH_DIR, BEACH_ASSETS, "Beach book")
    download_all(BIRTHDAY_DIR, BIRTHDAY_ASSETS, "Birthday book")
    print("\nDone with both books.")


if __name__ == "__main__":
    main()
