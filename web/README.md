# Browser edition

The browser studio carries the accepted Meowtext inventory into the web: a full-width artwork, three banks of real specimens, large comparison previews, immediate arrow-key selection and details one Enter away. Its headings and logo are rendered lettering. The desktop's approved design remains the source of this arrangement.

Edges includes six shadow specimens plus No shadow. Border and shadow tiles remain independently selected, and Enter on a shadow goes directly to its live controls.

Tune expands below the artwork and above the specimen banks. Controls preview changes as you type or adjust colours, without covering the artwork. Long settings scroll with the preview still visible, including on phones. Escape returns focus to the specimen or button that opened Tune; Undo restores both the artwork and open controls.

A module worker runs the shared Python compositor, palette, discovery, rasteriser and exports through Pyodide 314.0.7. PyFIGlet reads FIGlet and TOIlet fonts in place of their desktop subprocesses. TheDraw uses the same colour, block and outline parser as the desktop. Individual glyph editing and role splitting remain desktop controls; existing project patches, letter overrides, roles and notes survive browser project round trips.

## Build and serve

```sh
# The build needs Pillow, fonttools and Brotli (the latter two subset the UI font
# and precompress the runtime). These are build dependencies, not desktop ones.
.venv/bin/python -m pip install 'fonttools[woff]' brotli
.venv/bin/python web/build.py --download-runtime
.venv/bin/python -m http.server 8000 --directory web/dist
```

Omit `--download-runtime` after the first build. Runtime files are pinned by SHA-256 in `runtime-manifest.json` and verified on every build. The worker also verifies its startup payloads where Web Crypto is available. `vendor/` retains the PyFIGlet 1.0.4 wheel, DejaVu font and their licenses. The wheel SHA-256 is `65b57b7a8e1dff8a67dc8e940a117238661d5e14c3e49121032bd404d9b2b39f`. `vendor/catalogue-fonts.json` pins the additional public font archive and its upstream revisions. `vendor/Font-credits.txt` preserves provenance and points to the original notices. Four FIGlet files cannot render the index sample (one has a malformed header), and three TheDraw members contain no visible sample; the original font files are retained in the archive. No installed user font cache is copied into publication. `lettering.json` holds the glyph grids for the accepted inventory headings, so builds do not require TOIlet.

The build creates:

- A pre-rendered animated sample and first font specimens, embedded catalogue metadata, and a subset of DejaVu for stable UI metrics.
- A roughly 600 KB renderer archive containing the shared modules, catalogue metadata and starter fonts. Remaining files download individually with SHA-256 checks when used. The catalogue contains 881 FIGlet, 24 TOIlet and 3,708 TheDraw fonts and colour variants. Collection filters supplement comparison-first browsing; Browse all keeps the variants.
- Versioned Pyodide files and precompressed gzip/Brotli alternatives, plus a download manifest with checksums and exact decoded sizes.

## Readiness and recovery

Before editing is ready, the sample is labelled as a sample. The loader shows actual downloaded bytes, elapsed time, named stages and per-file progress. Byte counts are decoded payload sizes, independent of transfer compression. After 25 seconds without new download data it reports the stall and offers Retry. Initialization failures identify the failed file or stage. Retry creates a new worker, preserving typed words and completed browser-cache downloads. No partly initialized runtime is reused.

The largest download is still Python. On a slow connection the first visit can take a minute or more; subsequent visits reuse the runtime. Startup never uploads the user's text. The main thread accepts input independently; selected edits take priority over speculative thumbnail renders. Animation exports report completed frame counts while rendering.

The current draft is stored locally, and imported TheDraw fonts are cached in the browser where storage is available. Save a `.meowtext` file for a durable editable copy. A browser that refuses storage explicitly says so. Bundled fonts are found automatically when opening desktop projects, including TheDraw file/member selections. Custom imported fonts still need their original files when moving to another device. An imported font never silently falls back to a bundled file with the same name.

## Deploy and verify

Deploy `dist/`, including `.htaccess`, beneath `/meowtext/`. Apache must serve `.mjs` as JavaScript and `.wasm` as `application/wasm`. The configuration prefers Brotli, then gzip, with an uncompressed fallback, and uses versioned immutable runtime paths. App files and the boot manifest revalidate. Upload dependencies first and `index.html` last; keep previous runtime files for already-open tabs. No server-side application is required.

Run the optional browser regression suite with `node web/check.cjs` after installing Playwright. `MEOWTEXT_PLAYWRIGHT` and `MEOWTEXT_BROWSER` can point to an existing installation.

The regression suite covers comparisons, keyboard previews, opening Tune, palette changes after solid colours, pixel-identical PNG stills, animated GIF/Kitty exports, actual HTML5 text colour cycling, the readability toggle, the four new motions, mobile overflow, failed downloads and retry, typed words surviving startup, and reduced motion. Also check a stalled connection recovering, comparison/backtracking, Gothic search, successive Tune changes, offline HTML playback, project round trips, TDF imports surviving reload and painting. Run `.venv/bin/python -m unittest discover -s tests -q` and verify a separate Kitty window as well.

The 12 October 2026 deployment was checked in a fresh Chromium profile against the public host. It became editable in 53.3 seconds on that connection; a cached reload took 5.8 seconds. These are individual measurements, not a speed guarantee. Compressed runtime responses, live animation, Tune/Undo, exact PNG output, offline HTML playback, the phone layout and homepage tile passed with no browser errors.

HTML5 cycles CSS colours on selectable text cells with an embedded font and geometric block/border cells. It embeds no raster frames. Kitty and APNG retain full-colour animation; GIF uses a stable 256-colour palette and 10 ms timing. Its colour loss is explained before download. The 40 looks and ten animated motions use the shared compositor, including the default brightness floor for gradients. PNG, ANSI, text and other still formats state their losses before download. Excessive dimensions, frame counts or image memory produce an error; nothing silently clips or drops an effect.
