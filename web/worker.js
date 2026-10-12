// The renderer is shared Python. Input stays on the browser's main thread.
let runtime, boot, initialized = false, draining = false;
const queue = [], originalFetch = self.fetch.bind(self), downloads = new Map(), fontJobs = new Map();
let sentAt = 0, phase = 'download', startupFailed = false;
const startupAbort = new AbortController();
function progress(force = false) {
  if (startupFailed) return;
  if (!force && performance.now() - sentAt < 180) return;
  sentAt = performance.now();
  postMessage({loading:{phase, files:[...downloads.values()]}});
}
async function fetchBytes(url, info) {
  const key = new URL(url, self.location.href).href;
  const entry = {name:info.label, size:info.size, loaded:0, done:false};
  downloads.set(key, entry); progress(true);
  const response = await originalFetch(key, {cache:new URL(self.location.href).searchParams.has('retry')?'reload':'default', signal:startupAbort.signal});
  if (!response.ok) throw Error(`${info.label} could not download (HTTP ${response.status}). Retry to reconnect.`);
  const reader = response.body.getReader(), pieces = [];
  while (true) {
    const {done, value} = await reader.read(); if (done) break;
    pieces.push(value); entry.loaded += value.byteLength; progress();
  }
  const bytes = new Uint8Array(entry.loaded); let offset = 0;
  for (const piece of pieces) { bytes.set(piece, offset); offset += piece.length; }
  if (info.sha256 && crypto.subtle) {
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
    const actual = [...digest].map(b => b.toString(16).padStart(2,'0')).join('');
    if (actual !== info.sha256) throw Error(`${info.label} downloaded incompletely or has changed. Retry to fetch a fresh copy.`);
  }
  entry.done = true; progress(true);
  return {bytes, headers:response.headers};
}
async function initialize() {
  const version = new URL(self.location.href).searchParams.get('v') || '';
  const response = await originalFetch(`boot.json?v=${encodeURIComponent(version)}`, {cache:'no-cache'});
  if (!response.ok) throw Error(`Could not read the download manifest (HTTP ${response.status}).`);
  boot = await response.json();
  const cached = new Map();
  // Downloads run together, with real byte counts. Python starts only when its
  // dependencies have arrived; a failed attempt never becomes a ready runtime.
  try {
    await Promise.all(Object.entries(boot.files).map(async ([url, info]) => {
      cached.set(new URL(url, self.location.href).href, await fetchBytes(url, info));
    }));
  } catch(error) {
    startupFailed = true; startupAbort.abort(); throw error;
  }
  phase = 'starting'; progress(true);
  self.fetch = async (resource, options) => {
    const url = new URL(typeof resource === 'string' || resource instanceof URL ? resource : resource.url, self.location.href).href;
    const item = cached.get(url);
    if (!item) return originalFetch(resource, options);
    const headers = new Headers(item.headers);
    headers.delete('content-encoding'); headers.set('content-length', item.bytes.length);
    return new Response(item.bytes, {status:200, headers});
  };
  await import(`./${boot.runtime}/pyodide.js`);
  const candidate = await self.loadPyodide({indexURL:new URL(boot.runtime+'/', self.location.href).href});
  phase = 'images'; progress(true);
  await candidate.loadPackage('pillow');
  const archive = cached.get(new URL(boot.renderer, self.location.href).href);
  candidate.unpackArchive(archive.bytes, 'zip', {extractDir:'/app'});
  phase = 'fonts'; progress(true);
  candidate.runPython("import sys, os; os.chdir('/app'); sys.path.insert(0, '/app')\nimport bridge\nbridge.raster.MONO_FONT = '/app/DejaVuSansMono.ttf'\nbridge.use_font_index()");
  runtime = candidate;
  self.fetch = originalFetch;
  initialized = true;
}
async function ensureFont(font) {
  const name = font.name, source = font.source || '';
  // An imported font takes precedence only for its exact project source.
  if (font.engine === 'tdf' && source.startsWith('/app/fonts/')) return;
  const key = font.engine === 'tdf' ? 'tdf:' + source.split('/').pop().toLowerCase() : font.engine + ':' + name;
  const info = boot.fonts[key] || (font.engine === 'figlet' ? boot.fonts['toilet:' + name] : null);
  if (!info) return; // Python reports unknown fonts without replacing the artwork.
  const path = '/app/' + info.path;
  if (runtime.FS.analyzePath(path).exists) return;
  if (!fontJobs.has(path)) fontJobs.set(path, (async () => {
    const response = await originalFetch(info.url);
    if (!response.ok) throw Error(`Could not download font ${name} (HTTP ${response.status}). Your previous artwork is safe; try again.`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (crypto.subtle) {
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
      if ([...digest].map(b=>b.toString(16).padStart(2,'0')).join('') !== info.sha256) throw Error(`Font ${name} downloaded incompletely. Try again.`);
    }
    runtime.FS.mkdirTree(path.slice(0,path.lastIndexOf('/')));
    runtime.FS.writeFile(path, bytes);
  })().catch(error => { fontJobs.delete(path); throw error; }));
  await fontJobs.get(path);
}
async function drain() {
  if (draining) return; draining = true;
  while (queue.length) {
    // Selected edits and exports run before speculative gallery thumbnails.
    // Keep foreground operations in arrival order (set before its export).
    let index = queue.findIndex(m => !['specimen','frame'].includes(m.action));
    if (index < 0) index = 0;
    const {id, ...request} = queue.splice(index,1)[0];
    try {
      if (!initialized) await initialize();
      if (request.action === 'set') await ensureFont({engine:request.project.engine,name:request.project.font_name,source:request.project.font_source});
      if (request.action === 'specimen') await ensureFont(request.font);
      runtime.globals.set('browser_request',JSON.stringify(request));
      const result = JSON.parse(runtime.runPython('bridge.dispatch(browser_request)'));
      postMessage({id,result});
    } catch (error) {
      const message = String(error.message || error).split('\n').filter(Boolean).slice(-1)[0];
      postMessage({id,error:message});
      if (!initialized) { queue.length = 0; break; }
    }
    // Yield between frames so new keystrokes can reach the foreground queue.
    await new Promise(resolve => setTimeout(resolve, 0));
  }
  draining = false;
}
self.onmessage = ({data}) => { queue.push(data); drain(); };
