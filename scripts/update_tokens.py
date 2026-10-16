#!/usr/bin/env python3
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

URL = "https://huggingface.co/api/daily_papers"
HEADERS = {"User-Agent": "YibingSong-Homepage/1.0"}
OUT = Path(__file__).resolve().parents[1] / "tokens.json"
MAX_TOKENS = 30
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


def main() -> int:
    try:
        req = urllib.request.Request(URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("paper feed exceeds size limit")
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("paper feed is not a list")
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
        counts = extract(titles)
        ranked = sorted(counts, key=lambda term: (-counts[term], term.casefold()))
        tokens = [term for term in ranked if counts[term] >= 2][:MAX_TOKENS]
        if not tokens:
            raise ValueError("no terms found in at least two distinct paper titles")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        print(f"WARNING: preserving previous tokens and timestamp: {error}", file=sys.stderr)
        return 1

    payload = {
        "updated": datetime.now(timezone.utc).date().isoformat(),
        "source": URL,
        "papers": len(set(titles)),
        "tokens": tokens,
    }
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(OUT)
    print(f"tokens: {len(tokens)} from {payload['papers']} distinct papers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
