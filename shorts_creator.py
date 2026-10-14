#!/usr/bin/env python3
"""
YouTube Shorts Creator — Vertical 1080×1920 portrait videos.

Generates mobile-first educational Shorts for kids (animals/fruits/cars/…)
and tech (AI/LLM/RAG/…) content.

Narration and text are kept complete; videos are never trimmed mid-sentence.

Usage:
    python shorts_creator.py --item Lion    --cat animals
    python shorts_creator.py --item Lion    --cat animals --no-images
    python shorts_creator.py --item RAG     --cat rag    --style tech
    python shorts_creator.py --item Ferrari --cat cars   --output-dir shorts
"""

from filename_utils import video_slug
from visual_assets import relevant_image, save_visual_manifest
import os
import json
import argparse
import textwrap
import re
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

    # Fit every line by pixel width and height instead of discarding wrapped text.
    from motion_design import wrap_pixels
    def draw_fitted(text, y, height, start_size, color):
        for size in range(start_size, 27, -2):
            font = load_font(size)
            lines = wrap_pixels(draw, text, font, WIDTH - 160)
            if len(lines) * (size + 16) <= height and all(draw.textlength(line, font=font) <= WIDTH-160 for line in lines):
                break
        else:
            raise ValueError("Short text cannot fit legibly. Use shorter complete sentences.")
        for line in lines:
            x = (WIDTH - draw.textlength(line, font=font)) / 2
            draw.text((x, y), line, font=font, fill=color, stroke_width=1, stroke_fill=theme["bg"])
            y += size + 16
    # Opaque text panel keeps illustrations and captions separate.
    draw.rounded_rectangle((40, 1190, WIDTH-40, 1805), radius=32, fill=theme["card"])
    draw_fitted(title, 1225, 200, 84, theme["text"])
    draw.line((80, 1440, WIDTH-80, 1440), fill=theme["accent"], width=3)
    draw_fitted(subtitle, 1470, 300, 54, theme["text"])

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

def portrait_source_image(source_image, theme):
    from PIL import ImageOps
    from visual_assets import image_credit
    from motion_design import wrap_pixels
    background = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
    photo = ImageOps.contain(source_image, (900, 850))
    background.paste(photo, (90+(900-photo.width)//2, 240+(850-photo.height)//2))
    draw = ImageDraw.Draw(background)
    for i, line in enumerate(wrap_pixels(draw, image_credit(source_image), load_font(24), 900)[:2]):
        draw.text((90, 1110+i*28), line, font=load_font(24), fill=theme["text"])
    return background


def build_short_script(name, text, points=None, source_text=""):
    """Return a complete source-grounded explanation, with no stock intro/outro."""
    from tts_utils import join_spoken_lines
    parts = [str(text).strip()] + [str(p).strip() for p in (points or []) if p]
    parts = list(dict.fromkeys(p for p in parts if p))
    script = join_spoken_lines(*parts)
    if not script:
        raise ValueError("A Short needs a factual explanation, not just a topic name")
    if len(script.split()) > 95 or any(p.endswith(('...', '…')) for p in parts):
        from llm_client import generate_json
        data = generate_json(
            f"Write a complete standalone educational Short about {name}. "
            "Use only the source below. Explain the idea, give a concrete detail or example, "
            "and end with a useful takeaway. Write 45 to 85 words in 3 to 5 complete, short sentences. "
            "Preserve the source language. No branding, greetings, subscribe requests, "
            "unsupported facts, ellipses, or unfinished sentences. Return JSON with one string field: script.\n"
            + (source_text or '\n'.join(parts))
        )
        script = data.get('script', '')
        if not isinstance(script, str) or not script.strip():
            raise ValueError("LLM did not return a complete Short script")
        script = script.strip()
    if script.endswith(('...', '…')) or script[-1] not in '.!?।':
        raise ValueError("Short script ends unfinished; revise the source or generated script")
    return script


def short_script_pages(script):
    """Sentence boundaries provide natural narration stops; no word slicing."""
    return [s.strip() for s in re.split(r'(?<=[.!?।])\s+', script) if s.strip()]


def create_short(
    name: str,
    text: str,
    category: str,
    output_path: str,
    style: str = "kids",
    lang: str = "en",
    use_images: bool = True,
    points: Optional[list] = None,
    source_text: str = "",
    prepared_for_kids: bool = False,
) -> str:
    """
    Build a 3-slide portrait Short:  intro → main → outro.
    Uses a standalone explanation and one complete sentence per narrated scene.
    Each scene lasts for the full audio plus a reading pause.
    """
    themes    = KIDS_THEMES if style == "kids" else TECH_THEMES
    theme     = themes.get(category.lower(), DEFAULT_THEME)
    emoji     = theme.get("emoji", "📚")
    top_label = f"{emoji}  {category.capitalize()}"
    clips     = []

    with tempfile.TemporaryDirectory() as tmp:

        # ── Fetch portrait image (reused across slides) ───────────────────────
        img = None
        if style == "tech":
            from tech_video_creator import create_tech_slide, TECH_THEMES as LANDSCAPE_THEMES, DEFAULT_TECH_THEME
            diagram = Image.fromarray(create_tech_slide(name, text, LANDSCAPE_THEMES.get(category.lower(), DEFAULT_TECH_THEME))).crop((804, 161, 1216, 594))
            img = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
            img.paste(diagram.resize((880, 925), Image.Resampling.LANCZOS), (100, 240))
        elif style == "kids":
            from kids_illustrations import subject_illustration
            subject = subject_illustration(name)
            img = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
            img.paste(subject.resize((900, 900), Image.Resampling.LANCZOS), (90, 250))
        elif use_images:
            print(f"  🖼️  Fetching portrait image for {name}…")
            img = get_item_image(name, category)
            print(f"       {'✅ got image' if img else '📝 no image — text-only mode'}")

        if style == "kids":
            if not prepared_for_kids:
                from kids_content import generate_kids_lesson
                lesson = generate_kids_lesson(name, "\n".join([source_text or text, *(points or [])]), lang)
                text = lesson["short_text"]
            points = []
        source_image = relevant_image(name, text) if use_images else None
        visual_images = [source_image]
        if source_image is not None:
            img = portrait_source_image(source_image, theme)

        script = build_short_script(name, text, points, source_text)
        pages = short_script_pages(script)
        # Validate every page layout before generating any narration.
        slides = []
        for i, sentence in enumerate(pages):
            scene_image = relevant_image(name, sentence) if use_images else None
            visual_images.append(scene_image)
            scene_background = portrait_source_image(scene_image, theme) if scene_image is not None else img
            slides.append(create_short_slide(
                title=name, subtitle=sentence, theme=theme,
                top_label=f"{i+1} / {len(pages)}", image=scene_background,
            ))
        for i, (slide, sentence) in enumerate(zip(slides, pages)):
            print(f"  Narrating complete sentence {i+1}/{len(pages)}...")
            audio_path = os.path.join(tmp, f"sentence_{i}.mp3")
            spoken = join_spoken_lines(name, sentence) if i == 0 else sentence
            make_tts(spoken, audio_path, lang)
            clips.append(make_clip(slide, audio_path, animate=False))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(os.path.splitext(output_path)[0] + "_script.json", "w", encoding="utf-8") as fh:
            json.dump({"topic": name, "script": script, "sentences": pages}, fh, ensure_ascii=False, indent=2)

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
                                  audio_codec="aac", temp_audiofile=os.path.join(tmp, "render_audio.m4a"), logger=None)
        except TypeError:
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac", temp_audiofile=os.path.join(tmp, "render_audio.m4a"))

        for c in clips:
            try:
                c.close()
            except Exception:
                pass
        try:
            final.close()
        except Exception:
            pass

    save_visual_manifest(output_path, visual_images)
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
    # ── Auto-select config ────────────────────────────────────────────────────
    if not args.config:
        args.config = ("tech_content_config"
                       if args.style == "tech"
                       else "content_config")

    # ── Look up text and points from config if not supplied ───────────────────
    text   = args.text
    source_text = args.text
    prepared_for_kids = False
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
                prepared_for_kids = item_data.get("audience") == "8-12"
                source_text = "\n".join(str(section.get("narration", "")) for section in item_data.get("sections", []) if isinstance(section, dict)) or item_data.get("explanation", "") or text

    if not text:
        text = f"{args.item} is amazing!"

    slug        = video_slug(args.item)
    output_path = os.path.join(args.output_dir, f"{slug}_short.mp4")

    print("=" * 60)
    print(f"  📱  YouTube Shorts Creator  ({WIDTH}×{HEIGHT})")
    print(f"  🎨  Style    : {args.style}")
    print(f"  📂  Category : {args.cat}")
    print(f"  🏷️   Item     : {args.item}")
    print("  Visuals : local subject illustration or concept diagram")
    print("=" * 60)

    os.makedirs(args.output_dir, exist_ok=True)
    try:
        create_short(
            name=args.item, text=text, category=args.cat,
            output_path=output_path, style=args.style,
            lang=args.lang, use_images=use_images, points=points, source_text=source_text, prepared_for_kids=prepared_for_kids,
        )
        print(f"\n✅  Short ready: {output_path}")
        print("📏  1080×1920 portrait — YouTube auto-detects as a Short ✅")
    except Exception as e:
        import traceback
        print(f"❌  Failed: {e}")
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
