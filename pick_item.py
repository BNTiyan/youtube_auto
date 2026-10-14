#!/usr/bin/env python3
"""
Daily Item Picker — selects ONE item per day using a flat rotation across all categories.

Usage (local):
    python pick_item.py --config content_config
    python pick_item.py --config tech_content_config --field explanation
    python pick_item.py --config content_config --category animals

In GitHub Actions the outputs are written to $GITHUB_OUTPUT automatically.
Outputs: category, name, text, slug, index, total
"""

from filename_utils import video_slug
import os
import json
import argparse
from datetime import datetime


def generate_fallback_metadata(name: str, category: str, text: str, points: list) -> dict:
    """
    Generate high-quality metadata from local JSON data.
    """
    clean_name = name.strip()
    clean_cat = category.strip().capitalize()
    
    title = f"All About {clean_name} | {clean_cat} Learning"
    
    description = f"{text}\n\n"
    if points:
        description += "Key learning points:\n"
        for p in points:
            description += f"• {p}\n"
    
    # Generic but relevant tags
    tags = [clean_name.lower(), clean_cat.lower(), "learning", "education", "facts", "youtube"]
    
    # Add hashtags to description
    description += f"\n#Youtube #Learning #Education #{clean_name.replace(' ', '')} #{clean_cat.replace(' ', '')}"
    
    return {
        "title": title,
        "description": description,
        "tags": ",".join(tags)
    }


def pick_today(config_dir: str, field: str = "fact", category_filter: str = "") -> dict:
    """
    Pick ONE json from folders and fetch data from that.
    Picks files sequentially based on alphabetical sorting.
    """
    import glob
    json_files = sorted(glob.glob(os.path.join(config_dir, "*.json")))
    if not json_files:
        raise ValueError(f"No JSON files found in {config_dir}")

    state_file = os.path.join(config_dir, ".pick_state.json")
    state = {"file_idx": 0, "file_item_idx": {}}
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
        except Exception:
            pass

    # If category filter is provided, find that specific file
    if category_filter:
        target_file = None
        for jf in json_files:
            if os.path.basename(jf).replace(".json", "") == category_filter:
                target_file = jf
                break
        if not target_file:
            raise ValueError(f"Category {category_filter} not found in {config_dir}")
        selected_file = target_file
    else:
        # Pick next file sequentially
        file_idx = state.get("file_idx", 0) % len(json_files)
        selected_file = json_files[file_idx]
        state["file_idx"] = (file_idx + 1) % len(json_files)

    cat = os.path.basename(selected_file).replace(".json", "")
    
    with open(selected_file) as f:
        config_data = json.load(f)

    # Normalize to list of items
    all_items = []
    if isinstance(config_data, dict) and config_data and isinstance(next(iter(config_data.values())), dict):
        # New format: {"Lion": {"explanation": "...", "points": [...]}}
        for k, v in config_data.items():
            item = {"name": k}
            item.update(v)
            all_items.append(item)
    elif "items" in config_data:
        all_items = config_data["items"]
    elif isinstance(config_data, dict) and len(config_data) > 0 and "items" in next(iter(config_data.values())):
        all_items = next(iter(config_data.values()))["items"]
    else:
        all_items = config_data if isinstance(config_data, list) else []
        
    if not all_items:
        raise ValueError(f"No items found in {selected_file}")

    # Sort items alphabetically by name
    all_items.sort(key=lambda x: x["name"])

    # Pick item sequentially from this file
    item_idx = state["file_item_idx"].get(cat, 0) % len(all_items)
    state["file_item_idx"][cat] = (item_idx + 1) % len(all_items)

    try:
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

    raw_item = all_items[item_idx]
    text = raw_item.get(field) or raw_item.get("fact") or raw_item.get("explanation") or ""
    points = raw_item.get("points", [])
    
    chosen = {"category": cat, "name": raw_item["name"], "text": text}
    
    # Generate fallback metadata fields
    fallback = generate_fallback_metadata(chosen["name"], chosen["category"], chosen["text"], points)
    chosen.update(fallback)

    # Slug: lowercase name, spaces/hyphens → underscores
    chosen["slug"]  = video_slug(chosen["name"])
    chosen["index"] = item_idx
    chosen["total"] = len(all_items)
    chosen["day"]   = datetime.now().timetuple().tm_yday
    return chosen


def main():
    parser = argparse.ArgumentParser(
        description="Pick today's single item for a daily educational video",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pick_item.py --config content_config
  python pick_item.py --config tech_content_config --field explanation
  python pick_item.py --config content_config --category animals
        """,
    )
    parser.add_argument("--config",   default="content_config",
                        help="Path to content config directory (default: content_config)")
    parser.add_argument("--field",    default="fact",
                        help="Item text field to extract: fact (kids) or explanation (tech)")
    parser.add_argument("--category", default="",
                        help="Limit rotation to this category only (optional)")
    args = parser.parse_args()

    if not os.path.exists(args.config) and not os.path.isdir(args.config):
        print(f"❌  Config directory not found: {args.config}")
        raise SystemExit(1)

    item = pick_today(args.config, field=args.field, category_filter=args.category)

    print(f"📅  Day {item['day']} → slot #{item['index'] + 1} of {item['total']}")
    print(f"📂  Category : {item['category']}")
    print(f"🏷️   Name     : {item['name']}")
    print(f"💬  Text     : {item['text']}")
    print(f"📄  Slug     : {item['slug']}")

    # ── Write to GitHub Actions output file ──────────────────────────────────
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a") as f:
            for key in ("category", "name", "text", "slug", "title", "description", "tags"):
                # Sanitise: collapse any embedded newlines so the GITHUB_OUTPUT
                # key=value format stays on a single line.
                val = str(item[key]).replace("\n", " ").replace("\r", "")
                f.write(f"{key}={val}\n")
            f.write(f"index={item['index']}\n")
            f.write(f"total={item['total']}\n")
        print("✅  Outputs written to $GITHUB_OUTPUT")


if __name__ == "__main__":
    main()
