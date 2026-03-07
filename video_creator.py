#!/usr/bin/env python3
"""
Kids' Learning Video Creator
Generates educational slideshow videos with text-to-speech narration.

Categories: animals, fruits, vegetables, cars, airplanes, brands

Usage:
    python video_creator.py animals                  # Create one category video
    python video_creator.py all                      # Create all category videos
    python video_creator.py fruits --items 5         # Use first 5 items only
    python video_creator.py animals --lang en-uk     # British English TTS
    python video_creator.py all --output-dir videos  # Custom output folder

Requirements:
    pip install moviepy Pillow gTTS numpy
    brew install ffmpeg  (macOS) or  apt install ffmpeg  (Linux)
"""

import os
import json
import argparse
import textwrap
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

# ── moviepy v1 / v2 compat ────────────────────────────────────────────────────
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    _MOVIEPY_V1 = True
except (ImportError, ModuleNotFoundError):
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
    _MOVIEPY_V1 = False


def _set_audio(clip, audio):
    """Attach audio to a clip, compatible with moviepy v1 and v2."""
    try:
        return clip.set_audio(audio)   # v1
    except AttributeError:
        return clip.with_audio(audio)  # v2


# ── VIDEO SETTINGS ────────────────────────────────────────────────────────────
WIDTH, HEIGHT     = 1280, 720
FPS               = 24
PAUSE_AFTER_AUDIO = 0.8   # seconds of silence after TTS narration ends
MIN_SLIDE_DURATION = 4.0  # minimum clip length in seconds

# ── COLOUR THEMES (bg, card, accent, text) ───────────────────────────────────
THEMES = {
    "animals":    {"bg": (22, 78, 22),   "card": (46, 120, 46),   "accent": (144, 238, 144), "text": (255, 255, 255)},
    "fruits":     {"bg": (180, 70,  0),  "card": (230, 110,  0),  "accent": (255, 224, 130), "text": (255, 255, 255)},
    "vegetables": {"bg": (20, 80, 25),   "card": (40, 120, 50),   "accent": (165, 214, 167), "text": (255, 255, 255)},
    "cars":       {"bg": (130, 15, 15),  "card": (190, 40, 40),   "accent": (255, 160, 122), "text": (255, 255, 255)},
    "airplanes":  {"bg": (10, 50, 120),  "card": (20, 90, 180),   "accent": (144, 202, 249), "text": (255, 255, 255)},
    "brands":     {"bg": (60, 10, 110),  "card": (100, 30, 160),  "accent": (206, 147, 216), "text": (255, 255, 255)},
}
DEFAULT_THEME = {"bg": (30, 30, 30), "card": (60, 60, 60), "accent": (200, 200, 200), "text": (255, 255, 255)}

# ── EMOJI FALLBACK PER CATEGORY (added to top-right corner of card) ──────────
CATEGORY_EMOJI = {
    "animals": "🐾",
    "fruits": "🍎",
    "vegetables": "🥦",
    "cars": "🚗",
    "airplanes": "✈️",
    "brands": "⭐",
}

# ── FONTS ─────────────────────────────────────────────────────────────────────
_FONT_CACHE: dict = {}

_FONT_PATHS = [
    # macOS
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    # WSL / Windows fonts
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
    # Pillow built-in fallback
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


# ── SLIDE DRAWING ─────────────────────────────────────────────────────────────

def _draw_text_centered(draw, text: str, font, y: int, color, shadow=(0, 0, 0)):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (WIDTH - tw) // 2
    draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=color)


def _dot_pattern(draw, theme: dict):
    """Draw a subtle dot grid on the background."""
    for x in range(0, WIDTH, 72):
        for y in range(0, HEIGHT, 72):
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=theme["card"])


def create_slide(
    title: str,
    fact: str,
    theme: dict,
    counter: str = "",
) -> np.ndarray:
    """Return a 1280×720 numpy array RGB slide."""
    img = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
    draw = ImageDraw.Draw(img)

    # Background dot pattern
    _dot_pattern(draw, theme)

    # Centre card
    margin = 60
    draw.rectangle([margin, margin, WIDTH - margin, HEIGHT - margin], fill=theme["card"])
    draw.rectangle([margin, margin, WIDTH - margin, HEIGHT - margin],
                   outline=theme["accent"], width=4)

    # Counter (top-right inside card)
    if counter:
        small_font = load_font(30)
        bbox = draw.textbbox((0, 0), counter, font=small_font)
        tw = bbox[2] - bbox[0]
        draw.text((WIDTH - margin - tw - 20, margin + 18), counter,
                  font=small_font, fill=theme["accent"])

    # Title
    title_font = load_font(96)
    _draw_text_centered(draw, title, title_font, HEIGHT // 2 - 115, theme["text"])

    # Divider
    draw.line([margin + 80, HEIGHT // 2 - 8, WIDTH - margin - 80, HEIGHT // 2 - 8],
              fill=theme["accent"], width=3)

    # Fact (wrapped)
    fact_font = load_font(38)
    wrapped = textwrap.wrap(fact, width=58)
    y_pos = HEIGHT // 2 + 18
    for line in wrapped[:3]:
        bbox = draw.textbbox((0, 0), line, font=fact_font)
        tw = bbox[2] - bbox[0]
        x = (WIDTH - tw) // 2
        draw.text((x, y_pos), line, font=fact_font, fill=theme["accent"])
        y_pos += 50

    return np.array(img)


def create_intro_slide(category: str, total: int, theme: dict) -> np.ndarray:
    return create_slide(
        title=f"Learn {category.capitalize()}!",
        fact=f"Discover {total} amazing {category} today",
        theme=theme,
    )


def create_outro_slide(category: str, theme: dict) -> np.ndarray:
    return create_slide(
        title="Great Job! ⭐",
        fact=f"You learned {category} today! Like & Subscribe for more!",
        theme=theme,
    )


# ── AUDIO ─────────────────────────────────────────────────────────────────────

def create_tts(text: str, out_path: str, lang: str = "en") -> None:
    """Save TTS audio from gTTS (requires internet)."""
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(out_path)


# ── CLIP ASSEMBLY ─────────────────────────────────────────────────────────────

def make_clip(slide: np.ndarray, audio_path: str):
    audio = AudioFileClip(audio_path)
    duration = max(audio.duration + PAUSE_AFTER_AUDIO, MIN_SLIDE_DURATION)
    clip = ImageClip(slide, duration=duration)
    clip = _set_audio(clip, audio)
    return clip


# ── MAIN VIDEO BUILDER ────────────────────────────────────────────────────────

def create_kids_video(
    category: str,
    items: list,
    output_path: str,
    lang: str = "en",
) -> str:
    """
    Build a complete kids' learning video for a category.
    Returns output_path on success.
    """
    theme = THEMES.get(category.lower(), DEFAULT_THEME)
    total = len(items)
    clips = []

    with tempfile.TemporaryDirectory() as tmp:

        # ── Intro ──
        print("  Creating intro...")
        intro_slide = create_intro_slide(category, total, theme)
        intro_mp3 = os.path.join(tmp, "intro.mp3")
        create_tts(f"Hello friends! Let's learn about {category}! Get ready!", intro_mp3, lang)
        clips.append(make_clip(intro_slide, intro_mp3))

        # ── Item slides ──
        for i, item in enumerate(items, 1):
            name = item["name"]
            fact = item.get("fact", f"{name} is really amazing!")
            counter = f"{i} of {total}"
            print(f"  [{i}/{total}] {name}")

            slide = create_slide(
                title=name,
                fact=fact,
                theme=theme,
                counter=counter,
            )
            mp3_path = os.path.join(tmp, f"item_{i}.mp3")
            create_tts(f"{name}. {fact}", mp3_path, lang)
            clips.append(make_clip(slide, mp3_path))

        # ── Outro ──
        print("  Creating outro...")
        outro_slide = create_outro_slide(category, theme)
        outro_mp3 = os.path.join(tmp, "outro.mp3")
        create_tts(
            f"Amazing work! You just learned about {total} {category}! "
            "Don't forget to like this video and subscribe for more fun learning!",
            outro_mp3, lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3))

        # ── Render ──
        print(f"\n  Rendering video → {output_path}")
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        try:
            final.write_videofile(
                output_path,
                fps=FPS,
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )
        except TypeError:
            # Older moviepy may not accept logger=None
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

        # Cleanup
        for clip in clips:
            try:
                clip.close()
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
        description="Create kids' learning videos for YouTube",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python video_creator.py animals
  python video_creator.py all
  python video_creator.py fruits --items 5
  python video_creator.py all --lang en-uk --output-dir my_videos
        """,
    )
    parser.add_argument(
        "category",
        nargs="?",
        default="all",
        choices=list(THEMES.keys()) + ["all"],
        help="Category to generate (default: all)",
    )
    parser.add_argument("--config",     default="content_config.json", help="Path to content JSON")
    parser.add_argument("--output-dir", default="videos",              help="Output folder (default: videos/)")
    parser.add_argument("--lang",       default="en",                  help="gTTS language code (default: en)")
    parser.add_argument("--items",      type=int, default=0,           help="Max items per video (0 = all)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"❌  Config not found: {args.config}")
        print("    Expected: content_config.json in the current directory")
        return

    with open(args.config) as f:
        config = json.load(f)

    categories = list(config.keys()) if args.category == "all" else [args.category]

    print("=" * 60)
    print("  🎬  Kids' Learning Video Creator")
    print("=" * 60)

    os.makedirs(args.output_dir, exist_ok=True)
    created = []

    for cat in categories:
        if cat not in config:
            print(f"⚠️   Unknown category in config: {cat}")
            continue

        items = config[cat]["items"]
        if args.items > 0:
            items = items[: args.items]

        output_path = os.path.join(args.output_dir, f"{cat}_learning.mp4")

        print(f"\n🎯  {cat.upper()} — {len(items)} items")
        print(f"📁  → {output_path}")
        print("-" * 40)

        try:
            create_kids_video(
                category=cat,
                items=items,
                output_path=output_path,
                lang=args.lang,
            )
            print(f"✅  {cat}_learning.mp4 done!")
            created.append(output_path)
        except Exception as e:
            import traceback
            print(f"❌  Failed to create {cat} video: {e}")
            traceback.print_exc()

    print(f"\n🎉  Done! {len(created)}/{len(categories)} videos created.")
    if created:
        print("\nNext step — upload to YouTube:")
        print(f"  python youtube_auto.py {args.output_dir}/ \\")
        print(f'      --niche "Kids Education" \\')
        print(f'      --tone "fun and educational for children" \\')
        print(f"      --category 27 --made-for-kids")
    print("=" * 60)


if __name__ == "__main__":
    main()
