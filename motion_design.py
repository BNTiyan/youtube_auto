"""Locally rendered editorial tech scenes with timed text and diagram motion."""
import math
import numpy as np
from PIL import Image, ImageDraw


class MotionSlide(np.ndarray):
    """An ndarray for existing callers, with an animated scene for video renderers."""
    def __new__(cls, scene):
        obj = np.asarray(scene.frame(8)).view(cls)
        obj.scene = scene
        return obj

    def __array_finalize__(self, source):
        self.scene = getattr(source, 'scene', None)


def ease(t, start=0, duration=.7):
    p = max(0., min(1., (t - start) / duration))
    return 1 - (1 - p) ** 3


def wrap_pixels(draw, text, font, width):
    lines = []
    line = ''
    for word in str(text).split():
        candidate = f'{line} {word}'.strip()
        if draw.textlength(candidate, font=font) > width and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


class TechScene:
    def __init__(self, title, body, theme, font, points=None, image=None, counter=''):
        self.title, self.body, self.font = title, body, font
        self.points, self.counter = points, counter
        self.accent = tuple(theme['accent'])
        self.image = image
        self.background = self._background()

    def _background(self):
        yy, xx = np.mgrid[0:720, 0:1280]
        glow = np.exp(-((xx-1030)**2 + (yy-250)**2) / 210000)
        arr = np.zeros((720, 1280, 3))
        for i, base in enumerate((10, 15, 27)):
            arr[:, :, i] = base + glow * (self.accent[i] * .13)
        image = Image.fromarray(arr.astype('uint8'))
        d = ImageDraw.Draw(image)
        for x in range(32, 1280, 40):
            for y in range(32, 720, 40):
                d.ellipse((x, y, x+1, y+1), fill=(31, 40, 57))
        d.line((64, 96, 1216, 96), fill=(43, 53, 73), width=1)
        d.text((64, 40), 'NAVADISHA  /  TECH EXPLAINED', font=self.font(19), fill=(165, 180, 204))
        d.text((64, 675), 'IDEAS MADE SIMPLE', font=self.font(16), fill=(119, 137, 162))
        return image

    def text(self, canvas, text, xy, size, color, t, delay=0, width=650, max_lines=4):
        d = ImageDraw.Draw(canvas)
        for chosen in range(size, 17, -2):
            font = self.font(chosen)
            lines = wrap_pixels(d, text, font, width)
            if len(lines) <= max_lines:
                break
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            last = lines[-1]
            while last and d.textlength(last + '...', font=font) > width:
                last = last[:-1]
            lines[-1] = last.rstrip() + '...'
        layer = Image.new('RGBA', canvas.size)
        ld = ImageDraw.Draw(layer)
        for index, line in enumerate(lines):
            p = ease(t, delay + index * .09)
            y = xy[1] + index * (chosen + 11) + round(22 * (1-p))
            ld.text((xy[0], y), line, font=font, fill=(*color, round(255*p)))
        canvas.paste(layer, (0, 0), layer)
        return len(lines) * (chosen + 11)

    def diagram(self, canvas, t):
        d = ImageDraw.Draw(canvas)
        x, y = 1010, 350
        d.rounded_rectangle((804, 161, 1216, 594), radius=28, fill=(17, 27, 44), outline=(49, 65, 86), width=1)
        if self.image is not None:
            from PIL import ImageOps
            photo = ImageOps.fit(self.image.convert('RGB'), (380, 220))
            canvas.paste(photo, (820, 178))
            y = 480
        else:
            # Orbiting signals and an animated circuit convey local processing.
            for radius in (80, 126, 166):
                d.ellipse((x-radius, y-radius, x+radius, y+radius), outline=(38, 55, 76), width=1)
            for i in range(6):
                angle = i*math.pi/3 + .12*math.sin(t*.5)
                nx, ny = x + math.cos(angle)*145, y + math.sin(angle)*145
                d.line((x, y, nx, ny), fill=(55, 79, 106), width=2)
                travel = (t*.32 + i/6) % 1
                px, py = x+(nx-x)*travel, y+(ny-y)*travel
                d.ellipse((px-4, py-4, px+4, py+4), fill=self.accent)
                d.ellipse((nx-8, ny-8, nx+8, ny+8), fill=(24, 39, 58), outline=self.accent, width=2)
        pulse = int(3 * math.sin(t*2))
        d.rounded_rectangle((x-50-pulse, y-40-pulse, x+50+pulse, y+40+pulse), radius=18, fill=(24, 47, 67), outline=self.accent, width=2)
        d.text((x-26, y-20), 'AI', font=self.font(34), fill=(239, 246, 255))
        if self.image is None:
            d.text((850, 550), 'INPUT   /   PROCESS   /   CREATE', font=self.font(17), fill=(155, 183, 206))

    def frame(self, t, duration=10):
        canvas = self.background.copy()
        d = ImageDraw.Draw(canvas)
        d.text((1135, 40), self.counter or 'EXPLAINER', font=self.font(16), fill=self.accent)
        if self.points is None:
            self.text(canvas, 'THE BIG IDEA', (64, 156), 19, self.accent, t)
            title_height = self.text(canvas, self.title, (60, 207), 64, (241, 246, 255), t, .12, 690, 3)
            self.text(canvas, self.body, (64, 231+title_height), 29, (174, 192, 214), t, .45, 670, 5)
            self.diagram(canvas, t)
        else:
            self.text(canvas, self.title, (60, 126), 46, (241, 246, 255), t, 0, 1140, 2)
            for i, point in enumerate(self.points[:5]):
                p = ease(t, .35 + i*.38)
                y = 255 + i*76 + round((1-p)*18)
                layer = Image.new('RGBA', canvas.size)
                ld = ImageDraw.Draw(layer)
                ld.rounded_rectangle((64, y, 1216, y+64), radius=14, fill=(23, 35, 53, int(255*p)))
                ld.text((86, y+16), f'{i+1:02}', font=self.font(24), fill=(*self.accent, int(255*p)))
                canvas.paste(layer, (0, 0), layer)
                self.text(canvas, str(point), (150, y+12), 25, (211, 224, 239), t, .35+i*.38, 1035, 1)
        d = ImageDraw.Draw(canvas)
        progress = max(0., min(t/max(duration, .01), 1.))
        d.rectangle((0, 716, int(1280*progress), 719), fill=self.accent)
        return np.asarray(canvas)


class KidsScene(TechScene):
    """Bright learning cards with gentle movement and a protected text area."""
    def _background(self):
        image = Image.new('RGB', (1280, 720), (255, 249, 235))
        d = ImageDraw.Draw(image)
        d.ellipse((850, -190, 1480, 470), fill=(224, 242, 230))
        d.ellipse((-160, 570, 350, 1050), fill=(255, 228, 186))
        d.rounded_rectangle((48, 36, 318, 84), radius=24, fill=(255, 225, 146))
        d.text((69, 49), 'LITTLE DISCOVERIES', font=self.font(20), fill=(78, 62, 44))
        d.text((64, 668), 'LOOK  /  LEARN  /  WONDER', font=self.font(17), fill=(94, 113, 108))
        return image

    def frame(self, t, duration=10):
        from PIL import ImageOps
        canvas = self.background.copy()
        d = ImageDraw.Draw(canvas)
        # Rounded teaching card: movement stays away from the fact text.
        d.rounded_rectangle((48, 130, 752, 620), radius=36, fill=(255, 255, 255), outline=(237, 225, 202), width=2)
        self.text(canvas, 'LET\'S EXPLORE!', (84, 170), 20, (31, 126, 108), t)
        title = self.title.replace('⭐', '').strip()
        h = self.text(canvas, title, (80, 221), 66, (32, 65, 70), t, .1, 630, 2)
        self.text(canvas, self.body, (84, 250+h), 29, (78, 99, 104), t, .5, 620, 4)
        if self.counter:
            self.text(canvas, self.counter, (1090, 48), 22, (31, 126, 108), t, 0, 170, 1)
        bob = int(9 * math.sin(t*1.6))
        if self.image is not None:
            photo = ImageOps.fit(self.image.convert('RGB'), (390, 390))
            mask = Image.new('L', photo.size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 389, 389), radius=40, fill=255)
            canvas.paste(photo, (808, 182+bob), mask)
        else:
            # A friendly open book, drawn locally without downloaded assets.
            d.ellipse((835, 549, 1185, 577), fill=(211, 224, 211))
            y = 270 + bob
            d.rounded_rectangle((820, y-25, 1010, y+220), radius=24, fill=(63, 159, 139))
            d.rounded_rectangle((1000, y-25, 1190, y+220), radius=24, fill=(63, 159, 139))
            d.rounded_rectangle((832, y-40, 1008, y+200), radius=20, fill=(255, 246, 212))
            d.rounded_rectangle((1008, y-40, 1178, y+200), radius=20, fill=(255, 240, 196))
            d.line((1008, y-25, 1008, y+190), fill=(219, 198, 145), width=3)
            for x in (860, 1040):
                for row in range(3):
                    d.rounded_rectangle((x, y+15+row*25, x+105, y+21+row*25), radius=3, fill=(196, 177, 125))
            d.ellipse((938, y+118, 950, y+130), fill=(32, 65, 70))
            d.ellipse((1065, y+118, 1077, y+130), fill=(32, 65, 70))
            d.arc((974, y+122, 1040, y+163), 0, 180, fill=(32, 65, 70), width=4)
        # Orbiting confetti stays within the illustration panel.
        for i, (x, y) in enumerate(((800, 160), (1195, 155), (1210, 600), (810, 590))):
            r = 7 + int(2*math.sin(t*2+i))
            cy = y + int(10*math.sin(t*1.5+i))
            color = ((242, 176, 77), (92, 169, 150), (228, 133, 111))[i%3]
            d.ellipse((x-r, cy-r, x+r, cy+r), fill=color)
        d.rounded_rectangle((440, 679, 840, 687), radius=4, fill=(222, 230, 214))
        progress = max(0., min(1., t/max(duration, .01)))
        if progress > 0:
            d.rounded_rectangle((440, 679, 440+int(400*progress), 687), radius=4, fill=(63, 159, 139))
        return np.asarray(canvas)
