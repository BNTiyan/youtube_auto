#!/usr/bin/env python3
"""
Shared text-to-speech helpers.
"""

import asyncio
import re

from gtts import gTTS

KIDS_TTS_VOICE = "en-IN-PrabhatNeural"
KIDS_TTS_RATE = "-2%"
KIDS_TTS_PITCH = "-1Hz"
KIDS_TTS_VOLUME = "+0%"
_LANG_TO_VOICES = {
    "en": [
        "en-IN-PrabhatNeural",
        "en-IN-NeerjaNeural",
        "en-US-GuyNeural",
    ],
    "hi": [
        "hi-IN-MadhurNeural",
        "hi-IN-SwaraNeural",
        "en-IN-PrabhatNeural",
    ],
    "te": [
        "te-IN-ShrutiNeural",
        "en-IN-PrabhatNeural",
        "en-IN-NeerjaNeural",
    ],
    "en-GB": [
        "en-GB-RyanNeural",
        "en-IN-PrabhatNeural",
        "en-US-GuyNeural",
    ],
    "en-AU": [
        "en-AU-WilliamNeural",
        "en-IN-PrabhatNeural",
        "en-US-GuyNeural",
    ],
}
_GTTS_LANG = {
    "en": "en",
    "hi": "hi",
    "te": "te",
    "en-GB": "en",
    "en-AU": "en",
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


def _candidate_voices(lang: str) -> list[str]:
    voices = list(_LANG_TO_VOICES.get(lang, []))
    if KIDS_TTS_VOICE not in voices:
        voices.append(KIDS_TTS_VOICE)
    return voices


def create_kids_tts(text: str, out_path: str, lang: str = "en") -> None:
    """
    Prefer a mature Indian English neural narrator, with gTTS as fallback.
    """
    text = _normalize_tts_text(text)
    last_error = None
    for voice in _candidate_voices(lang):
        try:
            asyncio.run(_async_edge_tts(text, out_path, voice))
            return
        except Exception as e:
            last_error = e
    if last_error is not None:
        print(f"    ⚠️  edge-tts failed ({last_error}), falling back to gTTS")
    gtts_lang = _GTTS_LANG.get(lang, "en")
    gTTS(text=text, lang=gtts_lang, slow=False).save(out_path)
