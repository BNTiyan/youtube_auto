#!/usr/bin/env python3
"""
Daily Item Picker — selects ONE item per day using a flat rotation across all categories.

Usage (local):
    python pick_item.py --config content_config.json
    python pick_item.py --config tech_content_config.json --field explanation
    python pick_item.py --config content_config.json --category animals

In GitHub Actions the outputs are written to $GITHUB_OUTPUT automatically.
Outputs: category, name, text, slug, index, total
"""

import os
import json
import argparse
from datetime import datetime


def pick_today(config: dict, field: str = "fact", category_filter: str = "") -> dict:
    """
    Flatten all items across categories, optionally filter to one category,
    then select today's item by (day_of_year - 1) % total.
    """
    all_items = []
    for cat, data in config.items():
        if category_filter and cat != category_filter:
            continue
        for item in data.get("items", []):
            # Support both 'fact' (kids) and 'explanation' (tech) fields
            text = item.get(field) or item.get("fact") or item.get("explanation") or ""
            all_items.append({"category": cat, "name": item["name"], "text": text})

    if not all_items:
        raise ValueError(
            f"No items found. Config has categories: {list(config.keys())} "
            f"(filter={category_filter!r})"
        )

    doy = datetime.now().timetuple().tm_yday
    idx = (doy - 1) % len(all_items)
    chosen = dict(all_items[idx])   # copy so we can add metadata

    # Slug: lowercase name, spaces/hyphens → underscores
    chosen["slug"]  = chosen["name"].lower().replace(" ", "_").replace("-", "_")
    chosen["index"] = idx
    chosen["total"] = len(all_items)
    chosen["day"]   = doy
    return chosen


def main():
    parser = argparse.ArgumentParser(
        description="Pick today's single item for a daily educational video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pick_item.py --config content_config.json
  python pick_item.py --config tech_content_config.json --field explanation
  python pick_item.py --config content_config.json --category animals
        """,
    )
    parser.add_argument("--config",   default="content_config.json",
                        help="JSON content config (default: content_config.json)")
    parser.add_argument("--field",    default="fact",
                        help="Item text field to extract: fact (kids) or explanation (tech)")
    parser.add_argument("--category", default="",
                        help="Limit rotation to this category only (optional)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"❌  Config not found: {args.config}")
        raise SystemExit(1)

    with open(args.config) as f:
        config = json.load(f)

    item = pick_today(config, field=args.field, category_filter=args.category)

    print(f"📅  Day {item['day']} → slot #{item['index'] + 1} of {item['total']}")
    print(f"📂  Category : {item['category']}")
    print(f"🏷️   Name     : {item['name']}")
    print(f"💬  Text     : {item['text']}")
    print(f"📄  Slug     : {item['slug']}")

    # ── Write to GitHub Actions output file ──────────────────────────────────
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a") as f:
            for key in ("category", "name", "text", "slug"):
                # Sanitise: collapse any embedded newlines so the GITHUB_OUTPUT
                # key=value format stays on a single line.
                val = str(item[key]).replace("\n", " ").replace("\r", "")
                f.write(f"{key}={val}\n")
            f.write(f"index={item['index']}\n")
            f.write(f"total={item['total']}\n")
        print("✅  Outputs written to $GITHUB_OUTPUT")


if __name__ == "__main__":
    main()
