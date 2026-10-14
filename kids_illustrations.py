"""Deterministic subject illustrations; unknown subjects get a labeled word card."""
import re
import math
from PIL import Image, ImageDraw, ImageFont

SUBJECTS = ('lion', 'elephant', 'tiger', 'panda', 'rabbit', 'cat', 'dog',
            'apple', 'banana', 'orange', 'strawberry', 'grapes', 'carrot',
            'broccoli', 'car', 'airplane')


def identify_subject(text):
    aliases = {'aeroplane': 'airplane', 'plane': 'airplane', 'cars': 'car', 'bunny': 'rabbit'}
    text = re.sub(r'^(?:today:\s*|meet (?:the )?|this is (?:a )?)', '', text.strip(), flags=re.I).rstrip('!. ')
    for word in SUBJECTS + tuple(aliases):
        if re.fullmatch(re.escape(word) + r's?', text, re.I):
            return aliases.get(word, word)
    return None


def subject_illustration(name, fallback=True):
    subject = identify_subject(name)
    if subject is None and not fallback:
        return None
    im = Image.new('RGB', (600, 600), (232, 246, 232))
    d = ImageDraw.Draw(im)
    ink = (48, 64, 63)
    def eyes(y=270, x=300):
        for px in (x-48, x+48):
            d.ellipse((px-10,y-10,px+10,y+10),fill=ink)
        d.arc((x-28,y+20,x+28,y+55),0,180,fill=ink,width=5)
    if subject in {'lion','tiger','panda','cat','dog','rabbit'}:
        color = {'lion':'#efbc55','tiger':'#efa451','panda':'#fffef5','cat':'#e4a366','dog':'#bd8b66','rabbit':'#f4eee2'}[subject]
        if subject=='lion':
            for i in range(12):
                a=i*math.pi/6
                x,y=300+math.cos(a)*136,285+math.sin(a)*136
                d.ellipse((x-56,y-56,x+56,y+56),fill='#ae672f')
        if subject=='rabbit':
            for x in (225,335):
                d.rounded_rectangle((x-32,60,x+32,240),radius=32,fill=color)
                d.rounded_rectangle((x-15,83,x+15,210),radius=15,fill='#edb8b7')
        else:
            for x in (187,413):
                d.ellipse((x-48,140,x+48,240),fill=ink if subject=='panda' else color)
        d.ellipse((155,150,445,435),fill=color)
        if subject=='panda':
            for x in (250,350): d.ellipse((x-30,235,x+30,305),fill=ink)
            for x in (250,350): d.ellipse((x-7,260,x+7,274),fill='white')
        else: eyes()
        if subject=='tiger':
            for x in (240,290,340): d.polygon(((x,165),(x+20,165),(x+10,220)),fill=ink)
        if subject=='cat':
            for y in (310,330):
                d.line((160,y,240,y-5),fill=ink,width=3)
                d.line((360,y-5,440,y),fill=ink,width=3)
        d.ellipse((284,303,316,325),fill=ink)
    elif subject=='elephant':
        for x in (140,360): d.ellipse((x-65,170,x+105,390),fill='#91adb6')
        d.ellipse((185,125,415,375),fill='#adc4cb')
        d.rounded_rectangle((270,290,335,485),radius=28,fill='#adc4cb')
        d.arc((285,405,390,500),0,180,fill='#adc4cb',width=45)
        eyes(240)
    elif subject in {'apple','orange','strawberry','grapes'}:
        if subject=='grapes':
            for row in range(4):
                for col in range(4-row):
                    x=200+col*64+row*32;y=210+row*66
                    d.ellipse((x-42,y-42,x+42,y+42),fill='#9367b4')
        elif subject=='strawberry':
            d.polygon(((145,205),(455,205),(300,455)),fill='#e06c76')
            for x,y in ((220,240),(300,245),(380,240),(260,300),(340,300),(300,365)):
                d.ellipse((x-4,y-7,x+4,y+7),fill='#ffe6a2')
        else:
            d.ellipse((150,175,450,460),fill='#e77e5e' if subject=='apple' else '#edab48')
        d.line((300,190,310,125),fill='#86653c',width=14)
        d.ellipse((305,100,410,157),fill='#5e9f6e')
    elif subject=='banana':
        d.arc((120,65,450,465),5,170,fill='#efc84e',width=78)
        d.line((438,268,450,240),fill='#86653c',width=15)
    elif subject=='carrot':
        d.polygon(((190,210),(390,235),(265,480)),fill='#e9954f')
        for dx in (-55,0,55): d.line((290,230,290+dx,115),fill='#61a26d',width=22)
    elif subject=='broccoli':
        d.polygon(((270,260),(335,260),(355,465),(250,465)),fill='#88af65')
        for x,y in ((205,245),(285,190),(365,245)):
            d.ellipse((x-70,y-70,x+70,y+70),fill='#50916b')
    elif subject=='car':
        d.rounded_rectangle((110,270,490,395),radius=35,fill='#e68d69')
        d.polygon(((175,275),(230,190),(365,190),(430,275)),fill='#e68d69')
        d.polygon(((215,255),(245,211),(290,211),(290,255)),fill='#c6e5ed')
        d.polygon(((310,255),(310,211),(350,211),(390,255)),fill='#c6e5ed')
        for x in (195,410):
            d.ellipse((x-42,350,x+42,434),fill=ink)
            d.ellipse((x-18,374,x+18,410),fill='#dae4df')
    elif subject=='airplane':
        d.polygon(((95,300),(480,240),(520,270),(480,300),(95,335)),fill='#78a8c1')
        d.polygon(((250,290),(195,150),(260,160),(355,285)),fill='#6194b3')
        d.polygon(((260,300),(215,435),(280,410),(350,295)),fill='#6194b3')
        d.polygon(((120,310),(95,220),(145,230),(190,300)),fill='#6194b3')
    else:
        # Never substitute an unrelated animal or pretend a brand logo is verified.
        d.rounded_rectangle((70,130,530,440),radius=32,fill='#fffaf0',outline='#8bb3a0',width=4)
        try: font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf',34)
        except OSError: font=ImageFont.load_default(size=34)
        words=name.split();lines=[];line=''
        for word in words:
            candidate=(line+' '+word).strip()
            if d.textlength(candidate,font=font)>400 and line: lines.append(line);line=word
            else: line=candidate
        lines.append(line)
        for i,line in enumerate(lines[:5]):
            d.text((300-d.textlength(line,font=font)/2,170+i*45),line,font=font,fill=ink)
    return im
