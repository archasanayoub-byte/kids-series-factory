#!/usr/bin/env python3
"""
generate_token.py
------------------
RUN THIS LOCALLY ONLY, ONE TIME. Never run this inside GitHub Actions.

It uses your downloaded client_secret_*.json (from Google Cloud Console,
OAuth Client -> Desktop application) to run the interactive OAuth consent
flow in your browser, and produces a self-contained token.json.

token.json contains: access token, refresh token, client_id, client_secret,
token_uri, and scopes. That single file is enough for the upload script to
authenticate forever (it auto-refreshes) WITHOUT ever needing the browser
again. That's the file you paste into the GitHub secret YOUTUBE_TOKEN_JSON.

Usage:
    pip install -r requirements.txt
    python scripts/generate_token.py --client-secret client_secret_XXXX.json

Output:
    token.json  (created in the current directory)
"""

import argparse
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Full upload/manage scope. If you only ever upload (never edit/delete/set
# thumbnails on existing videos), you could narrow this to
# "https://www.googleapis.com/auth/youtube.upload", but the broader scope
# covers thumbnails + playlist management too.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    parser = argparse.ArgumentParser(description="One-time local YouTube OAuth setup")
    parser.add_argument(
        "--client-secret",
        required=True,
        help="Path to the client_secret_*.json downloaded from Google Cloud Console",
    )
    parser.add_argument(
        "--out",
        default="token.json",
        help="Where to write the resulting token file (default: token.json)",
    )
    args = parser.parse_args()

    client_secret_path = Path(args.client_secret)
    if not client_secret_path.exists():
        print(f"ERROR: {client_secret_path} not found.", file=sys.stderr)
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)

    # Opens a local browser window for the Google consent screen.
    # If you're on a headless machine, use run_console() manually instead.
    creds = flow.run_local_server(port=0)

    out_path = Path(args.out)
    out_path.write_text(creds.to_json())

    print(f"\nDone. Wrote {out_path.resolve()}")
    print("\nNext step:")
    print("  1. Open this file and copy its ENTIRE contents.")
    print("  2. In your GitHub repo: Settings -> Secrets and variables -> Actions")
    print("     -> New repository secret -> name it YOUTUBE_TOKEN_JSON -> paste -> Add secret.")
    print("  3. Do NOT commit token.json to git. Delete it locally once the secret is saved,")
    print("     or keep it in a password manager if you want a local backup.")

    # Sanity check the file is valid JSON before we tell the user it's ready.
    try:
        json.loads(out_path.read_text())
    except json.JSONDecodeError:
        print("WARNING: the written file is not valid JSON, something went wrong.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
