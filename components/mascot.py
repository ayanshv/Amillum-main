"""Lightweight shared pixel companion; animations remain presentation-only."""
from nicegui import app, ui
from fastapi import HTTPException
from fastapi.responses import Response
from core.mascot import ROWS, png, strip


@app.get('/mascot/{state}/{kind}.png')
def sprite_asset(state: str, kind: str):
    if state not in ROWS or kind not in ('still','strip'):
        raise HTTPException(404)
    return Response(png(state) if kind == 'still' else strip(state), media_type='image/png',
                    headers={'Cache-Control':'public, max-age=86400'})


def mascot(state='idle', size=64, label=None, once=False):
    count=len(ROWS[state][0])
    duration=max(1.2,count*.18)
    return ui.element('div').classes('beaver-sprite' + (' beaver-once' if once else '')).props(
        'aria-hidden="true"' if label is None else f'role="img" aria-label="{label}"').style(
        f'--beaver-width:{size}px;--beaver-height:{size*1.2}px;'
        f'--beaver-strip:url(/mascot/{state}/strip.png);--beaver-still:url(/mascot/{state}/still.png);'
        f'--beaver-distance:-{size*(count-1 if once else count)}px;--beaver-duration:{duration}s;--beaver-frames:{max(1,count-1) if once else count};')
