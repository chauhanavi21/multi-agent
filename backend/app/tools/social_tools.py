"""Mocked Facebook/Instagram trend tools.

In Phase 5, replace these with calls to Meta Graph API:
  https://developers.facebook.com/docs/graph-api/
  https://developers.facebook.com/docs/instagram-platform/

For now they return realistic-shaped fake data so agents work end-to-end.
"""
from __future__ import annotations
import hashlib
import random
from datetime import datetime, timedelta


# Deterministic fake data — same query -> same output (helps debugging)
_BASE_HASHTAGS = {
    "b2b saas": ["#saastools", "#productled", "#dev2dev", "#agenticops", "#noBS", "#leanstartup"],
    "fintech": ["#openbanking", "#paytech", "#defi2", "#realtimemoney", "#kyclite"],
    "healthtech": ["#patientfirst", "#fhir", "#aihealth", "#telehealth2", "#hipaaeasy"],
    "ai": ["#agenticai", "#llmops", "#localllm", "#rag2026", "#smolagents"],
    "developer tools": ["#devex", "#shipfast", "#opensource", "#tooling", "#dxmatters"],
    "design agency": ["#brandvoice", "#micromotion", "#design2026", "#tokens"],
    "supply chain": ["#chainviz", "#logisticstech", "#middlemile", "#predict4supply"],
    "default": ["#trending", "#growth", "#startup", "#community", "#momentum"],
}


def _topic_key(topic: str) -> str:
    t = (topic or "").lower()
    for k in _BASE_HASHTAGS:
        if k != "default" and k in t:
            return k
    return "default"


def _seeded_rand(seed_str: str):
    h = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    return random.Random(h)


def get_trending_hashtags(topic: str, platform: str = "instagram", limit: int = 8):
    """Return mock trending hashtags for a topic on a platform."""
    key = _topic_key(topic)
    base = _BASE_HASHTAGS[key].copy()
    if key != "default":
        base += _BASE_HASHTAGS["default"]
    r = _seeded_rand(f"{topic}:{platform}")
    r.shuffle(base)
    base = base[:limit]
    return [
        {
            "tag": tag,
            "platform": platform,
            "posts_7d": r.randint(800, 240_000),
            "growth_pct": round(r.uniform(-12, 180), 1),
        }
        for tag in base
    ]


def get_top_posts(topic: str, platform: str = "instagram", limit: int = 5):
    """Return mock top-performing posts for a topic."""
    r = _seeded_rand(f"posts:{topic}:{platform}")
    fake_authors = [
        "@maya.builds", "@nikhil_writes", "@aria.codes", "@deepak.devops",
        "@studiohana", "@buildwithjas", "@marcus.scales", "@priya.ships",
    ]
    snippets = [
        f"How we cut {topic} infra cost by {r.randint(20, 70)}% in 6 weeks",
        f"The {r.randint(3, 7)} mistakes every {topic} founder makes",
        f"We replaced our {topic} stack with a single LLM call. Here's the result.",
        f"Inside our {topic} team's daily workflow",
        f"Why nobody is talking about this in {topic}",
    ]
    return [
        {
            "author": r.choice(fake_authors),
            "platform": platform,
            "snippet": r.choice(snippets),
            "likes": r.randint(200, 18_500),
            "comments": r.randint(8, 420),
            "posted_at": (datetime.utcnow() - timedelta(hours=r.randint(2, 168))).isoformat(),
        }
        for _ in range(limit)
    ]


def get_audience_sentiment(topic: str, platform: str = "instagram"):
    """Return rough sentiment buckets."""
    r = _seeded_rand(f"sent:{topic}:{platform}")
    pos = r.randint(40, 75)
    neu = r.randint(15, 100 - pos - 5)
    neg = 100 - pos - neu
    return {
        "topic": topic,
        "platform": platform,
        "positive_pct": pos,
        "neutral_pct": neu,
        "negative_pct": neg,
        "sample_size": r.randint(800, 12_000),
    }
