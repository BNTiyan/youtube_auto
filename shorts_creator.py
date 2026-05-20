#!/usr/bin/env python3
"""
YouTube Shorts Creator — Vertical 1080×1920 portrait videos.

Generates mobile-first educational Shorts for kids (animals/fruits/cars/…)
and tech (AI/LLM/RAG/…) content.

YouTube auto-detects vertical videos ≤ 60 sec as Shorts — no special flag needed.

Usage:
    python shorts_creator.py --item Lion    --cat animals
    python shorts_creator.py --item Lion    --cat animals --no-images
    python shorts_creator.py --item RAG     --cat rag    --style tech
    python shorts_creator.py --item Ferrari --cat cars   --output-dir shorts
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
from animation_utils import build_animated_clip, safe_clip_duration
from tts_utils import create_kids_tts, join_spoken_lines

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


# ── PORTRAIT CONSTANTS ────────────────────────────────────────────────────────
WIDTH, HEIGHT     = 1080, 1920   # 9:16 — standard YouTube Shorts resolution
FPS               = 30
PAUSE_AFTER_AUDIO = 0.5
MIN_SLIDE_SEC     = 4.0

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# ── COLOUR THEMES ─────────────────────────────────────────────────────────────
KIDS_THEMES = {
    "animals":    {"bg": (22, 78, 22),   "card": (30, 100, 30),  "accent": (180, 255, 140), "text": (255, 255, 255), "emoji": "🦁"},
    "fruits":     {"bg": (180, 70,  0),  "card": (220, 100, 0),  "accent": (255, 230, 100), "text": (255, 255, 255), "emoji": "🍎"},
    "vegetables": {"bg": (20, 80, 25),   "card": (30, 110, 40),  "accent": (180, 230, 160), "text": (255, 255, 255), "emoji": "🥕"},
    "cars":       {"bg": (130, 15, 15),  "card": (180, 35, 35),  "accent": (255, 180, 100), "text": (255, 255, 255), "emoji": "🚗"},
    "airplanes":  {"bg": (10, 50, 130),  "card": (15, 80, 190),  "accent": (160, 215, 255), "text": (255, 255, 255), "emoji": "✈️"},
    "brands":     {"bg": (60, 10, 120),  "card": (90, 25, 170),  "accent": (220, 160, 255), "text": (255, 255, 255), "emoji": "⭐"},
}
TECH_THEMES = {
    "ai":       {"bg": (8,  10, 30),  "card": (15, 20, 60),  "accent": (100, 170, 255), "text": (255, 255, 255), "emoji": "🤖"},
    "llm":      {"bg": (15,  8, 35),  "card": (25, 15, 65),  "accent": (180, 150, 255), "text": (255, 255, 255), "emoji": "💬"},
    "rag":      {"bg": (8,  25, 22),  "card": (12, 50, 44),  "accent": (60, 220, 165),  "text": (255, 255, 255), "emoji": "🔍"},
    "database": {"bg": (28, 12,  5),  "card": (55, 25, 10),  "accent": (255, 160, 70),  "text": (255, 255, 255), "emoji": "🗄️"},
    "mcp":      {"bg": (5,  28, 15),  "card": (10, 55, 30),  "accent": (80, 230, 135),  "text": (255, 255, 255), "emoji": "🔌"},
}
DEFAULT_THEME = {
    "bg": (18, 18, 18), "card": (35, 35, 35),
    "accent": (200, 200, 200), "text": (255, 255, 255), "emoji": "📚",
}

# Pexels search suffixes per category (portrait orientation)
PEXELS_SUFFIX = {
    "animals":    "animal wildlife nature portrait",
    "fruits":     "fruit fresh food portrait",
    "vegetables": "vegetable fresh portrait",
    "cars":       "car automobile portrait",
    "airplanes":  "airplane aircraft sky portrait",
    "brands":     "brand colorful portrait",
    "ai":         "artificial intelligence futuristic technology portrait",
    "llm":        "language AI chatbot interface portrait",
    "rag":        "search retrieval knowledge portrait",
    "database":   "database server technology portrait",
    "mcp":        "protocol API network connection portrait",
}

# ── FONT LOADING ──────────────────────────────────────────────────────────────
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
                f = ImageFont.truetype(path, size)
                _FONT_CACHE[size] = f
                return f
            except Exception:
                continue
    try:
        f = ImageFont.load_default(size=size)
    except TypeError:
        f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    y: int,
    fill: tuple,
    stroke_fill: tuple = (0, 0, 0),
    stroke_width: int = 6,
) -> None:
    """Draw centered text with a thick stroke for readability over photos."""
    tw = _text_w(draw, text, font)
    x = (WIDTH - tw) // 2
    draw.text((x, y), text, font=font, fill=stroke_fill,
              stroke_width=stroke_width, stroke_fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _auto_size_font(draw, text: str, max_w: int, start_size: int = 160,
                    min_size: int = 60) -> ImageFont.FreeTypeFont:
    """Return the largest font that fits `text` within `max_w` pixels."""
    for size in range(start_size, min_size - 1, -8):
        f = load_font(size)
        if _text_w(draw, text, f) <= max_w:
            return f
    return load_font(min_size)


# ── PEXELS (portrait) ─────────────────────────────────────────────────────────
_img_cache: dict = {}


def fetch_pexels_image(query: str) -> Optional[Image.Image]:
    """Fetch a portrait-orientation image from Pexels. Returns None on failure."""
    if not PEXELS_API_KEY:
        return None
    if query in _img_cache:
        return _img_cache[query]
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 5, "orientation": "portrait"},
            timeout=10,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            resp2 = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": query, "per_page": 5},
                timeout=10,
            )
            resp2.raise_for_status()
            photos = resp2.json().get("photos", [])
        if not photos:
            _img_cache[query] = None
            return None
        src = photos[0]["src"]
        url = src.get("large2x") or src.get("large")
        ir = requests.get(url, timeout=15)
        ir.raise_for_status()
        img = Image.open(BytesIO(ir.content)).convert("RGB")
        _img_cache[query] = img
        return img
    except Exception as e:
        print(f"  ⚠️  Pexels: {e}")
        _img_cache[query] = None
        return None


def get_item_image(name: str, category: str) -> Optional[Image.Image]:
    suffix = PEXELS_SUFFIX.get(category, "portrait")
    return fetch_pexels_image(f"{name} {suffix}".strip())


# ── IMAGE PROCESSING ──────────────────────────────────────────────────────────

def _fill_portrait(img: Image.Image) -> Image.Image:
    """Scale and centre-crop any image to exactly 1080×1920."""
    iw, ih = img.size
    scale = max(WIDTH / iw, HEIGHT / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - WIDTH) // 2
    top  = (nh - HEIGHT) // 2
    return img.crop((left, top, left + WIDTH, top + HEIGHT))


def _gradient_overlay(base: Image.Image, start_y: int, target_rgb: tuple,
                      strength: float = 0.90) -> Image.Image:
    """Darken rows from start_y to the bottom toward target_rgb."""
    arr = np.array(base, dtype=np.float32)
    tc  = np.array(target_rgb, dtype=np.float32)
    h   = HEIGHT - start_y
    for i in range(h):
        alpha = ((i / h) ** 0.65) * strength
        arr[start_y + i] = arr[start_y + i] * (1 - alpha) + tc * alpha
    return Image.fromarray(arr.astype(np.uint8))


def _top_gradient_overlay(base: Image.Image, end_y: int, target_rgb: tuple,
                           strength: float = 0.72) -> Image.Image:
    """Darken rows from 0 to end_y toward target_rgb (top overlay)."""
    arr = np.array(base, dtype=np.float32)
    tc  = np.array(target_rgb, dtype=np.float32)
    for i in range(end_y):
        alpha = ((1 - i / end_y) ** 0.65) * strength
        arr[i] = arr[i] * (1 - alpha) + tc * alpha
    return Image.fromarray(arr.astype(np.uint8))


def _dot_bg(draw: ImageDraw.ImageDraw, theme: dict) -> None:
    """Subtle dot grid for text-only fallback slides."""
    for x in range(0, WIDTH, 90):
        for y in range(0, HEIGHT, 90):
            draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=theme["card"])


# ── SLIDE BUILDER ─────────────────────────────────────────────────────────────

def create_short_slide(
    title: str,
    subtitle: str,
    theme: dict,
    top_label: str = "",
    image: Optional[Image.Image] = None,
) -> np.ndarray:
    """
    Compose one 1080×1920 portrait frame:

    [  TOP LABEL — category pill (top 180px)   ]   ← always visible
    [                                           ]
    [      full-bleed portrait photo            ]   ← fills frame
    [         (or dot-pattern bg)               ]
    [                                           ]
    [  ─────────── accent line ──────────────   ]
    [  TITLE  — large auto-sized, centered      ]   ← bottom 680px
    [  subtitle — wrapped, smaller              ]
    [                                           ]
    """
    # ── 1. Background ─────────────────────────────────────────────────────────
    if image is not None:
        base = _fill_portrait(image)
        # Dark overlay at top (for label readability)
        base = _top_gradient_overlay(base, end_y=300, target_rgb=(0, 0, 0), strength=0.70)
        # Dark overlay at bottom (for title/subtitle readability)
        base = _gradient_overlay(base, start_y=HEIGHT - 780, target_rgb=theme["bg"], strength=0.93)
    else:
        base = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
        d_tmp = ImageDraw.Draw(base)
        _dot_bg(d_tmp, theme)

    draw = ImageDraw.Draw(base)

    # ── 2. Top category pill ──────────────────────────────────────────────────
    if top_label:
        lf    = load_font(56)
        lw    = _text_w(draw, top_label, lf)
        pad   = 28
        px1   = (WIDTH - lw - pad * 2) // 2
        px2   = px1 + lw + pad * 2
        py1, py2 = 55, 55 + 56 + pad
        draw.rounded_rectangle([px1, py1, px2, py2], radius=34, fill=theme["card"])
        draw.text((px1 + pad, py1 + pad // 2), top_label, font=lf, fill=theme["accent"])

    # ── 3. Accent line above title ────────────────────────────────────────────
    margin   = 70
    title_y  = HEIGHT - 680
    line_y   = title_y - 28
    draw.line([(margin, line_y), (WIDTH - margin, line_y)],
              fill=theme["accent"], width=5)

    # ── 4. Title (auto-size to fit) ───────────────────────────────────────────
    title_font = _auto_size_font(draw, title, max_w=WIDTH - margin * 2,
                                 start_size=170, min_size=70)
    _draw_centered(draw, title, title_font, title_y, theme["text"],
                   stroke_fill=(0, 0, 0), stroke_width=7)

    # ── 5. Subtitle / fact lines ──────────────────────────────────────────────
    sub_font  = load_font(62)
    # Narrower wrap for large titles to avoid crowding
    title_px  = _text_w(draw, title, title_font)
    max_chars = 22 if title_px > WIDTH * 0.7 else 28
    wrapped   = textwrap.wrap(subtitle, width=max_chars)
    sub_y     = title_y + title_font.size + 28 if hasattr(title_font, "size") else title_y + 180
    for line in wrapped[:3]:
        lw_px = _text_w(draw, line, sub_font)
        x     = (WIDTH - lw_px) // 2
        draw.text((x, sub_y), line, font=sub_font, fill=theme["accent"],
                  stroke_width=5, stroke_fill=(0, 0, 0))
        sub_y += 84

    return np.array(base)


# ── AUDIO + CLIP ──────────────────────────────────────────────────────────────

def make_tts(text: str, path: str, lang: str = "en") -> None:
    create_kids_tts(text, path, lang)


def make_clip(slide: np.ndarray, audio_path: str, animate: bool = False):
    audio    = AudioFileClip(audio_path)
    duration = safe_clip_duration(audio.duration, PAUSE_AFTER_AUDIO, MIN_SLIDE_SEC)
    clip = build_animated_clip(
        slide,
        duration=duration,
        animate=animate,
        zoom_ratio=0.08,
        pan_pixels=28,
        fadein_duration=0.25,
    )
    return _set_audio(clip, audio)


# ── SHORT VIDEO BUILDER ───────────────────────────────────────────────────────

def create_short(
    name: str,
    text: str,
    category: str,
    output_path: str,
    style: str = "kids",
    lang: str = "en",
    use_images: bool = True,
    points: list = [],
) -> str:
    """
    Build a 3-slide portrait Short:  intro → main → outro.
    Typical total: 30–55 seconds (within YouTube Shorts 60 sec limit).
    Uses up to 2 bullet points for main slide if provided.
    """
    themes    = KIDS_THEMES if style == "kids" else TECH_THEMES
    theme     = themes.get(category.lower(), DEFAULT_THEME)
    emoji     = theme.get("emoji", "📚")
    top_label = f"{emoji}  {category.capitalize()}"
    clips     = []

    with tempfile.TemporaryDirectory() as tmp:

        # ── Fetch portrait image (reused across slides) ───────────────────────
        img = None
        if use_images:
            print(f"  🖼️  Fetching portrait image for {name}…")
            img = get_item_image(name, category)
            print(f"       {'✅ got image' if img else '📝 no image — text-only mode'}")

        # ── Slide 1: Hook / Intro ─────────────────────────────────────────────
        print("  Building intro slide…")
        if style == "kids":
            intro_title    = "Did you know? 🤔"
            intro_subtitle = f"Today: {name}!"
            intro_tts      = join_spoken_lines(
                "Hi friends. Did you know",
                f"Today we're learning about {name}",
            )
        else:
            intro_title    = "Today's Concept"
            intro_subtitle = name
            intro_tts      = join_spoken_lines(
                f"Today's concept is {name}",
                f"It's a key topic in {category}",
                "Let's dive in",
            )

        intro_slide = create_short_slide(
            title=intro_title, subtitle=intro_subtitle,
            theme=theme, top_label=top_label, image=img,
        )
        intro_mp3 = os.path.join(tmp, "intro.mp3")
        make_tts(intro_tts, intro_mp3, lang)
        clips.append(make_clip(intro_slide, intro_mp3, animate=(img is not None)))

        # ── Slide 2: Main content ─────────────────────────────────────────────
        print("  Building main slide…")
        use_pts = [p for p in points if p][:2]
        if use_pts:
            main_subtitle = "  •  ".join(use_pts)
            main_tts_text = join_spoken_lines(name, ". ".join(use_pts))
        else:
            main_subtitle = text
            main_tts_text = join_spoken_lines(name, text)
        main_slide = create_short_slide(
            title=name, subtitle=main_subtitle,
            theme=theme, top_label=top_label, image=img,
        )
        main_mp3 = os.path.join(tmp, "main.mp3")
        make_tts(main_tts_text, main_mp3, lang)
        clips.append(make_clip(main_slide, main_mp3, animate=(img is not None)))

        # ── Slide 3: Outro (solid colour — no photo distraction) ──────────────
        print("  Building outro slide…")
        if style == "kids":
            outro_title    = "Great Job! ⭐"
            outro_subtitle = "Come back tomorrow!"
            outro_tts      = join_spoken_lines(
                f"Amazing. Now you know about {name}",
                "Come back tomorrow for more",
            )
        else:
            outro_title    = "See You Tomorrow!"
            outro_subtitle = f"One {category.upper()} concept every day"
            outro_tts      = join_spoken_lines(
                f"Great work. Now you understand {name}",
                "See you tomorrow for another concept",
            )

        outro_slide = create_short_slide(
            title=outro_title, subtitle=outro_subtitle,
            theme=theme, top_label=top_label, image=None,   # solid bg for outro
        )
        outro_mp3 = os.path.join(tmp, "outro.mp3")
        make_tts(outro_tts, outro_mp3, lang)
        clips.append(make_clip(outro_slide, outro_mp3, animate=False))

        # ── Render ────────────────────────────────────────────────────────────
        print(f"\n  Rendering {WIDTH}×{HEIGHT} Short → {output_path}")
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


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create YouTube Shorts (1080×1920 portrait) for kids or tech learning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python shorts_creator.py --item Lion    --cat animals
  python shorts_creator.py --item Ferrari --cat cars
  python shorts_creator.py --item RAG     --cat rag    --style tech
  python shorts_creator.py --item Lion    --cat animals --no-images
        """,
    )
    parser.add_argument("--item",       required=True,
                        help="Item/concept name e.g. 'Lion'")
    parser.add_argument("--cat",        required=True,
                        help="Category e.g. 'animals' or 'rag'")
    parser.add_argument("--text",       default="",
                        help="Fact/explanation text (auto-loaded from config if omitted)")
    parser.add_argument("--style",      default="kids", choices=["kids", "tech"],
                        help="Visual style: kids (colourful) or tech (dark professional)")
    parser.add_argument("--config",     default="",
                        help="Content config JSON (auto-selected by --style if omitted)")
    parser.add_argument("--output-dir", default="shorts")
    parser.add_argument("--lang",       default="en")
    parser.add_argument("--no-images",  action="store_true",
                        help="Skip Pexels image fetch — use solid colour background")
    args = parser.parse_args()

    use_images = not args.no_images
    if use_images and not PEXELS_API_KEY:
        print("⚠️   PEXELS_API_KEY not set — text-only mode.")
        print("    Free key: https://www.pexels.com/api/\n")
        use_images = False

    # ── Auto-select config ────────────────────────────────────────────────────
    if not args.config:
        args.config = ("tech_content_config"
                       if args.style == "tech"
                       else "content_config")

    # ── Look up text and points from config if not supplied ───────────────────
    text   = args.text
    points = []
    
    config_path = args.config
    if os.path.isdir(args.config):
        if args.cat and os.path.exists(os.path.join(args.config, f"{args.cat}.json")):
            config_path = os.path.join(args.config, f"{args.cat}.json")
        else:
            json_files = sorted(glob.glob(os.path.join(args.config, "*.json")))
            if json_files:
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

    if os.path.exists(config_path):
        cat_from_file = os.path.basename(config_path).replace(".json", "")
        with open(config_path) as f:
            raw_cfg = json.load(f)
        
        # Normalize
        config = {}
        is_multi = False
        for k, v in raw_cfg.items():
            if isinstance(v, dict) and "items" in v:
                is_multi = True
                break
        
        if is_multi:
            config = raw_cfg
        else:
            items = []
            if isinstance(raw_cfg, dict) and raw_cfg and isinstance(next(iter(raw_cfg.values())), dict):
                for name, data in raw_cfg.items():
                    item = {"name": name}
                    item.update(data)
                    items.append(item)
            elif "items" in raw_cfg:
                items = raw_cfg["items"]
            else:
                items = raw_cfg if isinstance(raw_cfg, list) else []
            config = {cat_from_file: {"items": items}}

        cat = args.cat.lower() if args.cat else cat_from_file
        if cat in config:
            field = "explanation" if args.style == "tech" else "fact"
            item_data = next(
                (it for it in config[cat].get("items", [])
                 if it.get("name", "").lower() == args.item.lower()),
                None,
            )
            if item_data:
                if not text:
                    text = item_data.get(field, "")
                points = item_data.get("points", [])

    if not text:
        text = f"{args.item} is amazing!"

    slug        = args.item.lower().replace(" ", "_").replace("-", "_")
    output_path = os.path.join(args.output_dir, f"{slug}_short.mp4")

    print("=" * 60)
    print(f"  📱  YouTube Shorts Creator  ({WIDTH}×{HEIGHT})")
    print(f"  🎨  Style    : {args.style}")
    print(f"  📂  Category : {args.cat}")
    print(f"  🏷️   Item     : {args.item}")
    print(f"  {'🖼️   Images  : Pexels API ✅' if use_images else '📝  Images  : solid colour (no Pexels)'}")
    print("=" * 60)

    os.makedirs(args.output_dir, exist_ok=True)
    try:
        create_short(
            name=args.item, text=text, category=args.cat,
            output_path=output_path, style=args.style,
            lang=args.lang, use_images=use_images, points=points,
        )
        print(f"\n✅  Short ready: {output_path}")
        print("📏  1080×1920 portrait — YouTube auto-detects as a Short ✅")
    except Exception as e:
        import traceback
        print(f"❌  Failed: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
