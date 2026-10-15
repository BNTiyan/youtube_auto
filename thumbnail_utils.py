"""Dedicated thumbnail composition using the video's existing approved artwork."""
import os
from PIL import Image, ImageDraw, ImageOps


def create_thumbnail(video_path, title, images, load_font):
    canvas = Image.new('RGB', (1280, 720), '#101827')
    draw = ImageDraw.Draw(canvas)
    if images:
        art = ImageOps.contain(images[0].convert('RGB'), (590, 620))
        canvas.paste(art, (670 + (590-art.width)//2, (720-art.height)//2))
    width = 560 if images else 1120
    words = str(title).strip().split()
    if not words:
        raise ValueError('Thumbnail needs a topic title')
    for size in range(96, 19, -2):
        font = load_font(size)
        lines = []
        line = ''
        for word in words:
            candidate = f'{line} {word}'.strip()
            if line and draw.textlength(candidate, font=font) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
        if len(lines)*(size+16) <= 520 and all(draw.textlength(line, font=font) <= width for line in lines):
            break
    else:
        raise ValueError('Thumbnail title is too long to fit legibly')
    y = (720-len(lines)*(size+16))//2
    draw.rounded_rectangle((64, y-35, 200, y-23), radius=6, fill='#ffcd38')
    for line in lines:
        draw.text((64, y), line, font=font, fill='white', stroke_width=1)
        y += size+16
    path = os.path.splitext(video_path)[0] + '_thumb.jpg'
    canvas.save(path, 'JPEG', quality=90, optimize=True)
    return path
