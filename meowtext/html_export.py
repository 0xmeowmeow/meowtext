"""HTML5 text cells with a shared colour palette cycled by JavaScript.

The compositor supplies colour tracks, never images. Characters remain real,
selectable text; geometric terminal glyphs use CSS rectangles to join exactly
at cell boundaries. Other characters use the embedded DejaVu font.
"""
from __future__ import annotations

import base64
import html
import json
from pathlib import Path
import unicodedata

from meowtext import raster
from meowtext.grid import Grid


def _rectangles(char, size=18):
    """Merge the shared geometric glyph's horizontal runs into CSS rectangles."""
    mask = raster._mask(char, size)
    active, rectangles = {}, []
    for y in range(mask.height + 1):
        runs = set()
        x = 0
        while y < mask.height and x < mask.width:
            if not mask.getpixel((x, y)):
                x += 1
                continue
            start = x
            while x < mask.width and mask.getpixel((x, y)):
                x += 1
            runs.add((start, x-start))
        for run in active.keys() - runs:
            rectangles.append((run[0], active.pop(run), run[1], y))
        for run in runs - active.keys():
            active[run] = y
    return [(x, y, w, end-y) for x, y, w, end in rectangles]


def _geometric(char):
    return len(char) == 1 and 0x2500 <= ord(char) <= 0x259f and "DIAGONAL" not in unicodedata.name(char, "")


def html_player(frames: list[Grid], poster: Grid, plan) -> str:
    width = max([poster.width] + [g.width for g in frames])
    height = max([poster.height] + [g.height for g in frames])
    cw, ch = raster.cell_size()
    colours, colour_ids, tracks, track_ids, initial = [], {}, [], {}, []
    characters, character_ids, changes = [], {}, []

    def colour_id(colour, fallback):
        value = colour.hex() if colour else fallback
        if value not in colour_ids:
            colour_ids[value] = len(colours)
            colours.append(value)
        return colour_ids[value]

    def character_id(char):
        char = char or " "
        if char not in character_ids:
            character_ids[char] = len(characters)
            characters.append(char)
        return character_ids[char]

    def track(values, start):
        values = tuple(values)
        if len(set(values)) == 1:
            values = values[:1]
        key = (values, start)
        if key not in track_ids:
            track_ids[key] = len(tracks)
            tracks.append(values)
            initial.append(start)
        return track_ids[key]

    cells = []
    for y in range(height):
        row = []
        for x in range(width):
            cell = poster.get(x, y)
            samples = [g.get(x, y) for g in frames]
            fg = track([colour_id(c.fg, "#e6e6e6") for c in samples], colour_id(cell.fg, "#e6e6e6"))
            bg = track([colour_id(c.bg, "#000000") for c in samples], colour_id(cell.bg, "#000000"))
            glyphs = [character_id(c.char) for c in samples]
            char_id = character_id(cell.char)
            if any(c != char_id for c in glyphs):
                changes.append((y*width+x, glyphs))
            row.append((char_id, fg, bg))
        cells.append(row)

    geometry, geometry_css = {}, []
    for char in characters:
        if not _geometric(char):
            continue
        name = f"g{len(geometry)}"
        geometry[char] = name
        rectangles = _rectangles(char)
        layers = ",".join(f"linear-gradient(currentColor,currentColor) {x}px {y}px/{w}px {h}px no-repeat" for x,y,w,h in rectangles)
        geometry_css.append(f".{name}::after{{background:{layers or 'none'}}}")

    rows = []
    for row in cells:
        pieces = []
        for char_id, fg, bg in row:
            char = characters[char_id]
            shape = f" geom {geometry[char]}" if char in geometry else ""
            pieces.append(f'<span class="cell{shape}" style="color:var(--c{fg});background-color:var(--c{bg})"><span class="glyph">{html.escape(char)}</span></span>')
        rows.append("".join(pieces))
    variables = ";".join(f"--c{i}:{colours[c]}" for i,c in enumerate(initial))
    payload = json.dumps({"colours":colours, "tracks":tracks, "characters":characters,
                          "changes":changes, "geometry":geometry, "count":len(frames),
                          "duration":plan.duration, "loop":plan.loop}, separators=(",", ":")).replace("<", "\\u003c")
    font = base64.b64encode(Path(raster.MONO_FONT).read_bytes()).decode("ascii")
    animated = len(frames) > 1
    # Licence text accompanies the embedded font; there are no network assets.
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meowtext artwork</title><style>
@font-face{{font-family:MeowtextMono;src:url(data:font/ttf;base64,{font}) format("truetype");font-display:block}}
html{{color-scheme:dark;background:#000;color:#eee;font:14px system-ui}}
body{{margin:0;padding:16px}} #viewport{{overflow:auto;max-width:100%;width:{max(1,width*cw)}px}}
#art{{font:{18}px/{ch}px MeowtextMono,monospace;white-space:pre;margin:0;width:{max(1,width*cw)}px;height:{max(1,height*ch)}px;transform-origin:top left;{variables}}}
.cell{{display:inline-block;position:relative;width:{cw}px;height:{ch}px;overflow:hidden;vertical-align:top}}
.glyph{{position:absolute;inset:0;font:inherit}} .geom .glyph{{opacity:0}}
.geom::after{{content:"";position:absolute;inset:0;pointer-events:none}}
{''.join(geometry_css)}
nav{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:16px}} button{{font:inherit;padding:8px 14px;cursor:pointer}}
details{{margin-top:16px;max-width:80ch}} details pre{{white-space:pre-wrap;font:12px/1.5 monospace}}
[hidden]{{display:none!important}}
</style></head><body>
<div id="viewport"><pre id="art" aria-label="Meowtext lettering">{chr(10).join(rows)}</pre></div>
<nav><button id="pause" type="button" {'hidden' if not animated else ''}>Pause</button><button id="replay" type="button" {'hidden' if not animated else ''}>Replay</button><button id="size" type="button">Actual size</button><span id="state" role="status"></span></nav>
<noscript>The complete still artwork is shown. Enable JavaScript for colour cycling and motion.</noscript>
<details><summary>Embedded font licence</summary><pre>{html.escape(FONT_LICENSE)}</pre></details>
<script id="meowtext-animation" type="application/json">{payload}</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('meowtext-animation').textContent);
const art=document.getElementById('art'), cells=[...art.querySelectorAll('.cell')];
const pause=document.getElementById('pause'), state=document.getElementById('state');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
let index=0, running=data.count>1&&!reduced.matches, elapsed=0, last=performance.now();
function paintFrame(number) {{
  data.tracks.forEach((track,n)=>art.style.setProperty('--c'+n,data.colours[track[track.length===1?0:number]]));
  for(const [n,track] of data.changes) {{
    const char=data.characters[track[number]], cell=cells[n];
    cell.firstElementChild.textContent=char;
    cell.className='cell'+(data.geometry[char]?' geom '+data.geometry[char]:'');
  }}
  art.dataset.frame=String(number);
}}
function label() {{pause.textContent=running?'Pause':'Play';state.textContent=data.count===1?'Still artwork':running?'Playing':index===data.count-1&&!data.loop?'Finished':'Paused';}}
if(running)paintFrame(0);
pause.onclick=()=>{{if(!running&&index===data.count-1&&!data.loop){{index=0;elapsed=0;paintFrame(0);}}running=!running;last=performance.now();label();}};
document.getElementById('replay').onclick=()=>{{index=0;elapsed=0;paintFrame(0);running=data.count>1;last=performance.now();label();}};
reduced.addEventListener('change',event=>{{if(event.matches){{running=false;label();}}}});
document.addEventListener('visibilitychange',()=>last=performance.now());
function tick(now) {{
  if(running&&!document.hidden) {{
    elapsed+=now-last;
    if(elapsed>=data.duration) {{
      index+=Math.floor(elapsed/data.duration);elapsed%=data.duration;
      if(!data.loop&&index>=data.count-1){{index=data.count-1;running=false;label();}}
      else index%=data.count;
      paintFrame(index);
    }}
  }}
  last=now;requestAnimationFrame(tick);
}}
const viewport=document.getElementById('viewport');let fit=true;
function resize(){{const scale=fit?Math.min(1,viewport.clientWidth/{max(1,width*cw)}):1;art.style.transform=`scale(${{scale}})`;viewport.style.height=({max(1,height*ch)}*scale)+'px';document.getElementById('size').textContent=fit?'Actual size':'Fit to page';}}
document.getElementById('size').onclick=()=>{{fit=!fit;resize();}};new ResizeObserver(resize).observe(viewport);
label();requestAnimationFrame(tick);
</script></body></html>'''


FONT_LICENSE = 'Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\nUpstream-Name: DejaVu fonts\nUpstream-Author: Stepan Roh <src@users.sourceforge.net> (original author),\n                  see /usr/share/doc/fonts-dejavu-core/AUTHORS for full list\nSource: https://dejavu-fonts.github.io/\n\nFiles: *\nCopyright: Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved.\n Bitstream Vera is a trademark of Bitstream, Inc.\n DejaVu changes are in public domain.\nLicense: bitstream-vera\n Permission is hereby granted, free of charge, to any person obtaining a copy\n of the fonts accompanying this license ("Fonts") and associated\n documentation files (the "Font Software"), to reproduce and distribute the\n Font Software, including without limitation the rights to use, copy, merge,\n publish, distribute, and/or sell copies of the Font Software, and to permit\n persons to whom the Font Software is furnished to do so, subject to the\n following conditions:\n .\n The above copyright and trademark notices and this permission notice shall\n be included in all copies of one or more of the Font Software typefaces.\n .\n The Font Software may be modified, altered, or added to, and in particular\n the designs of glyphs or characters in the Fonts may be modified and\n additional glyphs or characters may be added to the Fonts, only if the fonts\n are renamed to names not containing either the words "Bitstream" or the word\n "Vera".\n .\n This License becomes null and void to the extent applicable to Fonts or Font\n Software that has been modified and is distributed under the "Bitstream\n Vera" names.\n .\n The Font Software may be sold as part of a larger software package but no\n copy of one or more of the Font Software typefaces may be sold by itself.\n .\n THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS\n OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF MERCHANTABILITY,\n FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF COPYRIGHT, PATENT,\n TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL BITSTREAM OR THE GNOME\n FOUNDATION BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, INCLUDING\n ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES,\n WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF\n THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM OTHER DEALINGS IN THE\n FONT SOFTWARE.\n .\n Except as contained in this notice, the names of Gnome, the Gnome\n Foundation, and Bitstream Inc., shall not be used in advertising or\n otherwise to promote the sale, use or other dealings in this Font Software\n without prior written authorization from the Gnome Foundation or Bitstream\n Inc., respectively. For further information, contact: fonts at gnome dot\n org.\n\n'
