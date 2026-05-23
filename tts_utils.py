#!/usr/bin/env python3
"""
Shared text-to-speech helpers.
"""

import asyncio
import re

from gtts import gTTS

KIDS_TTS_VOICE = "en-IN-PrabhatIndicNeural"
KIDS_TTS_RATE = "-2%"
KIDS_TTS_PITCH = "-1Hz"
KIDS_TTS_VOLUME = "+0%"
_LANG_TO_VOICE = {
    "en": "en-IN-PrabhatIndicNeural",
    "en-GB": "en-IN-PrabhatIndicNeural",
    "en-AU": "en-IN-PrabhatIndicNeural",
}


def _normalize_tts_text(text: str) -> str:
    text = text.strip()
    text = text.replace("—", ", ").replace("–", ", ")
    text = text.replace("•", ". ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,;:.!?])\s*", r"\1 ", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1. \2", text)
    text = re.sub(r"([!?]){2,}", r"\1", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = text.strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def join_spoken_lines(*parts: str) -> str:
    cleaned = []
    for part in parts:
        part = _normalize_tts_text(part)
        if part:
            cleaned.append(part)
    return " ".join(cleaned)


def join_spoken_points(points: list[str]) -> str:
    transitions = ["First", "Also", "Another key point", "On top of that", "Finally"]
    spoken_parts = []
    for i, point in enumerate(points):
        point = _normalize_tts_text(point)
        if not point:
            continue
        lead = transitions[min(i, len(transitions) - 1)]
        spoken_parts.append(f"{lead}, {point}")
    return " ".join(spoken_parts)


async def _async_edge_tts(text: str, path: str, voice: str) -> None:
    import edge_tts

    await edge_tts.Communicate(
        text,
        voice,
        rate=KIDS_TTS_RATE,
        pitch=KIDS_TTS_PITCH,
        volume=KIDS_TTS_VOLUME,
    ).save(path)


def create_kids_tts(text: str, out_path: str, lang: str = "en") -> None:
    """
    Prefer a mature, confident neural female narrator with calm pacing,
    with gTTS as fallback.
    """
    text = _normalize_tts_text(text)
    voice = _LANG_TO_VOICE.get(lang, KIDS_TTS_VOICE)
    try:
        asyncio.run(_async_edge_tts(text, out_path, voice))
        return
    except Exception as e:
        print(f"    ⚠️  edge-tts failed ({e}), falling back to gTTS")
    gTTS(text=text, lang=lang, slow=False).save(out_path)
