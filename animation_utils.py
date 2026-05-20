#!/usr/bin/env python3
"""
Shared clip animation helpers for slideshow-style videos.
"""

import numpy as np
from PIL import Image

# moviepy v1 / v2 compat
try:
    from moviepy.editor import ImageClip
except (ImportError, ModuleNotFoundError):
    from moviepy import ImageClip


def _apply_zoom_pan(clip, zoom_ratio: float = 0.06, pan_pixels: int = 24):
    """
    Apply a subtle Ken Burns style zoom with a light diagonal pan.
    """
    duration = max(float(clip.duration or 0), 0.001)
    width, height = clip.size

    def _zoom(get_frame, t):
        frame = get_frame(t)
        progress = min(max(t / duration, 0.0), 1.0)
        eased = 1.0 - ((1.0 - progress) ** 2)
        zoom = 1.0 + zoom_ratio * eased

        crop_w = max(1, int(width / zoom))
        crop_h = max(1, int(height / zoom))
        max_x = max(width - crop_w, 0)
        max_y = max(height - crop_h, 0)

        x_shift = min(int(max(pan_pixels, 0) * eased), max_x)
        y_shift = min(int(max(pan_pixels // 2, 0) * eased), max_y)
        x1 = min(max_x // 2 + x_shift - (max_x // 4), max_x)
        y1 = min(max_y // 2 + y_shift - (max_y // 4), max_y)

        cropped = frame[y1:y1 + crop_h, x1:x1 + crop_w]
        return np.array(Image.fromarray(cropped).resize((width, height), Image.LANCZOS))

    if hasattr(clip, "fl"):
        return clip.fl(_zoom)
    return clip.transform(_zoom)


def _fadein(clip, duration: float = 0.30):
    try:
        return clip.fadein(duration)
    except Exception:
        return clip


def safe_clip_duration(
    audio_duration: float,
    pause_after_audio: float,
    min_duration: float,
    tail_buffer: float = 0.60,
):
    """
    Add a little safety margin after narration so clips don't cut on MP3 edges.
    """
    return max(float(audio_duration) + pause_after_audio + tail_buffer, min_duration)


def build_animated_clip(
    slide,
    duration: float,
    animate: bool = False,
    zoom_ratio: float = 0.06,
    pan_pixels: int = 24,
    fadein_duration: float = 0.30,
):
    clip = ImageClip(slide, duration=duration)
    if animate:
        clip = _apply_zoom_pan(clip, zoom_ratio=zoom_ratio, pan_pixels=pan_pixels)
    return _fadein(clip, fadein_duration)
