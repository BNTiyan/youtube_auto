#!/usr/bin/env python3
"""
Tech Learning Video Creator
Generates professional educational videos for AI/LLM/RAG/Database/MCP topics.

Target audience: developers, students, professionals learning tech concepts.
Style: dark, modern, terminal-inspired slides with TTS narration.

Usage:
    python tech_video_creator.py ai                  # Create one category video
    python tech_video_creator.py all                 # Create all category videos
    python tech_video_creator.py llm --items 5       # Quick test with 5 items
    python tech_video_creator.py all --output-dir tech_videos

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
except (ImportError, ModuleNotFoundError):
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips


def _set_audio(clip, audio):
    try:
        return clip.set_audio(audio)   # v1
    except AttributeError:
        return clip.with_audio(audio)  # v2


# ── VIDEO SETTINGS ────────────────────────────────────────────────────────────
WIDTH, HEIGHT      = 1280, 720
FPS                = 24
PAUSE_AFTER_AUDIO  = 1.0
MIN_SLIDE_DURATION = 5.0  # tech content benefits from slightly longer display

# ── PROFESSIONAL DARK THEMES ─────────────────────────────────────────────────
# Each theme: bg (background), card (panel), accent (highlights),
#             text (white), grid (subtle lines), muted (secondary text)
TECH_THEMES = {
    "ai": {
        "bg":     (8,  10, 25),
        "card":   (14, 20, 50),
        "accent": (96, 165, 250),    # blue
        "text":   (255, 255, 255),
        "grid":   (18, 25, 58),
        "muted":  (170, 195, 235),
        "badge":  "🤖  Artificial Intelligence",
    },
    "llm": {
        "bg":     (12, 8,  28),
        "card":   (22, 16, 56),
        "accent": (167, 139, 250),   # purple
        "text":   (255, 255, 255),
        "grid":   (28, 20, 65),
        "muted":  (200, 185, 240),
        "badge":  "💬  Large Language Models",
    },
    "rag": {
        "bg":     (8,  22, 20),
        "card":   (14, 44, 40),
        "accent": (52, 211, 153),    # emerald green
        "text":   (255, 255, 255),
        "grid":   (18, 52, 48),
        "muted":  (150, 220, 200),
        "badge":  "🔍  Retrieval Augmented Generation",
    },
    "database": {
        "bg":     (25, 12, 5),
        "card":   (50, 24, 10),
        "accent": (251, 146, 60),    # orange
        "text":   (255, 255, 255),
        "grid":   (60, 30, 14),
        "muted":  (235, 185, 140),
        "badge":  "🗄️   Database Systems",
    },
    "mcp": {
        "bg":     (5,  25, 14),
        "card":   (10, 50, 28),
        "accent": (74, 222, 128),    # green
        "text":   (255, 255, 255),
        "grid":   (12, 58, 34),
        "muted":  (155, 230, 185),
        "badge":  "🔌  Model Context Protocol",
    },
}
DEFAULT_TECH_THEME = {
    "bg": (12, 12, 12), "card": (24, 24, 24), "accent": (200, 200, 200),
    "text": (255, 255, 255), "grid": (28, 28, 28), "muted": (180, 180, 180),
    "badge": "📖  Tech Learning",
}

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


def fit_text_font(draw, text: str, max_width: int, max_size: int = 80) -> ImageFont.FreeTypeFont:
    """Return the largest font size that fits text within max_width."""
    for size in range(max_size, 28, -4):
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) < max_width:
            return font
    return load_font(28)


def draw_centered(draw, text: str, font, y: int, fill, shadow=(0, 0, 0)):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (WIDTH - tw) // 2
    draw.text((x + 2, y + 2), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


# ── SLIDE CREATION ────────────────────────────────────────────────────────────

def _draw_grid(draw, theme: dict):
    """Subtle dot-grid background pattern."""
    for x in range(0, WIDTH, 48):
        for y in range(0, HEIGHT, 48):
            draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=theme["grid"])


def create_tech_slide(
    term: str,
    explanation: str,
    theme: dict,
    counter: str = "",
) -> np.ndarray:
    """Create a professional dark-themed tech slide."""
    img = Image.new("RGB", (WIDTH, HEIGHT), theme["bg"])
    draw = ImageDraw.Draw(img)

    # Subtle dot grid
    _draw_grid(draw, theme)

    # ── Top badge bar ──────────────────────────────────────────────────────
    BAR_H = 72
    draw.rectangle([0, 0, WIDTH, BAR_H], fill=theme["card"])
    draw.line([(0, BAR_H), (WIDTH, BAR_H)], fill=theme["accent"], width=2)

    badge_font = load_font(30)
    draw.text((30, 22), theme["badge"], font=badge_font, fill=theme["accent"])

    if counter:
        small = load_font(26)
        bbox = draw.textbbox((0, 0), counter, font=small)
        draw.text((WIDTH - (bbox[2] - bbox[0]) - 30, 24),
                  counter, font=small, fill=theme["muted"])

    # ── Accent left strip ──────────────────────────────────────────────────
    draw.rectangle([0, BAR_H, 5, HEIGHT], fill=theme["accent"])

    # ── Term name (auto-sized to fit) ──────────────────────────────────────
    term_font = fit_text_font(draw, term, WIDTH - 120, max_size=84)
    term_y = BAR_H + (HEIGHT - BAR_H) // 2 - 105
    draw_centered(draw, term, term_font, term_y, theme["text"])

    # ── Divider ────────────────────────────────────────────────────────────
    div_y = term_y + 100
    draw.line([(80, div_y), (WIDTH - 80, div_y)], fill=theme["accent"], width=2)

    # ── Explanation (wrapped) ──────────────────────────────────────────────
    exp_font = load_font(38)
    wrapped = textwrap.wrap(explanation, width=56)
    y_pos = div_y + 22
    for line in wrapped[:3]:
        bbox = draw.textbbox((0, 0), line, font=exp_font)
        tw = bbox[2] - bbox[0]
        draw.text(((WIDTH - tw) // 2, y_pos), line, font=exp_font, fill=theme["muted"])
        y_pos += 52

    # ── Bottom watermark ───────────────────────────────────────────────────
    wm_font = load_font(22)
    wm_text = "Tech Learning  •  Subscribe for more"
    bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT - 36), wm_text, font=wm_font, fill=theme["grid"])

    return np.array(img)


def create_tech_intro(category: str, total: int, theme: dict) -> np.ndarray:
    return create_tech_slide(
        term=f"Learn {category.upper()}",
        explanation=f"Explore {total} essential {category.upper()} concepts in this video",
        theme=theme,
    )


def create_tech_outro(category: str, theme: dict) -> np.ndarray:
    return create_tech_slide(
        term="That's a Wrap!",
        explanation=f"You just leveled up your {category.upper()} knowledge. Like & Subscribe!",
        theme=theme,
    )


# ── AUDIO ─────────────────────────────────────────────────────────────────────

def create_tts(text: str, out_path: str, lang: str = "en") -> None:
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

def create_tech_video(
    category: str,
    items: list,
    output_path: str,
    lang: str = "en",
) -> str:
    """Build a complete tech learning video. Returns output_path."""
    theme = TECH_THEMES.get(category.lower(), DEFAULT_TECH_THEME)
    total = len(items)
    clips = []

    with tempfile.TemporaryDirectory() as tmp:

        # ── Intro ──
        print("  Creating intro...")
        intro_slide = create_tech_intro(category, total, theme)
        intro_mp3 = os.path.join(tmp, "intro.mp3")
        create_tts(
            f"Welcome! In this video you'll learn {total} key {category} concepts. Let's dive in!",
            intro_mp3, lang,
        )
        clips.append(make_clip(intro_slide, intro_mp3))

        # ── Concept slides ──
        for i, item in enumerate(items, 1):
            name = item["name"]
            explanation = item.get("explanation", f"{name} is a key concept in tech.")
            counter = f"{i} of {total}"
            print(f"  [{i}/{total}] {name}")

            slide = create_tech_slide(
                term=name,
                explanation=explanation,
                theme=theme,
                counter=counter,
            )
            mp3_path = os.path.join(tmp, f"item_{i}.mp3")
            # Pause between term and explanation for clarity
            create_tts(f"{name}. {explanation}", mp3_path, lang)
            clips.append(make_clip(slide, mp3_path))

        # ── Outro ──
        print("  Creating outro...")
        outro_slide = create_tech_outro(category, theme)
        outro_mp3 = os.path.join(tmp, "outro.mp3")
        create_tts(
            f"Great work! You've learned {total} {category} concepts. "
            "If you found this helpful, please like and subscribe for more tech learning videos!",
            outro_mp3, lang,
        )
        clips.append(make_clip(outro_slide, outro_mp3))

        # ── Render ──
        print(f"\n  Rendering → {output_path}")
        final = concatenate_videoclips(clips, method="compose")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        try:
            final.write_videofile(output_path, fps=FPS, codec="libx264",
                                  audio_codec="aac", logger=None)
        except TypeError:
            final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac")

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
        description="Create tech learning videos (AI, LLM, RAG, Database, MCP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tech_video_creator.py ai
  python tech_video_creator.py all
  python tech_video_creator.py rag --items 5
  python tech_video_creator.py all --output-dir tech_videos
        """,
    )
    parser.add_argument(
        "category",
        nargs="?",
        default="all",
        choices=list(TECH_THEMES.keys()) + ["all"],
        help="Category to generate (default: all)",
    )
    parser.add_argument("--config",      default="tech_content_config.json")
    parser.add_argument("--output-dir",  default="tech_videos")
    parser.add_argument("--lang",        default="en", help="gTTS language code")
    parser.add_argument("--items",       type=int, default=0, help="Max items (0=all)")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"❌  Config not found: {args.config}")
        return

    with open(args.config) as f:
        config = json.load(f)

    categories = list(config.keys()) if args.category == "all" else [args.category]

    print("=" * 60)
    print("  💻  Tech Learning Video Creator")
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

        print(f"\n🎯  {cat.upper()} — {len(items)} concepts")
        print(f"📁  → {output_path}")
        print("-" * 40)

        try:
            create_tech_video(
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
        print(f'      --niche "Technology and AI Education" \\')
        print(f'      --tone "clear, professional and educational" \\')
        print(f"      --category 28")
    print("=" * 60)


if __name__ == "__main__":
    main()
