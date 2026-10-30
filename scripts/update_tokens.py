#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

URL = "https://huggingface.co/api/daily_papers"
HEADERS = {"User-Agent": "YibingSong-Homepage/1.0"}
OUT = Path(__file__).resolve().parents[1] / "tokens.json"
MAX_TOKENS = 30
HISTORY_CAP = 40
MIN_TITLE_HITS = 2
MAX_BYTES = 4 * 1024 * 1024

STOP = {
    "THE", "AND", "FOR", "WITH", "FROM", "VIA", "NEW", "NOT", "BUT", "CAN",
    "HOW", "WHY", "WHAT", "WHEN", "WHERE", "WHO", "AI", "ML", "NLP", "CV",
    "IEEE", "ACM", "AAAI", "USA", "UK", "EU", "SOTA", "II", "III", "IV",
    "VI", "VII", "IX", "XI", "OK", "TO", "IN", "ON", "OF", "AT", "BY", "OR",
    "IF", "IS", "IT", "AS", "AN", "DO", "GO", "NO", "SO", "UP", "WE", "BE",
}

PHRASES = [
    "agent", "agentic", "reasoning", "chain-of-thought", "test-time",
    "tool use", "self-play", "reward model", "verifier", "distillation",
    "diffusion", "mixture of experts", "long context", "world model",
    "multimodal", "vision-language", "reinforcement learning", "scaling law",
    "code generation", "video generation", "unified model", "inference", "memory",
]

ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}(?:-[A-Za-z0-9]+)*\b")
MODEL_RE = re.compile(r"\b[A-Za-z]\d{1,2}(?:-[A-Za-z0-9]+)?\b")
TERM_RE = re.compile(r"[A-Za-z0-9 -]{1,24}")


def _clean(text):
    for raw, escaped in (("%", "%25"), ("\r", "%0D"), ("\n", "%0A")):
        text = text.replace(raw, escaped)
    return text


def fail(reason):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title=Trending token fetch::{_clean(reason)}")
    print(f"WARNING: preserving previous tokens and timestamp: {reason}", file=sys.stderr)
    return 1


def extract(titles):
    counts = Counter()
    for title in dict.fromkeys(titles):
        terms = set(ACRONYM_RE.findall(title) + MODEL_RE.findall(title)) - STOP
        for phrase in PHRASES:
            pattern = r"(?<!\w)" + re.escape(phrase) + r"s?(?!\w)"
            if re.search(pattern, title, re.IGNORECASE):
                terms.add(phrase)
        counts.update(t for t in terms if TERM_RE.fullmatch(t))
    return counts


def fetch_feed(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        status = response.status
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"response exceeds {MAX_BYTES} byte limit")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError(f"feed is {type(data).__name__}, expected a list")
    return status, data


def titles_from(data):
    titles = []
    for item in data:
        if not isinstance(item, dict):
            continue
        paper = item.get("paper")
        if not isinstance(paper, dict):
            continue
        title = paper.get("title")
        if isinstance(title, str) and 0 < len(title) <= 1000:
            titles.append(title)
    return titles


def ranked_terms(counts):
    order = sorted(counts, key=lambda term: (-counts[term], term.casefold()))
    return [term for term in order if counts[term] >= MIN_TITLE_HITS]


def load_history():
    if not OUT.exists():
        return []
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8"))
    except ValueError:
        return []
    prior = previous.get("recent") if isinstance(previous, dict) else None
    if not isinstance(prior, list):
        return []
    return [t for t in prior if isinstance(t, str) and TERM_RE.fullmatch(t)]


def backfill_history(history, days):
    today = datetime.now(timezone.utc).date()
    for offset in range(days, 0, -1):
        day = today - timedelta(days=offset)
        try:
            _, data = fetch_feed(f"{URL}?date={day.isoformat()}")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
            continue
        for term in ranked_terms(extract(titles_from(data))):
            if term not in history:
                history.append(term)
    return history


def main() -> int:
    backfill = int(os.environ.get("BACKFILL_DAYS", "0") or 0)

    try:
        status, data = fetch_feed(URL)
    except urllib.error.HTTPError as error:
        return fail(f"HTTP {error.code} {error.reason}")
    except urllib.error.URLError as error:
        return fail(f"unreachable: {error.reason}")
    except (TimeoutError, OSError) as error:
        return fail(f"request failed: {error}")
    except ValueError as error:
        return fail(str(error))

    titles = titles_from(data)
    if not titles:
        return fail(
            f"HTTP {status}, {len(data)} feed entries but no usable "
            f"paper.title: the daily feed may be empty at this hour"
        )

    counts = extract(titles)
    tokens = ranked_terms(counts)[:MAX_TOKENS]
    if not tokens:
        return fail(
            f"{len(set(titles))} distinct titles yielded {len(counts)} terms but none "
            f"reached the {MIN_TITLE_HITS}-title threshold"
        )

    history = load_history()
    if backfill > 0:
        history = backfill_history(history, backfill)
    recent = list(tokens)
    for term in history:
        if term not in recent:
            recent.append(term)
    recent = recent[:HISTORY_CAP]

    payload = {
        "updated": datetime.now(timezone.utc).date().isoformat(),
        "source": URL,
        "papers": len(set(titles)),
        "tokens": tokens,
        "recent": recent,
    }
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(OUT)
    print(f"tokens: {len(tokens)} today, {len(recent)} in rolling window from {payload['papers']} papers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
