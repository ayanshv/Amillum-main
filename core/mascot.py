"""Render the supplied sprite atlas, shared by web and native presentation.

No generated replacement artwork. Crop coordinates omit the reference sheet's
captions. Flood only the connected neutral backdrop, preserving enclosed details.
"""
from collections import deque
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image

SIZE = (80, 96)
# State: x centres, top, bottom, cell half-width. Coordinates in the original atlas.
ROWS = {
    'idle': ([53,106,158,210,262,314,366,418], 196,267,25),
    'blink': ([522,599,676,753], 194,267,35),
    'look_left': ([872,924,976,1028],196,267,25),
    'look_right': ([1114,1165,1215,1265],196,267,24),
    'curious': ([58,122,187,253,318],389,467,30),
    'inspecting': ([412,477,543,610,676,741,806,862],389,467,30),
    'found': ([958,1024,1090,1170,1246],374,469,32),
    'thinking': ([55,111,166,223,279,335],569,649,26),
    'reading': ([439,504,570,636,702,769],587,650,31),
    'analyzing': ([886,941,994,1047,1098,1151,1205,1257],580,650,25),
    'asking': ([57,118,179,238,297,353],766,846,28),
    'flying': ([448,508,584,645,703,755,800,850],768,840,26),
    'success': ([943,998,1054,1116,1179,1244],772,845,28),
    'error': ([59,124,189,253,320],941,1008,30),
    'happy': ([476,535,594,653,712,771],941,1015,28),
    'confused': ([926,985,1046,1108,1167,1228],940,1015,28),
    'sleep': ([54,108,158,210,260,310,360,411],1091,1159,24),
    'jump': ([506,576,642,704,760,814],1077,1159,28),
    'landing': ([919,986,1055,1122,1187,1248],1100,1159,30),
}


@lru_cache(maxsize=1)
def atlas():
    return Image.open(Path(__file__).resolve().parents[1] / 'assets/mascot/beaver-reference.png').convert('RGBA')


@lru_cache(maxsize=128)
def frame(state='idle', index=0):
    centres, top, bottom, half = ROWS[state]
    centre = centres[index % len(centres)]
    image = atlas().crop((centre-half, top, centre+half, bottom))
    pixels = image.load()
    width, height = image.size
    pending = deque([(x, y) for x in range(width) for y in (0,height-1)] +
                    [(x, y) for y in range(height) for x in (0,width-1)])
    seen = set()
    while pending:
        x, y = pending.popleft()
        if (x,y) in seen or not (0 <= x < width and 0 <= y < height):
            continue
        seen.add((x,y))
        r,g,b,a = pixels[x,y]
        if a == 0 or (min(r,g,b) > 145 and max(r,g,b)-min(r,g,b) < 42):
            pixels[x,y] = (0,0,0,0)
            pending.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
    # A few tightly packed reference cells include a sliver of the next sprite.
    # Discard disconnected edge fragments, while retaining symbols above the body.
    remaining={(x,y) for x in range(width) for y in range(height) if pixels[x,y][3]}
    components=[]
    while remaining:
        seed=remaining.pop(); component={seed}; queue=[seed]
        while queue:
            x,y=queue.pop()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    point=(x+dx,y+dy)
                    if point in remaining:
                        remaining.remove(point);component.add(point);queue.append(point)
        components.append(component)
    if components:
        body=max(components,key=len); body_top=min(y for x,y in body)
        for component in components:
            if component is not body and min(y for x,y in component)>=body_top and any(x in (0,width-1) for x,y in component):
                for x,y in component: pixels[x,y]=(0,0,0,0)
    canvas = Image.new('RGBA', SIZE)
    canvas.alpha_composite(image, ((SIZE[0]-width)//2, SIZE[1]-height))
    return canvas


@lru_cache(maxsize=160)
def png(state='idle', index=0):
    out = BytesIO()
    frame(state,index).save(out,format='PNG')
    return out.getvalue()


@lru_cache(maxsize=24)
def strip(state):
    image = Image.new('RGBA',(SIZE[0]*len(ROWS[state][0]),SIZE[1]))
    for i in range(len(ROWS[state][0])):
        image.alpha_composite(frame(state,i),(i*SIZE[0],0))
    out=BytesIO(); image.save(out,format='PNG'); return out.getvalue()
