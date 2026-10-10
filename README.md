# meowtext

A terminal editor for ASCII and ANSI banners. Type a line, pick a font, then add a colour gradient, an outline, or a drop shadow. The picture can be saved for a terminal, a browser, Kitty, IRC, or another program.

Three font sources:

- **FIGlet** (`.flf`), via the `figlet` program
- **TOIlet** (`.tlf`), via the `toilet` program
- **TheDraw** (`.tdf`), read directly. Colour, block, and outline fonts, including files that hold more than one font. Fonts already in `~/.config/tdfgo/fonts` are picked up.

## Run

```bash
python -m meowtext
```

```bash
python -m meowtext render "meow" -f "ANSI Shadow" --preset pop
python -m meowtext render "meow" -e toilet -f future --gradient ice
python -m meowtext render "MEOW" -e tdf -f NIRVANA --format png -o meow.png
python -m meowtext fonts -e tdf -q ice
```

With no flags, `render` prints ANSI on stdout. `--format` is `ansi`, `plain`, `html`, `json`, `png`, `kitty`, or `irc`. A piped program can pass the text on stdin.

In the editor, Ctrl+S saves, Ctrl+Y copies the selected text format, Ctrl+F filters fonts, and Ctrl+T jumps back to the text.

## Effects

Gradients repaint letters that are not part of a colour role. Outline can be a repeated symbol (shade or thick) or a line that follows the letter: contour, heavy, double, or half-blocks. The outline can be one flat colour from the colour list, or its own gradient. Drop shadow copies the letters, shifted. Presets: plain, rainbow, fire, ice, stamp, pop.

Animate plays in the preview only: hue cycle, marching gradient, outline pulse, sparkle, or a scanning band. Save and Copy use the frame on screen, not a movie.

A colour TheDraw font keeps the DOS palette index on each cell. Cells that share an index are one role, so the red parts stay related to the blue parts. Hue moves every linked role by the same amount: red and blue travel together and the gap between them stays. Greys have no hue and do not move. Turn Link off to edit one role's hue, saturation, and value on its own. Split sections makes each separate patch of that role its own copy, which you can then edit alone. Focus dims every other colour so the role you are editing is the one still bright. The saved file is never dimmed. `--hue 40` does the shared rotation from the command line.

TheDraw outline fonts are a separate thing: the file stores letters, and meowtext maps them with TheDraw's standard box-drawing table (`A` is `═`, `E` is `╒`, and so on). `@` and `O` are spaces. A row marked with `&` hangs below the baseline.

## Using the banner somewhere else

The editor is one frontend. The banner itself is a grid of cells, one terminal column each.

| Format | For |
| --- | --- |
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
