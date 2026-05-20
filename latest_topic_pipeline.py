#!/usr/bin/env python3
"""
Generate a daily "latest topic" content package from recent tech/AI headlines.

The output JSON is shaped like a tech content config file so it can be passed
directly into tech_video_creator.py and shorts_creator.py.
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from google import genai


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_QUERY = (
    "artificial intelligence OR generative AI OR large language model OR OpenAI "
    "OR Anthropic OR Google AI OR Microsoft AI OR NVIDIA"
)
DEFAULT_MODEL = "gemini-2.5-flash"
LOCAL_TZ = ZoneInfo("America/Detroit")
DEFAULT_SOURCE_URL = os.environ.get("LATEST_TOPIC_SOURCE_URL", "")


def build_manual_items(source_topic: str, source_notes: str = "") -> list[dict]:
    topic = normalize_sentence(source_topic).rstrip(".")
    notes = normalize_sentence(source_notes) if source_notes else ""
    title = topic if not notes else f"{topic} - {notes}"
    return [
        {
            "title": title,
            "link": "",
            "source": "manual_input",
            "published_at": datetime.now(LOCAL_TZ).isoformat(),
        }
    ]


def build_manual_topic_prompt(source_topic: str, source_text: str, source_notes: str, today_label: str) -> str:
    return f"""You are preparing an original educational YouTube video package from a manually submitted topic.

Today is {today_label}.

Topic:
{source_topic}

User-provided source text:
{source_text}

Optional notes:
{source_notes or "None"}

Return ONLY valid JSON with this exact shape:
{{
  "category": "ai",
  "headline": "Clean source headline based on the topic",
  "source": "manual_input",
  "published_at": "{datetime.now(LOCAL_TZ).isoformat()}",
  "video_topic": "Short clean topic title for the video",
  "video_summary": "2 to 3 sentence original educational summary based on the user text",
  "short_text": "1 to 2 short spoken-friendly sentences for a vertical short",
  "points": ["point 1", "point 2", "point 3", "point 4"],
  "search_terms": "Pexels-friendly visual search terms",
  "topic_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}

Rules:
- Keep the final package original and educational
- Preserve the key idea from the user text, but rewrite it clearly
- category must be one of: ai, llm, rag, database, mcp
- video_topic must be under 70 characters
- points must be short and easy to narrate
- topic_tags must be lowercase
- if the topic is general AI or product news, prefer category "ai"
"""


def slugify(text: str) -> str:
    text = (text or "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or "latest_topic"


def normalize_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    text = text.replace("—", "-").replace("–", "-")
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _looks_like_feed(content_type: str, text: str) -> bool:
    ct = (content_type or "").lower()
    sample = (text or "")[:400].lstrip().lower()
    return (
        "xml" in ct
        or "rss" in ct
        or sample.startswith("<?xml")
        or sample.startswith("<rss")
        or sample.startswith("<feed")
    )


class RecentLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._current_href = None
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        attr_map = dict(attrs)
        href = (attr_map.get("href") or "").strip()
        if href:
            self._current_href = href
            self._text_parts = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self._current_href is None:
            return
        text = normalize_sentence(" ".join(self._text_parts)).strip()
        text = text[:-1] if text.endswith(".") else text
        if len(text) >= 25:
            self.links.append({"title": text, "href": self._current_href})
        self._current_href = None
        self._text_parts = []


def fetch_recent_headlines(query: str, limit: int = 12) -> list[dict]:
    rss_url = "https://news.google.com/rss/search"
    response = requests.get(
        rss_url,
        params={"q": f"{query} when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"},
        timeout=20,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None and source_el.text else ""

        pub_date = ""
        if pub_date_raw:
            try:
                pub_date = parsedate_to_datetime(pub_date_raw).astimezone(LOCAL_TZ).isoformat()
            except Exception:
                pub_date = pub_date_raw

        if title:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "source": source,
                    "published_at": pub_date,
                }
            )
    return items


def fetch_items_from_feed_url(source_url: str, limit: int = 12) -> list[dict]:
    response = requests.get(source_url, timeout=20, headers={"User-Agent": "youtube-auto/1.0"})
    response.raise_for_status()
    root = ET.fromstring(response.content)

    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None and source_el.text else source_url
        pub_date = ""
        if pub_date_raw:
            try:
                pub_date = parsedate_to_datetime(pub_date_raw).astimezone(LOCAL_TZ).isoformat()
            except Exception:
                pub_date = pub_date_raw
        if title:
            items.append({"title": title, "link": link, "source": source, "published_at": pub_date})

    if items:
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("./atom:entry", ns)[:limit]:
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        pub_date = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
        link = ""
        for link_el in entry.findall("atom:link", ns):
            href = (link_el.attrib.get("href") or "").strip()
            if href:
                link = href
                break
        if title:
            items.append({"title": title, "link": link, "source": source_url, "published_at": pub_date})
    return items


def fetch_items_from_html_url(source_url: str, limit: int = 12) -> list[dict]:
    response = requests.get(source_url, timeout=20, headers={"User-Agent": "youtube-auto/1.0"})
    response.raise_for_status()
    parser = RecentLinkParser()
    parser.feed(response.text)

    seen = set()
    items = []
    for link in parser.links:
        href = urljoin(source_url, link["href"])
        key = (link["title"].lower(), href)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "title": link["title"],
                "link": href,
                "source": source_url,
                "published_at": "",
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_items_from_source_url(source_url: str, limit: int = 12) -> list[dict]:
    response = requests.get(source_url, timeout=20, headers={"User-Agent": "youtube-auto/1.0"})
    response.raise_for_status()
    if _looks_like_feed(response.headers.get("Content-Type", ""), response.text):
        try:
            ET.fromstring(response.content)
        except ET.ParseError:
            return fetch_items_from_html_url(source_url, limit=limit)
        return fetch_items_from_feed_url(source_url, limit=limit)
    return fetch_items_from_html_url(source_url, limit=limit)


def build_prompt(headlines: list[dict], today_label: str) -> str:
    headlines_json = json.dumps(headlines, indent=2)
    return f"""You are helping create a daily educational YouTube video about a current tech topic.

Today is {today_label}.

Below is a JSON array of recent headlines from the last day:
{headlines_json}

Choose ONE topic that is:
- current and newsworthy today
- understandable to a broad tech audience
- suitable for an educational explainer video
- not just stock-market chatter, gossip, or legal drama unless there is a strong product or AI angle

Return ONLY valid JSON with this exact shape:
{{
  "category": "ai",
  "headline": "Original selected headline",
  "source": "News source",
  "published_at": "ISO datetime string from the input if available",
  "video_topic": "Short clean topic title for the video",
  "video_summary": "2 to 3 sentence explanation of what happened and why it matters",
  "short_text": "1 to 2 short sentences for a vertical short",
  "points": ["point 1", "point 2", "point 3", "point 4"],
  "search_terms": "Pexels-friendly visual search terms",
  "topic_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}

Rules:
- category must be one of: ai, llm, rag, database, mcp
- video_topic must be under 70 characters
- video_summary should be concise, factual, and easy to narrate
- points must be short spoken-friendly learning points
- short_text should be punchy but not clickbait
- topic_tags must be lowercase
- if the topic is general AI news, prefer category "ai"
"""


def choose_topic_with_gemini(headlines: list[dict]) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    today_label = datetime.now(LOCAL_TZ).strftime("%B %d, %Y")
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=build_prompt(headlines, today_label),
    )
    raw = (response.text or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 3:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
    data = json.loads(raw.strip())
    return data


def choose_manual_topic_with_gemini(source_topic: str, source_text: str, source_notes: str) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    today_label = datetime.now(LOCAL_TZ).strftime("%B %d, %Y")
    response = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=build_manual_topic_prompt(source_topic, source_text, source_notes, today_label),
    )
    raw = (response.text or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 3:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
    return json.loads(raw.strip())


def fallback_topic(headlines: list[dict]) -> dict:
    chosen = headlines[0]
    title = chosen["title"]
    clean_topic = re.sub(r"\s*\|\s*.*$", "", title).strip()
    return {
        "category": "ai",
        "headline": title,
        "source": chosen.get("source", ""),
        "published_at": chosen.get("published_at", ""),
        "video_topic": clean_topic[:68],
        "video_summary": normalize_sentence(
            f"{clean_topic} is one of today's major AI stories. "
            "In this video, we break down what happened and why it matters."
        ),
        "short_text": normalize_sentence(
            f"Big AI update today: {clean_topic}. Here's why people are talking about it."
        ),
        "points": [
            "What happened in the story",
            "Why the update matters now",
            "Who is affected by the change",
            "What to watch next",
        ],
        "search_terms": "artificial intelligence technology innovation news",
        "topic_tags": ["ai", "tech news", "today", "artificial intelligence", "explainer"],
    }


def fallback_manual_topic(source_topic: str, source_text: str, source_notes: str) -> dict:
    merged = normalize_sentence(" ".join(part for part in [source_text, source_notes] if part))
    return {
        "category": "ai",
        "headline": source_topic,
        "source": "manual_input",
        "published_at": datetime.now(LOCAL_TZ).isoformat(),
        "video_topic": source_topic[:68],
        "video_summary": merged or normalize_sentence(f"{source_topic} is today's topic. In this video, we explain what it means and why it matters."),
        "short_text": normalize_sentence(f"{source_topic}. Here's the quick version and why it matters."),
        "points": [
            "What the topic is about",
            "Why people are paying attention",
            "What the main takeaway is",
            "What to watch next",
        ],
        "search_terms": "artificial intelligence technology software innovation",
        "topic_tags": ["ai", "technology", "explainer", "news", "software"],
    }


def normalize_topic_package(data: dict) -> dict:
    category = data.get("category", "ai").lower()
    if category not in {"ai", "llm", "rag", "database", "mcp"}:
        category = "ai"

    video_topic = (data.get("video_topic") or "Latest AI Topic").strip()
    summary = normalize_sentence(data.get("video_summary") or "")
    short_text = normalize_sentence(data.get("short_text") or summary)
    points = [normalize_sentence(p) for p in data.get("points", []) if p]
    if not points:
        points = [
            "What happened today.",
            "Why this matters.",
            "What could happen next.",
        ]

    topic_slug = slugify(video_topic)
    package = {
        "category": category,
        "video_topic": video_topic,
        "topic_slug": topic_slug,
        "headline": (data.get("headline") or video_topic).strip(),
        "source": (data.get("source") or "").strip(),
        "published_at": (data.get("published_at") or "").strip(),
        "video_summary": summary,
        "short_text": short_text,
        "points": points[:5],
        "search_terms": (data.get("search_terms") or video_topic).strip(),
        "topic_tags": [str(t).strip().lower() for t in data.get("topic_tags", []) if str(t).strip()][:8],
    }
    package["creator_config"] = {
        category: {
            "items": [
                {
                    "name": video_topic,
                    "explanation": summary,
                    "points": package["points"],
                    "fact": short_text,
                    "search_terms": package["search_terms"],
                    "headline": package["headline"],
                    "source": package["source"],
                    "published_at": package["published_at"],
                }
            ]
        }
    }
    return package


def write_outputs(output_path: str, topic: dict):
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if not github_output:
        return
    values = {
        "config_path": output_path,
        "topic_name": topic["video_topic"],
        "topic_slug": topic["topic_slug"],
        "topic_category": topic["category"],
        "topic_headline": topic["headline"],
        "topic_source": topic["source"],
        "topic_summary": topic["video_summary"],
        "topic_origin_url": topic.get("origin_url", ""),
    }
    with open(github_output, "a", encoding="utf-8") as fh:
        for key, value in values.items():
            safe = str(value).replace("\n", " ").strip()
            fh.write(f"{key}={safe}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate today's latest-topic config package.")
    parser.add_argument("--source-topic", default="", help="Manual topic input for today's video")
    parser.add_argument("--source-text", default="", help="Manual source text to convert into a video")
    parser.add_argument("--source-notes", default="", help="Optional extra notes/context for the manual topic")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Google News RSS search query")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL, help="Optional public source URL or feed to use as the primary topic source")
    parser.add_argument("--limit", type=int, default=12, help="Max headlines to analyze")
    parser.add_argument(
        "--output",
        default="generated/latest_topic_package.json",
        help="Where to write the generated config package",
    )
    args = parser.parse_args()

    headlines = []
    manual_mode = bool(args.source_topic.strip())
    if manual_mode:
        headlines = build_manual_items(args.source_topic, args.source_notes)
        print("✍️  Using manual topic input from workflow.")
    elif args.source_url:
        try:
            headlines = fetch_items_from_source_url(args.source_url, limit=args.limit)
            print(f"🔎  Fetched {len(headlines)} recent items from source URL.")
        except Exception as e:
            print(f"⚠️   Source URL fetch failed: {e}")
            print("     Falling back to Google News RSS.")

    if not headlines:
        try:
            headlines = fetch_recent_headlines(args.query, limit=args.limit)
            print(f"📰  Fetched {len(headlines)} recent headlines from Google News.")
        except Exception as e:
            print(f"❌  Failed to fetch headlines: {e}")
            sys.exit(1)

    if not headlines:
        print("❌  No recent headlines found.")
        sys.exit(1)
    try:
        if manual_mode:
            raw_topic = choose_manual_topic_with_gemini(
                args.source_topic.strip(),
                args.source_text.strip(),
                args.source_notes.strip(),
            )
            print("🤖  Gemini built the manual topic package.")
        else:
            raw_topic = choose_topic_with_gemini(headlines)
            print("🤖  Gemini selected today's topic.")
    except Exception as e:
        print(f"⚠️   Gemini topic selection failed: {e}")
        if manual_mode:
            print("     Falling back to a local manual package.")
            raw_topic = fallback_manual_topic(
                args.source_topic.strip(),
                args.source_text.strip(),
                args.source_notes.strip(),
            )
        else:
            print("     Falling back to the top headline.")
            raw_topic = fallback_topic(headlines)

    topic = normalize_topic_package(raw_topic)
    topic["origin_url"] = args.source_url or ""
    output_path = os.path.abspath(args.output)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(topic["creator_config"], fh, indent=2)

    write_outputs(output_path, topic)

    print("\n✅  Latest topic package ready")
    print(f"    Topic    : {topic['video_topic']}")
    print(f"    Category : {topic['category']}")
    print(f"    Headline : {topic['headline']}")
    if topic["source"]:
        print(f"    Source   : {topic['source']}")
    print(f"    Config   : {output_path}")


if __name__ == "__main__":
    main()
