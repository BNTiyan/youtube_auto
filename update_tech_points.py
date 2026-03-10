#!/usr/bin/env python3
"""
Generates unique, educational 5-point explanations for every item in
tech_content_config.json using Gemini API with batch processing and
progress checkpointing so runs can be resumed if interrupted.

Usage:
    GEMINI_API_KEY=your_key python3 update_tech_points.py

The updated config is written to tech_content_config.json in-place.
A checkpoint file (.update_progress.json) tracks completed items so
the script can safely be re-run after interruption.
"""

import json
import os
import sys
import time
from pathlib import Path

# ── config ─────────────────────────────────────────────────────────────────
CONFIG_FILE     = Path(__file__).parent / "tech_content_config.json"
CHECKPOINT_FILE = Path(__file__).parent / ".update_progress.json"
BATCH_SIZE      = 10        # items per Gemini request
RETRY_DELAY     = 5         # seconds between retries on rate-limit
MAX_RETRIES     = 3
MODEL           = "gemini-2.0-flash"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    sys.exit("❌  Set GEMINI_API_KEY in your environment before running.")

from google import genai  # noqa: E402

client = genai.Client(api_key=GEMINI_API_KEY)


# ── helpers ─────────────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(checkpoint: dict):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f)


def build_prompt(items: list[dict]) -> str:
    """
    Build a Gemini prompt that returns exactly 5 unique educational bullet
    points for each item in the batch.
    """
    lines = ["Return a JSON array. Each element must have exactly these keys:"]
    lines.append('  "name"   – the item name (copy verbatim from input)')
    lines.append('  "points" – an array of EXACTLY 5 strings')
    lines.append("")
    lines.append("Rules for every point string:")
    lines.append("  • Specific and educational – no generic filler phrases.")
    lines.append("  • Each point teaches ONE distinct, concrete fact about the topic.")
    lines.append("  • Written in plain English, max ~18 words per point.")
    lines.append("  • Do NOT start any point with 'Core concept', 'Important for',")
    lines.append("    'Commonly applied', 'Often combined', or 'Key knowledge area'.")
    lines.append("  • Points must differ from each other within the same item.")
    lines.append("")
    lines.append("Items to process:")
    for item in items:
        lines.append(f"  name: {item['name']}")
        lines.append(f"  explanation: {item['explanation']}")
        lines.append("")
    lines.append("Return ONLY the JSON array, no markdown, no extra text.")
    return "\n".join(lines)


def call_gemini(prompt: str) -> list[dict]:
    """Call Gemini and parse the returned JSON array."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            raw = response.text.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]
            return json.loads(raw.strip())
        except Exception as exc:
            print(f"  ⚠  Attempt {attempt}/{MAX_RETRIES} failed: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
    raise RuntimeError("All retries exhausted for a batch.")


def process_batch(batch: list[dict], topic: str, checkpoint: dict) -> list[dict]:
    """
    Process a batch of items. Skip items already in checkpoint.
    Returns updated items with new points.
    """
    to_fetch = [item for item in batch
                if f"{topic}/{item['name']}" not in checkpoint]
    already_done = [item for item in batch
                    if f"{topic}/{item['name']}" in checkpoint]

    results = {}
    for item in already_done:
        results[item["name"]] = checkpoint[f"{topic}/{item['name']}"]

    if to_fetch:
        prompt = build_prompt(to_fetch)
        generated = call_gemini(prompt)
        for entry in generated:
            name = entry["name"]
            pts  = entry["points"]
            results[name] = pts
            checkpoint[f"{topic}/{name}"] = pts

    # Return items in original order with updated points
    updated = []
    for item in batch:
        new_item = dict(item)
        if item["name"] in results:
            new_item["points"] = results[item["name"]]
        updated.append(new_item)
    return updated


# ── main ────────────────────────────────────────────────────────────────────

def main():
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    checkpoint = load_checkpoint()

    total_topics = len(config)
    for topic_idx, (topic, content) in enumerate(config.items(), 1):
        items = content["items"]
        total_items = len(items)
        print(f"\n[{topic_idx}/{total_topics}] Topic: {topic!r}  ({total_items} items)")

        updated_items = []
        for batch_start in range(0, total_items, BATCH_SIZE):
            batch = items[batch_start: batch_start + BATCH_SIZE]
            batch_end = min(batch_start + BATCH_SIZE, total_items)

            already_count = sum(
                1 for item in batch
                if f"{topic}/{item['name']}" in checkpoint
            )
            if already_count == len(batch):
                print(f"  ✔  Items {batch_start+1}–{batch_end} already done, skipping")
                updated = process_batch(batch, topic, checkpoint)
            else:
                print(f"  →  Generating points for items {batch_start+1}–{batch_end} …",
                      end=" ", flush=True)
                updated = process_batch(batch, topic, checkpoint)
                save_checkpoint(checkpoint)
                print("saved ✔")

            updated_items.extend(updated)

        config[topic]["items"] = updated_items

    # Write final result
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    # Clean up checkpoint
    CHECKPOINT_FILE.unlink(missing_ok=True)
    print(f"\n✅  Done! Updated {CONFIG_FILE}")


if __name__ == "__main__":
    main()
