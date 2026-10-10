# meowtext

A terminal editor for ASCII and ANSI banners. Type a line, pick a font, then add a colour gradient, an outline, or a drop shadow. The picture can be exported for a terminal, a browser, Kitty, IRC, or another program. The editable banner is a `.meowtext` project.

Three font sources:

- **FIGlet** (`.flf`), via the `figlet` program. The system set in `/usr/share/figlet`, plus extra fonts in `~/.config/meowtext/fonts`.
- **TOIlet** (`.tlf`), via the `toilet` program, from the same two directories.
- **TheDraw** (`.tdf`), read directly. Colour, block, and outline fonts, including files that hold more than one font. Fonts already in `~/.config/tdfgo/fonts` are picked up. The list is split into block, outline, and colour, and colour copies such as Nuclear Blue and Nuclear Cyan share one row.

`meowtext fonts --fetch` downloads the extra FIGlet collection (contributed, JavE, international, C64, Obanner, and the rest of the figlet.org set) into `~/.config/meowtext/fonts`. Names the system already has are left as they are. On this machine the TOIlet fonts in that collection were already installed.

## Run

```bash
python -m meowtext
python -m meowtext path/to/banner.meowtext
```

```bash
python -m meowtext render "meow" -f "ANSI Shadow" --preset pop
python -m meowtext render "meow" -e toilet -f future --gradient ice
python -m meowtext render "MEOW" -e tdf -f NIRVANA --format png -o meow.png
python -m meowtext fonts -e tdf -q ice
```

With no flags, `render` prints ANSI on stdout. `--format` is `ansi`, `plain`, `html`, `json`, `png`, `kitty`, or `irc`. A piped program can pass the text on stdin.

```bash
python3 -m ui_board
```

That opens the reference boards at <http://127.0.0.1:8765/>. Folders named along `tui`, `inspo`, and `mood` are the shelves. Each folder is a contact sheet: Include keeps a picture for the editor, Leave out sets it aside, and the note is the instruction for that picture. The choices are saved in `ui_board/notes.json`.

The banner uses the full width. The words sit above it. Under it is one grid. Each control has its letter printed on it, in gold. That letter changes the setting and the banner updates. Shift plus the same letter goes the other way. The arrows move through the grid the way it is drawn: up and down stay in a column, left and right cross to the other column. Enter changes the highlighted setting, and backspace goes back. `1` through `6` change section (Look, Outline, Shadow, Colour, Animate, Notes), and so do `[` and `]`. The numbers are printed on the section row. Font search stays closed until Ctrl+F. It opens in the band under the banner, so the picture keeps its height. Type a name, and up, down, page up, and page down walk the matches while the banner shows the font. Enter keeps it. Ctrl+T jumps to the words. Esc comes back to the grid. These keys work while you are typing.

| Key | Does |
| --- | --- |
| Ctrl+S | Save a `.meowtext` project. The name comes from the words and the font. A file that is already there is left alone, and the new one gets the next number. Saving again updates the file this session created. |
| Ctrl+B | Save the whole setup to favourites (`~/.config/meowtext/favourites`). Recall one from the Look section. |
| Ctrl+E | Paint. Arrows move. Type a character to put it down. `[` and `]` change the paint colour. `,` and `.` change letter. Tab switches between the banner and one letter. |
| Ctrl+Y | Copy the export format. |
| Ctrl+O | Open the `.meowtext` path in the export box. |
| 1–6, `[` `]` | Change section. A letter changes that setting. Shift plus the letter goes back. Arrows move. Enter changes the highlighted one. |
| Ctrl+F | Search fonts. Type, then up, down, page up, and page down. Enter keeps the font. |
| Ctrl+T / Esc | Jump to the words. Esc comes back to the settings. |

Export and Copy write the picture in the format next to the path box. They use the frame on screen.

## Instruments

The included reference pictures share six themes: phosphor, instrument, glyph, living structure, object, and state. Frames, brackets, repeating borders, plates, readouts, and ticks are drawn on the cell grid. Dials, gauges, faders, and lamps are real pixels, placed with the kitty graphics protocol the way eventhorizon places its picture, because a circle and a smooth meter do not survive being bent onto characters. Inks are green, amber, cyan, violet, and magenta.

```bash
python3 -m meowtext.instruments
```

## Effects

Gradients repaint letters that are not part of a colour role. A gradient can be smooth or hard bands. In Colour, each stop's hue, saturation, and value can be changed, and `+` and `-` add or remove a stop. The stops travel with the project. Named palettes in `~/.config/meowtext/palettes.json` show up in the palette control, and named looks in `presets.json` show up beside them.

The outline has its own palette, its own direction, and its own cycle speed. Direction can run left, right, up, down, or on a diagonal, and the outline can be set to the opposite of the letters, so a dark end of the letters gets a light rim. On the Outline section, with the direction still left to right, shift+d lands on that opposite rim. Hue cycle rotates the colours in place. March slides the gradient along its direction. It can sit on any mix of the top, bottom, left, and right, a chosen number of cells out, outside the letters, inside the holes, or both. Whole word rims the banner as one shape. Each letter rims every letter, so neighbours do not share an edge. The outline can also be shifted, the way the shadow is. Symbols are the block, box-drawing, and braille sets, plus any character listed in `~/.config/meowtext/symbols.json`.

Drop shadow copies the letters, shifted. Built-in looks: plain, rainbow, fire, ice, stamp, pop.

Animate plays in the preview: hue cycle, marching gradient, outline pulse, sparkle, a scanning band, or a trace. A trace can run around the outline, across the rows, one letter fully then the next, or out from the centre. It can draw the letters on and leave them, or be a bright point that keeps moving. Speed, direction (forward, backward, ping-pong), how far the colour travels, and which layer moves (letters, outline, colour roles, or everything) are all editable. The project remembers the settings. Export keeps the frame on screen, not a movie.

A colour TheDraw font keeps the DOS palette index on each cell. Cells that share an index are one role, so the red parts stay related to the blue parts. Hue moves every linked role by the same amount: red and blue travel together and the gap between them stays. Greys have no hue and do not move. Turn Link off to edit one role's hue, saturation, and value on its own. Split sections makes each separate patch of that role its own copy, which you can then edit alone. Focus dims every other colour so the role you are editing is the one still bright. The saved picture is never dimmed. `--hue 40` does the shared rotation from the command line.

TheDraw outline fonts are a separate thing: the file stores letters, and meowtext maps them with TheDraw's standard box-drawing table (`A` is `═`, `E` is `╒`, and so on). `@` and `O` are spaces. A row marked with `&` hangs below the baseline.

Notes are a page in the editor. They are stored in the project and in a favourite.

Painting the banner replaces cells on the picture you see. Painting a letter changes that character for this banner and places the letters separately, so the font file is not rewritten.

## Using the banner somewhere else

The editor is one frontend. The banner itself is a grid of cells, one terminal column each.

| Format | For |
| --- | --- |
| `.meowtext` | the project. Words, font, both gradients, outline, shadow, colour roles, animation, notes, painted cells, and edited letters. `"meowtext": "project"`. |
| ANSI | terminals, shell scripts, other TUIs |
| plain | anywhere colour would be stripped |
| HTML | a browser |
| JSON | another program. `"meowtext": 1`, cells of `{c, fg, bg}`, plus `fg_slot` / `roles` / `hue` when the banner has colour roles |
| PNG | an image |
| Kitty | a [Kitty graphics](https://sw.kovidgoyal.net/kitty/graphics-protocol/) sequence. `cat file.kitty` inside Kitty shows it |
| IRC | mIRC colour codes |

JSON is the interchange for a second interface, for example a Charmbracelet / Bubble Tea client, without linking that UI to this one. The Python call is `meowtext.render_banner`.

```python
from meowtext import render_banner
from meowtext.effects import BannerStyle

banner = render_banner("meow", "figlet", "ANSI Shadow", BannerStyle(gradient="sunset", shadow=True))
```

Letter case in a TheDraw font is often uppercase only. Missing lowercase is drawn from the uppercase glyph, and the status line says when that happened.
