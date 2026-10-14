#!/usr/bin/env python3
"""Render a short, silent visual preview locally without LLM, TTS, or uploads."""
import argparse
from pathlib import Path
from PIL import Image
from moviepy import VideoFileClip
from animation_utils import build_animated_clip
from tech_video_creator import (
    TECH_THEMES, create_tech_intro, create_tech_slide,
    create_points_slide, create_tech_outro, concatenate_videoclips,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='videos/animated_visual_preview.mp4')
    parser.add_argument('--style', choices=['tech', 'kids'], default='tech')
    args = parser.parse_args()
    theme = TECH_THEMES['ai']
    frames = [
        create_tech_slide("Your ideas. Your machine.", "A quick guide to creating videos with local AI.", theme),
        create_tech_slide('Local AI', 'Run a language model on your own computer to draft scripts and video descriptions.', theme),
        create_points_slide('How it works', ['Choose a topic', 'Draft a script locally', 'Render and review the video'], theme),
        create_tech_outro('ai', theme),
    ]
    if args.style == 'kids':
        from video_creator import create_slide, THEMES
        theme = THEMES['animals']
        frames = [
            create_slide('Hello, explorers!', 'Every day is a new chance to discover something amazing.', theme),
            create_slide('Meet the lion', 'Lions live in family groups called prides.', theme, counter='01 / 02'),
            create_slide('Listen closely!', "A lion's roar can travel a long way across the grasslands.", theme, counter='02 / 02'),
            create_slide('Great job!', 'Keep asking questions. There is so much more to learn!', theme),
        ]
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frames[1]).save(output.with_suffix('.png'))
    clips = [build_animated_clip(frame, duration=4, animate=False) for frame in frames]
    final = concatenate_videoclips(clips, method='compose')
    try:
        final.write_videofile(str(output), fps=24, codec='libx264', audio=False, logger=None)
    finally:
        final.close()
        for clip in clips:
            clip.close()
    with VideoFileClip(str(output)) as check:
        assert check.size == [1280, 720]
        assert 15.9 <= check.duration <= 16.1
        check.get_frame(6)
        print(f'Validated {check.duration}s preview at {check.size}: {output}')


if __name__ == '__main__':
    main()
