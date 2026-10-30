#!/usr/bin/env python3
import json
import os
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

BLOCK_MARKERS = ("unusual traffic", "not a robot", "/sorry/index", "enablejs", "recaptcha")


def _clean(text):
    """Workflow-command fields must not contain these sequences."""
    for raw, escaped in (("%", "%25"), ("\r", "%0D"), ("\n", "%0A")):
        text = text.replace(raw, escaped)
    return text


def fail(reason):
    # Run logs need admin rights to read, but annotations do not, so the
    # precise reason is surfaced there instead of only on stderr.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title=Scholar citation fetch::{_clean(reason)}")
    print(f"WARNING: preserving previous citation count: {reason}", file=sys.stderr)
    return 1


def main() -> int:
    try:
        req = urllib.request.Request(URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.status
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        return fail(f"HTTP {error.code} {error.reason}: Scholar rejects datacenter IPs")
    except urllib.error.URLError as error:
        return fail(f"unreachable: {error.reason}")
    except (TimeoutError, OSError) as error:
        return fail(f"request failed: {error}")

    if len(raw) > MAX_BYTES:
        return fail(f"response exceeds {MAX_BYTES} byte limit")

    html = raw.decode("utf-8", "ignore")
    markers = [m for m in BLOCK_MARKERS if m in html.lower()]
    counts = re.findall(r'class="gsc_rsb_std">([\d,]+)</td>', html)

    if not counts:
        if markers:
            return fail(
                f"served an anti-bot page instead of the profile "
                f"(HTTP {status}, {len(raw)} bytes, markers={markers})"
            )
        return fail(
            f"HTTP {status}, {len(raw)} bytes, but no gsc_rsb_std cell found: "
            f"profile markup may have changed (block markers={markers or 'none'})"
        )

    citations = int(counts[0].replace(",", ""))
    if citations <= 0:
        return fail(f"profile reported a non-positive citation count: {counts[0]}")

    payload = {"citations": citations, "updated": datetime.now(timezone.utc).date().isoformat()}
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUT)
    print(f"citations: {citations}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
