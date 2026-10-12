# Browser edition

The browser studio carries the accepted Meowtext inventory into the web: a full-width artwork, three banks of real specimens, large comparison previews, immediate arrow-key selection and details one Enter away. Its headings and logo are rendered lettering. The desktop's approved design remains the source of this arrangement.

A module worker runs the shared Python compositor, palette, discovery, rasteriser and exports through Pyodide 314.0.7. PyFIGlet replaces the desktop FIGlet subprocess. TheDraw imports use the same parser. TOIlet rendering, individual glyph editing and role splitting remain desktop controls; existing project patches, letter overrides, roles and notes survive browser project round trips.

## Build and serve

```sh
# The build needs Pillow, fonttools and Brotli (the latter two subset the UI font
# and precompress the runtime). These are build dependencies, not desktop ones.
.venv/bin/python -m pip install 'fonttools[woff]' brotli
.venv/bin/python web/build.py --download-runtime
.venv/bin/python -m http.server 8000 --directory web/dist
```

Omit `--download-runtime` after the first build. Runtime files are pinned by SHA-256 in `runtime-manifest.json` and verified on every build. The worker also verifies its startup payloads where Web Crypto is available. `vendor/` retains the PyFIGlet 1.0.4 wheel, DejaVu font and their licenses. The wheel SHA-256 is `65b57b7a8e1dff8a67dc8e940a117238661d5e14c3e49121032bd404d9b2b39f`. `lettering.json` holds the glyph grids for the accepted inventory headings, so builds do not require TOIlet.

The build creates:

- A pre-rendered animated sample and first font specimens, embedded catalogue metadata, and a subset of DejaVu for stable UI metrics.
- A roughly 356 KB renderer archive containing the shared modules and starter fonts. Remaining fonts are fetched individually when used; all 569 fonts remain discoverable.
- Versioned Pyodide files and precompressed gzip/Brotli alternatives, plus a download manifest with checksums and exact decoded sizes.

## Readiness and recovery

Before editing is ready, the sample is labelled as a sample. The loader shows actual downloaded bytes, elapsed time, named stages and per-file progress. Byte counts are decoded payload sizes, independent of transfer compression. After 25 seconds without new download data it reports the stall and offers Retry. Initialization failures identify the failed file or stage. Retry creates a new worker, preserving typed words and completed browser-cache downloads. No partly initialized runtime is reused.

The largest download is still Python. On a slow connection the first visit can take a minute or more; subsequent visits reuse the runtime. Startup never uploads the user's text. The main thread accepts input independently; selected edits take priority over speculative thumbnail renders. Animation exports report completed frame counts while rendering.

The current draft is stored locally, and imported TheDraw fonts are cached in the browser where storage is available. Save a `.meowtext` file for a durable editable copy. A browser that refuses storage explicitly says so. The original font is still needed when moving a project to another device.

## Deploy and verify

Deploy `dist/`, including `.htaccess`, beneath `/meowtext/`. Apache must serve `.mjs` as JavaScript and `.wasm` as `application/wasm`. The configuration prefers Brotli, then gzip, with an uncompressed fallback, and uses versioned immutable runtime paths. App files and the boot manifest revalidate. Upload dependencies first and `index.html` last; keep previous runtime files for already-open tabs. No server-side application is required.

Run the optional browser regression suite with `node web/check.cjs` after installing Playwright. `MEOWTEXT_PLAYWRIGHT` and `MEOWTEXT_BROWSER` can point to an existing installation.

The regression suite covers comparisons, keyboard previews, opening Tune, palette changes after solid colours, pixel-identical PNG stills, animated Kitty exports, mobile overflow, failed downloads and retry, typed words surviving startup, and reduced motion. Also check a stalled connection recovering, comparison/backtracking, Gothic search, successive Tune changes, offline HTML playback, project round trips, TDF imports surviving reload and painting. Run `.venv/bin/python -m unittest discover -s tests -q` and verify a separate Kitty window as well.

The 12 October 2026 deployment was checked in a fresh Chromium profile against the public host. It became editable in 53.3 seconds on that connection; a cached reload took 5.8 seconds. These are individual measurements, not a speed guarantee. Compressed runtime responses, live animation, Tune/Undo, exact PNG output, offline HTML playback, the phone layout and homepage tile passed with no browser errors.

HTML and Kitty exports carry the complete animation; APNG does so in supported viewers. PNG, ANSI, text and other still formats state their losses before download. Excessive dimensions, frame counts or image memory produce an error; nothing silently clips or drops an effect.
