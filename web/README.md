# Browser edition

The browser runs the existing Python compositor, palette, effects, discovery and export code in a module worker using [Pyodide 314.0.7](https://pyodide.org/en/stable/usage/index.html). Preview frames and downloads use the same Pillow rasteriser. PyFIGlet replaces the desktop FIGlet subprocess; TheDraw imports use the original parser. TOIlet and terminal integration remain desktop features. Existing project patches, letter overrides, colour roles and notes are preserved. The browser includes cell painting; individual glyph editing and role splitting are currently desktop controls.

```sh
.venv/bin/python web/build.py --download-runtime
.venv/bin/python -m http.server 8000 --directory web/dist
```

The build bundles 569 renderable fonts from PyFIGlet 1.0.4, creates the comparison index and effect specimens with Meowtext, and packages an explicit list of shared modules in `runtime.zip`. `vendor/` retains the PyFIGlet wheel, DejaVu font and their licenses. The PyFIGlet wheel SHA-256 is `65b57b7a8e1dff8a67dc8e940a117238661d5e14c3e49121032bd404d9b2b39f`.

The first build downloads the exact runtime files recorded in `runtime-manifest.json` and verifies their SHA-256 hashes. They remain in ignored `dist/pyodide` and are served from the same origin, including their license. Builds without `--download-runtime` require those verified files already to be present. Use a current browser with WebAssembly and module workers. No user content is sent to a server. The first visit downloads approximately 16 MB before HTTP compression; normal browser caching reuses runtime files. A failed startup reports the reason in the editor.

Deploy the contents of `dist/`, including `.htaccess`, beneath `/meowtext/`. Apache needs `.mjs` served as JavaScript and `.wasm` as `application/wasm`; the included configuration declares both. App files revalidate to avoid stale worker/code combinations. Exported HTML is self-contained and works without this runtime or a network connection.

The editor stores the latest FIGlet draft in browser local storage and offers explicit project downloads. Imported TheDraw font files stay in the worker for the life of the tab; import the original font again when reopening a project. Browser limits (text length, cell count, motion speed, border reach, animation frames and image memory) report errors instead of clipping artwork or silently dropping effects.

Browser checks should cover startup, arrow-key previews, comparisons/backtracking, search synonyms, successive Tune changes, animation, pausing to export the visible PNG frame, standalone HTML playback without network, project round trips, font import, painting, error recovery, and mobile overflow. Desktop verification remains `.venv/bin/python -m unittest discover -s tests -q` plus an isolated Kitty window.
