#!/usr/bin/env python3
"""
Kids' Learning Video Creator
Generates educational slideshow videos with real images + text-to-speech narration.

Images are fetched from the Pexels API (free).
Set PEXELS_API_KEY environment variable to enable images.
Without the key, slides fall back to a clean coloured text-only design.

Usage:
    python video_creator.py animals                  # one category
    python video_creator.py all                      # all 6 categories
    python video_creator.py fruits --items 5         # first 5 items
    python video_creator.py all --no-images          # skip image fetching
"""

import os
import json
import argparse
import textwrap
import tempfile
import random
import glob
import shutil
from io import BytesIO
from typing import Optional

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from animation_utils import build_animated_clip
from tts_utils import create_kids_tts

# ── moviepy v1 / v2 compat ────────────────────────────────────────────────────
try:
    from moviepy.editor import AudioFileClip, concatenate_videoclips
except (ImportError, ModuleNotFoundError):
    from moviepy import AudioFileClip, concatenate_videoclips


def _set_audio(clip, audio):
    try:
        return clip.set_audio(audio)
    except AttributeError:
        return clip.with_audio(audio)


# ── CONFIG ────────────────────────────────────────────────────────────────────
WIDTH, HEIGHT      = 1280, 720
FPS                = 24
PAUSE_AFTER_AUDIO  = 0.8
MIN_SLIDE_DURATION = 4.0

IMAGE_H = 420          # photo occupies top IMAGE_H pixels
TEXT_H  = HEIGHT - IMAGE_H   # = 300 px text band at bottom
GRAD_H  = 90           # gradient blend zone at bottom of photo

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# Extra search words appended to item name per category
CATEGORY_SEARCH_SUFFIX = {
    "animals":    "animal wildlife nature",
    "fruits":     "fruit fresh food",
    "vegetables": "vegetable fresh food",
    "cars":       "car automobile",
    "airplanes":  "airplane aircraft aviation",
    "brands":     "brand store logo",
}

# ── COLOUR THEMES ─────────────────────────────────────────────────────────────
THEMES = {
    "animals":    {"bg": (22, 78, 22),   "card": (46, 120, 46),   "accent": (144, 238, 144), "text": (255, 255, 255)},
    "fruits":     {"bg": (180, 70,  0),  "card": (230, 110,  0),  "accent": (255, 224, 130), "text": (255, 255, 255)},
    "vegetables": {"bg": (20, 80, 25),   "card": (40, 120, 50),   "accent": (165, 214, 167), "text": (255, 255, 255)},
    "cars":       {"bg": (130, 15, 15),  "card": (190, 40, 40),   "accent": (255, 160, 122), "text": (255, 255, 255)},
    "airplanes":  {"bg": (10, 50, 120),  "card": (20, 90, 180),   "accent": (144, 202, 249), "text": (255, 255, 255)},
    "brands":     {"bg": (60, 10, 110),  "card": (100, 30, 160),  "accent": (206, 147, 216), "text": (255, 255, 255)},
}
DEFAULT_THEME = {"bg": (30, 30, 30), "card": (60, 60, 60), "accent": (200, 200, 200), "text": (255, 255, 255)}

# ── FONTS ─────────────────────────────────────────────────────────────────────
_FONT_CACHE: dict = {}
_FONT_PATHS = [
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/mnt/c/Windows/Fonts/arialbd.ttf",
    "/mnt/c/Windows/Fonts/arial.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def _draw_text_centered(draw, text: str, font, y: int, fill, shadow=(0, 0, 0)):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (WIDTH - tw) // 2
    draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


# ── PEXELS IMAGE FETCH ────────────────────────────────────────────────────────
_img_cache: dict = {}


def fetch_pexels_image(query: str) -> Optional[Image.Image]:
    """
    Search Pexels for `query` and return a PIL Image (landscape).
    Returns None if API key missing, network error, or no results.
    """
    if not PEXELS_API_KEY:
        return None
    if query in _img_cache:
        return _img_cache[query]

    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 3, "orientation": "landscape"},
            timeout=10,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            # Retry without orientation filter (helps for subjects like hummingbirds
            # where landscape shots are rare on Pexels)
            resp2 = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": query, "per_page": 3},
                timeout=10,
            )
            resp2.raise_for_status()
            photos = resp2.json().get("photos", [])
        if not photos:
            _img_cache[query] = None
            return None

        src = photos[0]["src"]
        url = src.get("large2x") or src.get("large")
        img_resp = requests.get(url, timeout=15)
        img_resp.raise_for_status()
        img = Image.open(BytesIO(img_resp.content)).convert("RGB")
        _img_cache[query] = img
        return img

    except Exception as e:
        print(f"    ⚠️   Pexels fetch failed ({query}): {e}")
        _img_cache[query] = None
        return None


def get_item_image(name: str, category: str) -> Optional[Image.Image]:
    suffix = CATEGORY_SEARCH_SUFFIX.get(category, "")
    return fetch_pexels_image(f"{name} {suffix}".strip())


# ── IMAGE + TEXT SLIDE COMPOSITING ────────────────────────────────────────────

def _gradient_blend(base: Image.Image, start_y: int, end_y: int,
                    target_rgb: tuple) -> Image.Image:
    """Blend rows [start_y, end_y) smoothly from photo pixels → target_rgb."""
    arr = np.array(base, dtype=np.float32)
    tc  = np.array(target_rgb, dtype=np.float32)
    h   = end_y - start_y
    for i in range(h):
        alpha   = (i / h) ** 1.4       # ease-in curve: slow start, fast end
        arr[start_y + i] = arr[start_y + i] * (1 - alpha) + tc * alpha
    return Image.fromarray(arr.astype(np.uint8))


def _dot_pattern(draw, theme: dict):
    for x in range(0, WIDTH, 72):
        for y in range(0, HEIGHT, 72):
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=theme["card"])


# ── SLIDE CREATION ────────────────────────────────────────────────────────────

def create_slide(
    title: str,
    fact: str,
    theme: dict,
    counter: str = "",
    image: Optional[Image.Image] = None,
) -> np.ndarray:
    """Return a 1280×720 numpy array slide."""

    base = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])

    if image is not None:
        # ══ PHOTO + TEXT LAYOUT ══════════════════════════════════════════════
        #   [  photo fills top IMAGE_H px, full width              ]
        #   [ gradient blend to card colour at bottom of photo      ]
        #   [  card-coloured text band (TEXT_H px)                  ]
        #   [    large title + fact wrapped across 2 lines           ]

        # 1. Smart crop: fill width, keep centre of height
        img_w, img_h = image.size
        scale = max(WIDTH / img_w, IMAGE_H / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        img_scaled = image.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - WIDTH) // 2
        top  = (new_h - IMAGE_H) // 2
        img_cropped = img_scaled.crop((left, top, left + WIDTH, top + IMAGE_H))
        base.paste(img_cropped, (0, 0))

        # 2. Gradient from photo → card colour in bottom GRAD_H rows of photo
        base = _gradient_blend(base,
                               start_y=IMAGE_H - GRAD_H,
                               end_y=IMAGE_H,
                               target_rgb=theme["card"])

        draw = ImageDraw.Draw(base)

        # 3. Text area solid fill
        draw.rectangle([0, IMAGE_H, WIDTH, HEIGHT], fill=theme["card"])

        # 4. Accent separator line
        draw.rectangle([0, IMAGE_H, WIDTH, IMAGE_H + 5], fill=theme["accent"])

        # 5. Counter pill (top-right corner over the photo)
        if counter:
            cf = load_font(28)
            bbox = draw.textbbox((0, 0), counter, font=cf)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad = 10
            rx1, ry1 = WIDTH - tw - pad * 2 - 18, 14
            rx2, ry2 = rx1 + tw + pad * 2, ry1 + th + pad * 2
            draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=16, fill=(0, 0, 0))
            draw.text((rx1 + pad, ry1 + pad), counter, font=cf, fill=theme["accent"])

        # 6. Title
        title_font = load_font(80)
        _draw_text_centered(draw, title, title_font, IMAGE_H + 18, theme["text"])

        # 7. Fact (max 2 wrapped lines)
        fact_font = load_font(36)
        wrapped = textwrap.wrap(fact, width=60)
        y_pos = IMAGE_H + 118
        for line in wrapped[:2]:
            bbox = draw.textbbox((0, 0), line, font=fact_font)
            draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, y_pos),
                      line, font=fact_font, fill=theme["accent"])
            y_pos += 54

    else:
        # ══ TEXT-ONLY FALLBACK ═══════════════════════════════════════════════
        draw = ImageDraw.Draw(base)
        _dot_pattern(draw, theme)
        margin = 60
        draw.rectangle([margin, margin, WIDTH - margin, HEIGHT - margin], fill=theme["card"])
        draw.rectangle([margin, margin, WIDTH - margin, HEIGHT - margin],
                       outline=theme["accent"], width=4)

        if counter:
            sf = load_font(30)
            bbox = draw.textbbox((0, 0), counter, font=sf)
            draw.text((WIDTH - margin - (bbox[2] - bbox[0]) - 20, margin + 18),
                      counter, font=sf, fill=theme["accent"])

        _draw_text_centered(draw, title, load_font(96), HEIGHT // 2 - 115, theme["text"])
        draw.line([margin + 80, HEIGHT // 2 - 8, WIDTH - margin - 80, HEIGHT // 2 - 8],
                  fill=theme["accent"], width=3)

        y_pos = HEIGHT // 2 + 18
        for line in textwrap.wrap(fact, width=58)[:3]:
            bbox = draw.textbbox((0, 0), line, font=load_font(38))
            draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, y_pos),
                      line, font=load_font(38), fill=theme["accent"])
            y_pos += 50

    return np.array(base)


def create_intro_slide(category: str, total: int, theme: dict,
                       image: Optional[Image.Image] = None) -> np.ndarray:
    return create_slide(
        title=f"Learn {category.capitalize()}!",
        fact=f"Discover {total} amazing {category} today",
        theme=theme,
        image=image,
    )


def create_outro_slide(category: str, theme: dict) -> np.ndarray:
    return create_slide(           # outro is always text-only
        title="Great Job! ⭐",
        fact=f"You learned about {category}! Come back tomorrow for more!",
        theme=theme,
    )


# ── SINGLE-ITEM VIDEO ─────────────────────────────────────────────────────────

def create_single_item_video(
    category: str,
    item: dict,
    output_path: str,
    lang: str = "en",
    use_images: bool = True,
) -> str:
    """
    Generate a short (~30-45 sec) video for ONE item only.
    Structure: intro slide → main content slide → outro slide.
    """
    theme = THEMES.get(category.lower(), DEFAULT_THEME)
    name  = item["name"]
    fact  = item.get("fact", f"{name} is really amazing!")
    clips = []

    with tempfile.TemporaryDirectory() as tmp:

        # Fetch image once and reuse across slides
        item_img = None
        if use_images:
            print(f"  🖼️  Fetching image for {name}...")
            item_img = get_item_image(name, category)

        # ── Intro slide ──────────────────────────────────────────────────────
        print("  Creating intro slide...")
        intro_slide = create_slide(
            title=f"Today: {name}!",
            fact=f"A fun {category} fact just for you!",
            theme=theme,
            image=item_img,
        )
        intro_mp3 = os.path.join(tmp, "intro.mp3")
        create_tts(f"Hello friends! Today we are going to learn about {name}!", intro_mp3, lang)
        clips.append(make_clip(intro_slide, intro_mp3, animate=(item_img is not None)))

        # ── Main content slide ────────────────────────────────────────────────
        print("  Creating main slide...")
        main_slide = create_slide(
            title=name,
            fact=fact,
            theme=theme,
            image=item_img,
        )
        main_mp3 = os.path.join(tmp, "main.mp3")
        create_tts(f"{name}. {fact}", main_mp3, lang)
        clips.append(make_clip(main_slide, main_mp3, animate=(item_img is not None)))

        # ── Outro slide ───────────────────────────────────────────────────────
        print("  Creating outro slide...")
        outro_slide = create_outro_slide(category, theme)
        outro_mp3   = os.path.join(tmp, "outro.mp3")
        create_tts(
            f"Great job! Now you know about {name}! Come back tomorrow for another fun fact!",
            outro_mp3, lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3, animate=False))

        # ── Render ────────────────────────────────────────────────────────────
        print(f"\n  Rendering → {output_path}")
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Robustness: Remove if it mistakenly exists as a directory
        if os.path.isdir(output_path):
            print(f"  ⚠️   Removing erroneous directory at output path: {output_path}")
            shutil.rmtree(output_path)
            
        try:
            final.write_videofile(output_path, fps=FPS, codec="libx264",
                                  audio_codec="aac", logger=None)
        except TypeError:
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            final.close()
        except Exception:
            pass

    return output_path


def create_tts(text: str, out_path: str, lang: str = "en") -> None:
    create_kids_tts(text, out_path, lang)


# ── CLIP ASSEMBLY ─────────────────────────────────────────────────────────────

def make_clip(slide: np.ndarray, audio_path: str, animate: bool = False):
    """
    Build a single slide video clip.

    animate=True  → Ken Burns slow-zoom + fade-in  (use for photo slides)
    animate=False → static image + fade-in          (use for text-only slides)
    """
    audio    = AudioFileClip(audio_path)
    duration = max(audio.duration + PAUSE_AFTER_AUDIO, MIN_SLIDE_DURATION)
    clip = build_animated_clip(
        slide,
        duration=duration,
        animate=animate,
        zoom_ratio=0.06,
        pan_pixels=20,
        fadein_duration=0.30,
    )
    return _set_audio(clip, audio)


# ── MAIN VIDEO BUILDER ────────────────────────────────────────────────────────

def create_kids_video(
    category: str,
    items: list,
    output_path: str,
    lang: str = "en",
    use_images: bool = True,
) -> str:
    theme = THEMES.get(category.lower(), DEFAULT_THEME)
    total = len(items)
    clips = []

    with tempfile.TemporaryDirectory() as tmp:

        # ── Intro ──
        print("  Creating intro...")
        intro_img = None
        if use_images:
            suffix = CATEGORY_SEARCH_SUFFIX.get(category, "")
            intro_img = fetch_pexels_image(f"{category} {suffix} collection")
        intro_slide = create_intro_slide(category, total, theme, image=intro_img)
        intro_mp3   = os.path.join(tmp, "intro.mp3")
        create_tts(f"Hello friends! Let's learn about {category}! Get ready!", intro_mp3, lang)
        clips.append(make_clip(intro_slide, intro_mp3, animate=(intro_img is not None)))

        # ── Item slides ──
        for i, item in enumerate(items, 1):
            name    = item["name"]
            fact    = item.get("fact", f"{name} is really amazing!")
            counter = f"{i} of {total}"

            print(f"  [{i}/{total}] {name}", end="", flush=True)
            item_img = None
            if use_images:
                item_img = get_item_image(name, category)
                print(f"  {'🖼️ ' if item_img else '📝 '}", end="")
            print()

            slide    = create_slide(title=name, fact=fact, theme=theme,
                                    counter=counter, image=item_img)
            mp3_path = os.path.join(tmp, f"item_{i}.mp3")
            create_tts(f"{name}. {fact}", mp3_path, lang)
            clips.append(make_clip(slide, mp3_path, animate=(item_img is not None)))

        # ── Outro ──
        print("  Creating outro...")
        outro_slide = create_outro_slide(category, theme)
        outro_mp3   = os.path.join(tmp, "outro.mp3")
        create_tts(
            f"Amazing work! You learned about {total} {category}! Come back tomorrow for more!",
            outro_mp3, lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3, animate=False))

        # ── Render ──
        print(f"\n  Rendering → {output_path}")
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            final.write_videofile(output_path, fps=FPS, codec="libx264",
                                  audio_codec="aac", logger=None)
        except TypeError:
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            final.close()
        except Exception:
            pass

    return output_path


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create kids' learning videos with Pexels images + TTS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python video_creator.py animals                  # whole category (10 slides)
  python video_creator.py all                      # all 6 categories
  python video_creator.py fruits --items 5         # first 5 items
  python video_creator.py all --no-images          # text-only, no Pexels key needed

  # ── Single-item mode (daily pipeline) ──────────────────────────────────────
  python video_creator.py --item Lion    --cat animals   # one item, ~30-45 sec
  python video_creator.py --item Ferrari --cat cars
        """,
    )
    # Positional (legacy whole-category mode)
    parser.add_argument("category", nargs="?", default=None,
                        help="Category name or 'all' — omit when using --item/--cat")
    # Single-item mode
    parser.add_argument("--item",       default=None,
                        help="Single item name, e.g. 'Lion'  (enables single-item mode)")
    parser.add_argument("--cat",        default=None,
                        help="Category for --item, e.g. 'animals'")
    # Common options
    parser.add_argument("--config",     default="content_config")
    parser.add_argument("--output-dir", default="videos")
    parser.add_argument("--lang",       default="en")
    parser.add_argument("--items",      type=int, default=0,
                        help="Limit items per category (whole-category mode only)")
    parser.add_argument("--no-images",  action="store_true",
                        help="Disable Pexels image fetching (text-only slides)")
    args = parser.parse_args()

    use_images = not args.no_images
    if use_images and not PEXELS_API_KEY:
        print("⚠️   PEXELS_API_KEY not set — using text-only slides.")
        print("    Free key: https://www.pexels.com/api/\n")
        use_images = False

    config_path = args.config
    if os.path.isdir(args.config):
        if args.cat and os.path.exists(os.path.join(args.config, f"{args.cat}.json")):
            config_path = os.path.join(args.config, f"{args.cat}.json")
        else:
            json_files = sorted(glob.glob(os.path.join(args.config, "*.json")))
            if not json_files:
                print(f"❌  No JSON config files found in directory: {args.config}")
                return
            
            state_file = os.path.join(args.config, ".last_config_idx.txt")
            idx = 0
            if os.path.exists(state_file):
                try:
                    with open(state_file) as sf:
                        idx = (int(sf.read().strip()) + 1) % len(json_files)
                except Exception:
                    pass
            
            config_path = json_files[idx]
            try:
                with open(state_file, "w") as sf:
                    sf.write(str(idx))
            except Exception:
                pass
                
            print(f"🔄  Sequentially selected config: {os.path.basename(config_path)}")

    if not os.path.exists(config_path):
        print(f"❌  Config not found: {config_path}")
        return

    cat_from_file = os.path.basename(config_path).replace(".json", "")
    with open(config_path) as f:
        raw_config = json.load(f)

    # Normalize raw_config into the expected format { "category": { "items": [...] } }
    config = {}
    is_multi = False
    for k, v in raw_config.items():
        if isinstance(v, dict) and "items" in v:
            is_multi = True
            break

    if is_multi:
        config = raw_config
    else:
        items = []
        if isinstance(raw_config, dict) and raw_config and isinstance(next(iter(raw_config.values())), dict):
            # New format: {"Lion": {"explanation": "...", "points": [...]}}
            for name, data in raw_config.items():
                item = {"name": name}
                item.update(data)
                items.append(item)
        elif "items" in raw_config:
            items = raw_config["items"]
        elif isinstance(raw_config, dict) and raw_config and "items" in next(iter(raw_config.values())):
            items = next(iter(raw_config.values()))["items"]
        else:
            items = raw_config if isinstance(raw_config, list) else []
            
        config = {cat_from_file: {"items": sorted(items, key=lambda x: x.get("name", ""))}}

    # ── SINGLE-ITEM MODE ──────────────────────────────────────────────────────
    if args.item:
        if not args.cat:
            print("❌  --cat CATEGORY is required when using --item")
            return
        cat = args.cat.lower()
        if cat not in config:
            print(f"❌  Unknown category: {cat!r}. Available: {list(config.keys())}")
            return

        # Look up the item by name (case-insensitive); create stub if not found
        item_data = next(
            (it for it in config[cat]["items"]
             if it["name"].lower() == args.item.lower()),
            None,
        )
        if item_data is None:
            print(f"⚠️   Item {args.item!r} not found in '{cat}' config — using name only.")
            item_data = {"name": args.item, "fact": f"{args.item} is amazing!"}

        slug        = item_data["name"].lower().replace(" ", "_").replace("-", "_")
        output_path = os.path.join(args.output_dir, f"{slug}_learning.mp4")

        print("=" * 60)
        print("  🎬  Kids' Learning Video Creator — Single Item")
        print(f"  📂  Category : {cat}")
        print(f"  🏷️   Item     : {item_data['name']}")
        print(f"  {'🖼️   Images: Pexels API ✅' if use_images else '📝  Images: text-only mode'}")
        print("=" * 60)

        os.makedirs(args.output_dir, exist_ok=True)
        try:
            create_single_item_video(
                category=cat, item=item_data, output_path=output_path,
                lang=args.lang, use_images=use_images,
            )
            print(f"\n✅  Done: {output_path}")
        except Exception as e:
            import traceback
            print(f"❌  Failed: {e}")
            traceback.print_exc()
        return

    # ── WHOLE-CATEGORY MODE (original behaviour) ──────────────────────────────
    cat_arg  = args.category or "all"
    all_cats = list(config.keys()) + ["all"]
    if cat_arg not in all_cats:
        print(f"❌  Unknown category: {cat_arg!r}. Choose from: {all_cats}")
        return

    categories = list(config.keys()) if cat_arg == "all" else [cat_arg]

    print("=" * 60)
    print("  🎬  Kids' Learning Video Creator")
    print(f"  {'🖼️   Images: Pexels API ✅' if use_images else '📝  Images: text-only mode'}")
    print("=" * 60)

    os.makedirs(args.output_dir, exist_ok=True)
    created = []

    for cat in categories:
        if cat not in config:
            print(f"⚠️   Unknown category: {cat}")
            continue
        items = config[cat]["items"]
        if args.items > 0:
            items = items[: args.items]

        output_path = os.path.join(args.output_dir, f"{cat}_learning.mp4")
        print(f"\n🎯  {cat.upper()} — {len(items)} items")
        print(f"📁  → {output_path}")
        print("-" * 40)

        try:
            create_kids_video(category=cat, items=items, output_path=output_path,
                              lang=args.lang, use_images=use_images)
            print(f"✅  {cat}_learning.mp4 done!")
            created.append(output_path)
        except Exception as e:
            import traceback
            print(f"❌  Failed: {e}")
            traceback.print_exc()

    print(f"\n🎉  Done! {len(created)}/{len(categories)} videos created.")
    print("=" * 60)


if __name__ == "__main__":
    main()
