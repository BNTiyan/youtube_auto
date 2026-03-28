#!/usr/bin/env python3
"""
Shared text-to-speech helpers.
"""

import asyncio

from gtts import gTTS

KIDS_TTS_VOICE = "en-US-AnaNeural"
_LANG_TO_VOICE = {
    "en": "en-US-AnaNeural",
    "en-GB": "en-GB-SoniaNeural",
    "en-AU": "en-AU-NatashaNeural",
}


async def _async_edge_tts(text: str, path: str, voice: str) -> None:
    import edge_tts

    await edge_tts.Communicate(text, voice).save(path)


def create_kids_tts(text: str, out_path: str, lang: str = "en") -> None:
    """
    Prefer Microsoft's neural child-like voice, with gTTS as fallback.
    """
    voice = _LANG_TO_VOICE.get(lang, KIDS_TTS_VOICE)
    try:
        asyncio.run(_async_edge_tts(text, out_path, voice))
        return
    except Exception as e:
        print(f"    ⚠️  edge-tts failed ({e}), falling back to gTTS")
    gTTS(text=text, lang=lang, slow=False).save(out_path)
