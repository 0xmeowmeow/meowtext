# What the rebuild preserves

The 1.1 editor uses visual inventories and comparison-first navigation, with saved-design integration. It reuses the accumulated font and effect engines.

| Existing work | Where it lives now |
| --- | --- |
| FIGlet, TOIlet and TheDraw glyph rendering | Original `engines/` and `catalog.py` |
| All six outline modes, per-letter geometry, sides, placement and offsets | Original `effects.py`, exposed in Decorate → Edges → Enter |
| Independent lettering and outline gradients, bands and speed | Decorate → Looks / Edges / Motion → Enter |
| Hue, march, pulse, sparkle, scan and trace | Original `compose.present` and `effects.py`, shared by the editor and `watch` |
| All trace paths and reveal behaviours | Decorate → Motion |
| Colour roles, linked colour rotation, independent HSV edits, splitting and focus | Original `palette.py`, exposed in Decorate → Looks → Enter |
| Cell patches and replacement letter glyphs | Original grid/project/layout representation, exposed through Paint in Looks → Enter |
| Custom palettes, presets, symbols, saved favourites and notes | Loaded from the existing configuration directory |
| Original editing interface | `meowtext legacy` |
| Experimental instruments, phosphor panels and readouts | Source retained; separate modules outside the main banner workflow |

No existing outline or animation functions were removed. The compositor, role operations and TheDraw renderer are retained. The effects entry point was extended so explicit solid fills and recolouring choices work on colour fonts. The new editor and standalone playback are tested against the same rendered frames.

Role splits now record their sequence in the editable project, so the separate sections can be reconstructed on reopen. Earlier projects without that field keep their existing behaviour. Preview focus never dims the exported artwork.

## Recovered versions

Two early snapshots were reconstructed from captured file snapshots, working backwards from the source preserved before rebuilding. Files not changed in those snapshots were inherited. They are recoveries, not a recreated original Git history.

- **[Recovered v0.1.0](https://github.com/0xmeowmeow/meowtext/tree/recovered-v0.1.0):** checkpoint 23 September 2026, 11:32 UTC. Its 12 original tests pass.
- **[Recovered early v0.2.0](https://github.com/0xmeowmeow/meowtext/tree/recovered-early-v0.2.0):** checkpoint 23 September 2026, 13:49 UTC. Its 16 original tests pass.

Later work is preserved in the current engine, the original editor, and a complete local pre-rebuild archive. Private session logs, reference images, notes and local saved designs are not included in the public repository.
