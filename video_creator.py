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
    """Return a learning card with animated text and illustration layers."""
    from motion_design import MotionSlide, KidsScene
    return MotionSlide(KidsScene(title, fact, theme, load_font, image=image, counter=counter))


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


def _chunk_script_text(text: str, max_chars: int = 320) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    chunks = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks or [text]


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
    sections = [section for section in item.get("sections", []) if isinstance(section, dict)]
    clips = []

    with tempfile.TemporaryDirectory() as tmp:

        # Fetch image once and reuse across slides
        item_img = None
        if use_images:
            print(f"  🖼️  Fetching image for {name}...")
            item_img = get_item_image(name, category)

        if sections:
            print("  Creating intro slide...")
            intro_slide = create_slide(
                title=name,
                fact=sections[0].get("title", fact),
                theme=theme,
                image=item_img,
            )
            intro_mp3 = os.path.join(tmp, "intro.mp3")
            create_tts(sections[0].get("title", name), intro_mp3, lang)
            clips.append(make_clip(intro_slide, intro_mp3, theme=theme, category=category, animate=(item_img is not None)))

            for section_idx, section in enumerate(sections, 1):
                title = section.get("title") or f"Part {section_idx}"
                narration_chunks = _chunk_script_text(section.get("narration", ""), max_chars=300)
                for chunk_idx, chunk in enumerate(narration_chunks, 1):
                    print(f"  Creating script slide {section_idx}.{chunk_idx}...")
                    slide = create_slide(
                        title=title,
                        fact=section.get("slide_text") or chunk,
                        theme=theme,
                        image=item_img,
                    )
                    mp3_path = os.path.join(tmp, f"section_{section_idx}_{chunk_idx}.mp3")
                    create_tts(chunk, mp3_path, lang)
                    clips.append(make_clip(slide, mp3_path, theme=theme, category=category, animate=(item_img is not None)))
        else:
            # ── Intro slide ──────────────────────────────────────────────────────
            print("  Creating intro slide...")
            intro_slide = create_slide(
                title=f"Today: {name}!",
                fact=f"A fun {category} fact just for you!",
                theme=theme,
                image=item_img,
            )
            intro_mp3 = os.path.join(tmp, "intro.mp3")
            create_tts(
                join_spoken_lines(
                    f"Hi friends. Today we're learning about {name}",
                    "Let's get started",
                ),
                intro_mp3,
                lang,
            )
            clips.append(make_clip(intro_slide, intro_mp3, theme=theme, category=category, animate=(item_img is not None)))

            # ── Main content slide ────────────────────────────────────────────────
            print("  Creating main slide...")
            main_slide = create_slide(
                title=name,
                fact=fact,
                theme=theme,
                image=item_img,
            )
            main_mp3 = os.path.join(tmp, "main.mp3")
            create_tts(
                join_spoken_lines(
                    f"This is {name}",
                    fact,
                ),
                main_mp3,
                lang,
            )
            clips.append(make_clip(main_slide, main_mp3, theme=theme, category=category, animate=(item_img is not None)))

            # ── Outro slide ───────────────────────────────────────────────────────
            print("  Creating outro slide...")
            outro_slide = create_outro_slide(category, theme)
            outro_mp3   = os.path.join(tmp, "outro.mp3")
            create_tts(
                join_spoken_lines(
                    f"Great job. Now you know about {name}",
                    "Come back tomorrow for another fun fact",
                ),
                outro_mp3,
                lang,
            )
            clips.append(make_clip(outro_slide, outro_mp3, theme=theme, category=category, animate=False, decorative=True))

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


# ── PLAYFUL KIDS OVERLAY ANIMATION ────────────────────────────────────────────

def _draw_star(draw, cx: float, cy: float, radius: float, fill) -> None:
    points = []
    inner_radius = radius * 0.45
    for i in range(10):
        angle = np.pi / 5 * i - np.pi / 2
        r = radius if i % 2 == 0 else inner_radius
        points.append((cx + np.cos(angle) * r, cy + np.sin(angle) * r))
    draw.polygon(points, fill=fill)


def _draw_bird(draw, x: float, y: float, scale: float, fill) -> None:
    wing_w = 28 * scale
    wing_h = 16 * scale
    width = max(2, int(3 * scale))
    draw.arc([x - wing_w, y - wing_h, x, y + wing_h], start=205, end=340, fill=fill, width=width)
    draw.arc([x, y - wing_h, x + wing_w, y + wing_h], start=200, end=335, fill=fill, width=width)


def _draw_cloud(draw, x: float, y: float, scale: float, fill) -> None:
    puffs = [
        (x - 28 * scale, y + 2 * scale, 18 * scale),
        (x - 4 * scale, y - 10 * scale, 24 * scale),
        (x + 24 * scale, y + 2 * scale, 19 * scale),
    ]
    for px, py, r in puffs:
        draw.ellipse([px - r, py - r, px + r, py + r], fill=fill)
    draw.rounded_rectangle(
        [x - 48 * scale, y - 6 * scale, x + 46 * scale, y + 24 * scale],
        radius=max(4, int(12 * scale)),
        fill=fill,
    )


def _draw_plane(draw, x: float, y: float, scale: float, fill) -> None:
    body = [
        (x - 26 * scale, y + 2 * scale),
        (x + 12 * scale, y - 7 * scale),
        (x + 26 * scale, y),
        (x + 12 * scale, y + 7 * scale),
    ]
    wing = [
        (x - 2 * scale, y),
        (x - 16 * scale, y - 15 * scale),
        (x + 3 * scale, y - 4 * scale),
        (x + 8 * scale, y + 12 * scale),
    ]
    tail = [
        (x - 20 * scale, y + 2 * scale),
        (x - 31 * scale, y - 10 * scale),
        (x - 14 * scale, y),
    ]
    draw.polygon(body, fill=fill)
    draw.polygon(wing, fill=fill)
    draw.polygon(tail, fill=fill)


def _draw_leaf(draw, x: float, y: float, scale: float, fill) -> None:
    draw.ellipse([x - 18 * scale, y - 10 * scale, x + 18 * scale, y + 10 * scale], fill=fill)
    draw.line([x - 14 * scale, y + 8 * scale, x + 14 * scale, y - 8 * scale], fill=(255, 255, 255, 80), width=max(1, int(2 * scale)))


def _draw_wheel(draw, x: float, y: float, scale: float, fill, inner_fill) -> None:
    r = 18 * scale
    draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)
    inner_r = 7 * scale
    draw.ellipse([x - inner_r, y - inner_r, x + inner_r, y + inner_r], fill=inner_fill)


def _draw_car(draw, x: float, y: float, scale: float, fill) -> None:
    draw.rounded_rectangle(
        [x - 34 * scale, y - 14 * scale, x + 34 * scale, y + 10 * scale],
        radius=max(4, int(8 * scale)),
        fill=fill,
    )
    draw.polygon(
        [(x - 18 * scale, y - 14 * scale), (x - 2 * scale, y - 28 * scale), (x + 18 * scale, y - 28 * scale), (x + 28 * scale, y - 14 * scale)],
        fill=fill,
    )
    _draw_wheel(draw, x - 18 * scale, y + 12 * scale, scale, (40, 40, 40, 220), (220, 220, 220, 200))
    _draw_wheel(draw, x + 18 * scale, y + 12 * scale, scale, (40, 40, 40, 220), (220, 220, 220, 200))


def _draw_fruit(draw, x: float, y: float, scale: float, fill, leaf_fill) -> None:
    draw.ellipse([x - 20 * scale, y - 22 * scale, x + 20 * scale, y + 22 * scale], fill=fill)
    draw.rectangle([x - 2 * scale, y - 30 * scale, x + 2 * scale, y - 16 * scale], fill=(90, 55, 20, 210))
    _draw_leaf(draw, x + 10 * scale, y - 23 * scale, scale * 0.65, leaf_fill)


def _draw_vegetable(draw, x: float, y: float, scale: float, fill, leaf_fill) -> None:
    draw.ellipse([x - 17 * scale, y - 26 * scale, x + 17 * scale, y + 26 * scale], fill=fill)
    for dx in (-8, 0, 8):
        _draw_leaf(draw, x + dx * scale * 0.5, y - 28 * scale, scale * 0.55, leaf_fill)


def _draw_brand_badge(draw, x: float, y: float, scale: float, fill, accent) -> None:
    size = 26 * scale
    draw.rounded_rectangle([x - size, y - size, x + size, y + size], radius=max(6, int(10 * scale)), fill=fill)
    _draw_star(draw, x, y, 11 * scale, accent)


def _apply_kids_overlay(clip, theme: dict, category: str):
    width, height = clip.size
    accent_rgba = (*theme["accent"], 155)
    soft_white = (255, 255, 255, 120)
    bubble_fill = (*theme["accent"], 85)
    shape_fill = (*theme["text"], 72)
    category = category.lower()

    def _overlay(get_frame, t):
        frame = Image.fromarray(get_frame(t)).convert("RGBA")
        draw = ImageDraw.Draw(frame, "RGBA")

        if category == "animals":
            for i, (base_x, base_y) in enumerate(((110, 90), (width - 120, 110), (width - 210, 70))):
                pulse = 0.75 + 0.25 * np.sin(t * 2.3 + i * 1.2)
                drift_y = 8 * np.sin(t * 1.7 + i)
                _draw_star(draw, base_x, base_y + drift_y, 14 * pulse, accent_rgba)
            for i, base_y in enumerate((92, 145, 185)):
                x = ((t * (150 + i * 24) + i * 220) % (width + 180)) - 90
                y = base_y + 12 * np.sin(t * 2.4 + i * 0.7)
                _draw_bird(draw, x, y, 0.8 + i * 0.12, soft_white)
        elif category == "airplanes":
            for i, base_y in enumerate((86, 136)):
                x = ((t * (145 + i * 18) + i * 280) % (width + 200)) - 100
                _draw_cloud(draw, x, base_y + 6 * np.sin(t * 1.4 + i), 0.9 + i * 0.12, (255, 255, 255, 92))
            for i, base_y in enumerate((120, 180)):
                x = ((t * (210 + i * 30) + i * 350) % (width + 220)) - 110
                _draw_plane(draw, x, base_y + 10 * np.sin(t * 1.9 + i), 0.9 + i * 0.12, accent_rgba)
        elif category == "cars":
            for i, lane_y in enumerate((height - 126, height - 76)):
                x = ((t * (220 + i * 35) + i * 300) % (width + 240)) - 120
                _draw_car(draw, x, lane_y + 4 * np.sin(t * 3.0 + i), 0.72 + i * 0.08, (*theme["accent"], 170))
        elif category == "fruits":
            fruit_colors = [(255, 120, 120, 170), (255, 195, 90, 170), (255, 90, 140, 170)]
            for i, base_x in enumerate((95, 165, width - 165, width - 95)):
                y = 125 + ((t * (34 + i * 4) + i * 100) % (height - 240))
                wobble = 14 * np.sin(t * 1.8 + i)
                _draw_fruit(draw, base_x + wobble, y, 0.72, fruit_colors[i % len(fruit_colors)], (*theme["accent"], 150))
        elif category == "vegetables":
            veg_colors = [(110, 205, 100, 170), (255, 145, 80, 170), (150, 220, 120, 170)]
            for i, base_x in enumerate((95, 165, width - 165, width - 95)):
                y = 135 + ((t * (30 + i * 4) + i * 110) % (height - 250))
                wobble = 12 * np.sin(t * 1.9 + i)
                _draw_vegetable(draw, base_x + wobble, y, 0.74, veg_colors[i % len(veg_colors)], (*theme["accent"], 145))
        elif category == "brands":
            for i, base_x in enumerate((95, 165, width - 165, width - 95)):
                y = 130 + ((t * (34 + i * 5) + i * 92) % (height - 245))
                wobble = 14 * np.sin(t * 1.7 + i)
                _draw_brand_badge(draw, base_x + wobble, y, 0.78, (*theme["card"], 170), (*theme["accent"], 170))
        else:
            for i, (base_x, base_y) in enumerate(((110, 90), (width - 120, 110), (width - 210, 70))):
                pulse = 0.75 + 0.25 * np.sin(t * 2.3 + i * 1.2)
                drift_y = 8 * np.sin(t * 1.7 + i)
                _draw_star(draw, base_x, base_y + drift_y, 14 * pulse, accent_rgba)
            for i, base_x in enumerate((90, 170, width - 170, width - 95)):
                y = 120 + ((t * (38 + i * 6) + i * 95) % (height - 220))
                wobble = 18 * np.sin(t * 1.6 + i * 0.8)
                r = 12 + 4 * np.sin(t * 2.1 + i)
                if i % 2 == 0:
                    draw.ellipse([base_x + wobble - r, y - r, base_x + wobble + r, y + r], fill=bubble_fill)
                else:
                    side = 18 + 4 * np.sin(t * 1.4 + i)
                    draw.rounded_rectangle(
                        [base_x + wobble - side, y - side, base_x + wobble + side, y + side],
                        radius=8,
                        fill=shape_fill,
                    )

        return np.array(frame.convert("RGB"))

    if hasattr(clip, "fl"):
        return clip.fl(_overlay)
    return clip.transform(_overlay)


# ── CLIP ASSEMBLY ─────────────────────────────────────────────────────────────

def make_clip(slide: np.ndarray, audio_path: str, theme: dict, category: str, animate: bool = False, decorative: bool = True):
    """
    Build a single slide video clip.

    Motion scenes animate text and illustrations independently.
    Legacy bitmap slides retain optional zoom and decorative overlays.
    """
    audio    = AudioFileClip(audio_path)
    duration = safe_clip_duration(audio.duration, PAUSE_AFTER_AUDIO, MIN_SLIDE_DURATION)
    clip = build_animated_clip(
        slide,
        duration=duration,
        animate=animate,
        zoom_ratio=0.06,
        pan_pixels=20,
        fadein_duration=0.30,
    )
    if decorative and getattr(slide, "scene", None) is None:
        clip = _apply_kids_overlay(clip, theme, category)
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
        create_tts(
            join_spoken_lines(
                f"Hi friends. Let's learn about {category}",
                f"We have {total} fun things to explore today",
            ),
            intro_mp3,
            lang,
        )
        clips.append(make_clip(intro_slide, intro_mp3, theme=theme, category=category, animate=(intro_img is not None)))

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
            create_tts(
                join_spoken_lines(
                    f"Number {i}. {name}",
                    fact,
                ),
                mp3_path,
                lang,
            )
            clips.append(make_clip(slide, mp3_path, theme=theme, category=category, animate=(item_img is not None)))

        # ── Outro ──
        print("  Creating outro...")
        outro_slide = create_outro_slide(category, theme)
        outro_mp3   = os.path.join(tmp, "outro.mp3")
        create_tts(
            join_spoken_lines(
                f"Amazing work. You learned about {total} {category}",
                "Come back tomorrow for more",
            ),
            outro_mp3,
            lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3, theme=theme, category=category, animate=False, decorative=True))

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
