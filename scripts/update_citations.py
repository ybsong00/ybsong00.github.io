#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHOLAR_ID = "oRhJHmIAAAAJ"
URL = f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en"
OUT = Path(__file__).resolve().parents[1] / "citations.json"
MAX_BYTES = 2 * 1024 * 1024
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def main() -> int:
    try:
        req = urllib.request.Request(URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Scholar response exceeds size limit")
        html = raw.decode("utf-8", "ignore")
        counts = re.findall(r'class="gsc_rsb_std">([\d,]+)</td>', html)
        if not counts:
            raise ValueError("citation count not found in profile page")
        citations = int(counts[0].replace(",", ""))
        if citations <= 0:
            raise ValueError("invalid citation count")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        print(f"WARNING: preserving previous citation count: {error}", file=sys.stderr)
        return 1

    payload = {"citations": citations, "updated": datetime.now(timezone.utc).date().isoformat()}
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUT)
    print(f"citations: {citations}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
