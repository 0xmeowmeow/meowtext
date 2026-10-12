'use strict';
const $ = id => document.getElementById(id);
const bootstrap = JSON.parse($('bootstrap').textContent);
let worker, startGeneration = 0, loadStarted = 0, loadChanged = 0, loadBytes = 0, loadPhase = 'download', loadTimer;
let displayedFrame = 0, samplesMoving = !matchMedia('(prefers-reduced-motion: reduce)').matches, activeTab = 'decorate';
let requestId = 0, pending = new Map(), project, config, revision = 0, goodProject;
let frame = 0, playing = !matchMedia('(prefers-reduced-motion: reduce)').matches, busyFrame = false, ready = false, valid = false;
let lastTick = performance.now(), choices = [], browse = false, page = 0, selected = 0, history = [], painting = false;
let paintChar = '█', paintColor = '#65e8ed', filenameOwned = false, width = 0, height = 0;
const clone = value => JSON.parse(JSON.stringify(value));
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
function createWorker(retry = false) {
  if (worker) worker.terminate();
  for (const handler of pending.values()) { clearTimeout(handler.timer); handler.reject(new Error('Loading restarted.')); }
  pending.clear();
  worker = new Worker(`worker.js?v=${bootstrap.build}${retry ? '&retry=1' : ''}`, {type:'module'});
  worker.onmessage = ({data}) => {
    if (data.loading) return loading(data.loading);
    if (data.exportProgress) { const {done,total}=data.exportProgress; status(`Rendering your export · ${done} of ${total} frames${done===total?' · packaging the file…':''}`); return; }
    const handler = pending.get(data.id); if (!handler) return;
    pending.delete(data.id); clearTimeout(handler.timer);
    data.error ? handler.reject(new Error(data.error)) : handler.resolve(data.result);
  };
  worker.onerror = event => {
    const error = new Error(event.message || 'The browser could not start the renderer.');
    for (const p of pending.values()) { clearTimeout(p.timer); p.reject(error); }
    pending.clear();
    if (!ready) loadFailure(error); else report(error);
  };
}
function loading({phase, files}) {
  const loaded = files.reduce((n,f) => n+f.loaded,0), total = files.reduce((n,f) => n+f.size,0);
  if (loaded !== loadBytes || phase !== loadPhase) { loadChanged = performance.now(); $('loader').classList.remove('stalled'); }
  loadBytes = loaded; loadPhase = phase;
  const labels = {download:'Downloading your tools', starting:'Starting the renderer', images:'Preparing image tools', fonts:'Opening the font catalogue'};
  $('load-heading').textContent = labels[phase] || 'Preparing the studio';
  if (phase === 'download' && total) {
    $('load-progress').max = total; $('load-progress').value = loaded;
    $('load-bytes').textContent = `${Math.floor(loaded/total*100)}% · ${(loaded/1e6).toFixed(1)} / ${(total/1e6).toFixed(1)} MB`;
    const current = files.filter(f=>!f.done).map(f=>f.name).join(', ');
    $('load-detail').textContent = current ? `Receiving ${current.toLowerCase()}…` : 'Download complete. Starting your tools…';
  } else {
    $('load-progress').removeAttribute('value');
    $('load-bytes').textContent = 'Download complete';
    $('load-detail').textContent = {starting:'Your browser is starting Python locally. No more large downloads.', images:'Connecting the same image renderer used by the Kitty edition.', fonts:'Preparing the first editable frame and font comparisons.'}[phase] || '';
  }
  $('load-files').textContent = files.map(f=>`${f.done?'✓':'↓'} ${f.name}: ${(f.loaded/1e6).toFixed(2)} / ${(f.size/1e6).toFixed(2)} MB`).join('\n');
}
function loadFailure(error) {
  clearInterval(loadTimer); ready = false;
  $('loader').hidden = false; $('loader').classList.add('stalled');
  $('load-heading').textContent = 'The tools could not finish loading';
  $('load-detail').textContent = error.message || String(error);
  $('load-step').textContent = 'Your words are still here. Retry reconnects and reuses files that already arrived.';
  $('load-progress').removeAttribute('value'); $('retry').hidden = false;
  $('motion-state').textContent = 'SAMPLE ONLY · EDITOR NOT READY';
  status('Editing is waiting for the renderer. Use Retry loading above.', true);
}
function rpc(action, values = {}) { return new Promise((resolve, reject) => { const id = ++requestId; const timer = setTimeout(() => { pending.delete(id); reject(new Error('The renderer has not answered for five minutes. Reload to recover; your last valid draft is saved.')); }, 300000); pending.set(id, {resolve, reject, timer}); worker.postMessage({id, action, ...values}); }); }
function report(error) { status(error.message || String(error), true); }
function image(result, number = frame) { displayedFrame = number; if (result.image) { $('art').src = result.image; $('full-art').src = result.image; } }
function remember() { if (project) { history.push(clone(goodProject || project)); if (history.length > 50) history.shift(); $('undo').disabled = false; } }
function extension() { return {project:'meowtext', plain:'txt', ansi:'ans', markdown:'md'}[$('format').value] || $('format').value; }
function slug() { return project.text.replace(/[^a-z0-9_-]+/gi, '-').replace(/^-+|-+$/g, '').slice(0,60) || 'my-artwork'; }
function nameFile(force = false) { if (!filenameOwned || force) $('filename').value = slug() + '.' + extension(); }
function syncControls() {
  if (document.activeElement !== $('words')) $('words').value = project.text; $('font-name').textContent = project.font_name;
  $('pause').innerHTML = (playing ? 'Ⅱ Pause' : '▶ Play') + ' <kbd>Alt P</kbd>';
  $('pause').disabled = !ready || project.animation.name === 'none'; $('restart').disabled = !ready || project.animation.name === 'none';
  $('motion-state').textContent = project.animation.name === 'none' ? 'STILL ARTWORK' : `${project.animation.name.toUpperCase()} / ${playing ? 'PLAYING' : 'PAUSED'} / ${String(displayedFrame).padStart(3,'0')}`;
  document.querySelectorAll('.font-card').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.name === project.font_name)));
  document.querySelectorAll('#motions button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === project.animation.name)));
  document.querySelectorAll('#edges button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === (project.style.outline ? project.style.outline_mode : 'off'))));
  $('undo').disabled = !history.length;
  const sameStyle = value => Object.keys(value).every(k => JSON.stringify(value[k]) === JSON.stringify(project.style[k]));
  const look = Object.keys(config.looks).find(k => sameStyle(config.looks[k]));
  document.querySelectorAll('#looks button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.value===look)));
  readout('look', look ? title(look) : 'Custom look');
  readout('edge', project.style.outline ? title(project.style.outline_mode) : 'No border');
  readout('motion', project.animation.name === 'none' ? 'Still' : title(project.animation.name));
  document.querySelectorAll('.inventory').forEach(roving);
}
async function notice() {
  if (!ready) return;
  const fmt = $('format').value;
  const text = config.notices[fmt][project.animation.name === 'none' ? 0 : 1];
  if ($('format').value !== fmt) return;
  $('export-notice').textContent = text;
  $('export-notice').classList.toggle('loss', !['html','apng','kitty','project'].includes(fmt));
  $('download').textContent = 'Download ' + (fmt === 'project' ? 'project' : fmt.toUpperCase());
}
async function commit({reset = true} = {}) {
  const ownRevision = ++revision;
  if (reset) { frame = 0; lastTick = performance.now(); }
  valid = false; $('download').disabled = true; syncControls(); nameFile();
  try {
    const result = await rpc('set', {project:clone(project), frame});
    if (ownRevision !== revision) return;
    image(result); project = result.project; goodProject = clone(project);
    width = result.width; height = result.height;
    $('dimensions').textContent = `${width} × ${height} CELLS / ${project.engine.toUpperCase()}`;
    valid = true; $('download').disabled = false; syncControls();
    status('Arrow keys try nearby specimens · Enter opens their details.');
    $('draft-state').textContent = 'DRAFT SAVED LOCALLY';
    try { localStorage.setItem('meowtext-project-v1', JSON.stringify(project)); } catch (_) { $('draft-state').textContent='SAVE A PROJECT TO KEEP IT'; }
    await notice(); return true;
  } catch (error) { if (ownRevision === revision) { report(error); $('draft-state').textContent='PREVIOUS FRAME SHOWN'; } return false; }
}
async function chooseFont(index) {
  selected = index; const choice = choices[index]; if (!choice) return;
  remember(); project.engine = choice.engine; project.font_name = choice.name;
  project.font_source = choice.source; project.font_index = choice.index;
  project.roles = {}; project.role_splits = []; project.letters = {}; project.patches = [];
  await commit();
}
let galleryVersion = 0;
async function gallery(preloaded = false) {
  const version = ++galleryVersion, grid = $('font-grid'); grid.replaceChildren();
  const shown = browse ? choices.slice(page * 12, page * 12 + 12) : choices;
  $('font-count').textContent = browse ? `${choices.length} fonts · page ${page + 1} of ${Math.max(1,Math.ceil(choices.length/12))}` : `${choices.length} choices · cyan is selected · amber labels are wildcards`;
  $('browse').textContent = browse ? 'Back to comparisons' : 'Browse all';
  if (!shown.length) { grid.textContent = 'No fonts match. Try a different name or shape.'; return; }
  await Promise.all(shown.map(async (choice, localIndex) => {
    const index = (browse ? page * 12 : 0) + localIndex;
    const button = document.createElement('button'); button.className = 'font-card'; button.dataset.name = choice.name; button.dataset.index = index;
    button.setAttribute('aria-pressed', String(choice.name === project.font_name)); button.disabled = !ready;
    const specimen = document.createElement('span'); specimen.className = 'specimen';
    const picture = document.createElement('img'); picture.alt = ''; specimen.append(picture);
    const name = document.createElement('b'); name.textContent = choice.name;
    const desc = document.createElement('small'); desc.textContent = choice.description;
    button.append(specimen, name, desc);
    if (choice.wildcard) { const tag = document.createElement('small'); tag.className = 'wildcard'; tag.textContent = '↗ Wildcard'; button.append(tag); }
    button.onclick = () => chooseFont(index);
    button.onkeydown = event => { if (event.key === 'Enter' && !browse) { event.preventDefault(); selected = index; chooseFont(index).then(()=>compare('narrow')); } };
    grid.append(button);
    try {
      const result = preloaded ? bootstrap.specimens[choice.name] : await rpc('specimen', {font:{engine:choice.engine,name:choice.name,source:choice.source,index:choice.index},text:project.text});
      if (version === galleryVersion) picture.src = result;
    } catch (error) { desc.textContent = error.message; button.disabled = true; }
  }));
  if (version === galleryVersion) roving(grid);
}
async function compare(mode) {
  if (!ready) return;
  try {
    if (browse && ['more','back'].includes(mode)) { page = Math.max(0, Math.min(Math.ceil(choices.length / 12) - 1, page + (mode === 'more' ? 1 : -1))); return gallery(); }
    if(mode==='narrow')browse=false;
    const font=mode==='narrow'?{engine:project.engine,name:project.font_name,source:project.font_source,index:project.font_index}:null;
    const result = await rpc('compare', {mode, font, index:selected, query:$('search').value, browse});
    choices = result.choices; selected = 0; page = 0; await gallery(); roving($('font-grid'));
    if (['narrow','more','back'].includes(mode)) $('font-grid').querySelector('button')?.focus();
  } catch (error) { report(error); }
}
function effectBank(id, values, kind, asset, callback) {
  for (const [label, value] of values) {
    const button = document.createElement('button'); button.className = 'effect'; button.dataset.value = value; button.disabled = !ready; button.setAttribute('aria-pressed','false');
    const img = document.createElement('img'); img.src = `assets/${asset}-${value}.png`; img.alt = ''; img.loading = 'lazy';
    const text = document.createElement('span'); text.textContent = title(label); button.append(img,text);
    button.onclick = () => { if (!ready) return; remember(); callback(value); document.querySelectorAll(`#${id} button`).forEach(b => b.setAttribute('aria-pressed', String(b === button))); commit(); };
    button.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); tune(kind); } };
    $(id).append(button);
  }
}
document.addEventListener('focusin', event => { const grid=event.target.closest('.inventory'); if(grid)roving(grid); });
// Directional navigation applies the next specimen immediately.
document.addEventListener('keydown', event => {
  const button = event.target.closest('.inventory button');
  if (!button || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
  event.preventDefault(); const grid = button.parentElement, items = [...grid.querySelectorAll('button:not(:disabled)')];
  const cols = getComputedStyle(grid).gridTemplateColumns.split(' ').length;
  const delta = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-cols,ArrowDown:cols}[event.key];
  const next = items[event.key==='Home'?0:event.key==='End'?items.length-1:Math.max(0, Math.min(items.length-1, items.indexOf(button) + delta))];
  next.focus({preventScroll:true}); next.scrollIntoView({block:'nearest',inline:'nearest'}); next.click(); roving(grid);
});
function tab(name) {
  activeTab = name;
  document.querySelectorAll('.workspace>.panel').forEach(p => p.hidden = p.id !== name + '-panel');
  document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tab === name)));
  if (name === 'export') notice().catch(report);
  $('stage-hint').textContent = {fonts:'Compare the shapes. Follow the one you like.',decorate:'Choose a specimen. See it here.',export:'The preview is the artwork you take with you.'}[name];
}
document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => tab(b.dataset.tab));
document.querySelectorAll('[data-tune]').forEach(b => b.onclick = () => tune(b.dataset.tune));
function field(label, key, type = 'text', options, group = 'style') {
  const wrap = document.createElement('label'); wrap.append(document.createTextNode(label));
  const obj = group ? project[group] : project;
  const input = document.createElement(options ? 'select' : type === 'textarea' ? 'textarea' : 'input');
  input.setAttribute('aria-label',label);
  if (options) for (const value of options) { const opt = document.createElement('option'); opt.value = value; opt.textContent = value === '' ? 'None / original' : value; input.append(opt); }
  else if (type !== 'textarea') input.type = type;
  if (type === 'number') { input.step = 'any'; }
  if (type === 'checkbox') input.checked = !!obj[key];
  else input.value = Array.isArray(obj[key]) ? obj[key].join(',') : obj[key] ?? '';
  input.onchange = () => {
    remember(); let value = type === 'checkbox' ? input.checked : type === 'number' ? Number(input.value) : input.value;
    if (['stops','outline_stops'].includes(key)) value = value.trim() ? value.split(',').map(x => x.trim()) : null;
    if (['gradient','outline_gradient'].includes(key) && value === '') value = null;
    const target=group ? project[group] : project; target[key]=value;
    if(key==='gradient'&&value)target.stops=null;
    if(key==='outline_gradient'&&value)target.outline_stops=null;
    if(key==='stops'&&value)target.gradient=null;
    if(key==='outline_stops'&&value)target.outline_gradient=null;
    if (group==='animation' && key==='name') playing = value!=='none' && samplesMoving;
    commit();
  };
  wrap.append(input); $('tune-controls').append(wrap);
}
const directions = ['horizontal','horizontal-back','vertical','vertical-back','diagonal','diagonal-back'];
function tune(kind) {
  if (!ready) return;
  $('tune-controls').replaceChildren(); $('tune-title').textContent = {look:'Tune the look',edge:'Tune the edges',motion:'Tune the motion',paint:'Paint cells'}[kind];
  const palettes = ['', ...config.palettes];
  if (kind === 'look') {
    const solidLabel=document.createElement('label');solidLabel.textContent='Solid colour';
    const solid=document.createElement('input');solid.type='color';solid.value=project.style.stops?.[0]||'#65e8ed';solid.onchange=()=>{remember();project.style.gradient=null;project.style.stops=[solid.value,solid.value];commit();};solidLabel.append(solid);$('tune-controls').append(solidLabel);
    field('Palette','gradient','text',palettes); field('Custom colours · comma-separated #hex','stops');
    field('Gradient direction','direction','text',directions); field('Hard colour bands','bands','checkbox');
    field('Rotate colour roles · degrees','hue','number',null,null); field('Recolour original font roles','recolour_roles','checkbox');
    field('Project notes','notes','textarea',null,null);
    for (const [slot, role] of Object.entries(project.roles || {})) {
      const label = document.createElement('label'); label.textContent = `Role ${slot} · ${role.name}`;
      const color = document.createElement('input'); color.type = 'color'; color.value = role.base;
      color.onchange = () => { remember(); project.roles[slot] = {...role, base:color.value, linked:true}; commit(); };
      label.append(color); $('tune-controls').append(label);
    }
  } else if (kind === 'edge') {
    field('Border enabled','outline','checkbox'); field('Border shape','outline_mode','text',config.edges.map(v => v[1]));
    field('Border colour','outline_color','color'); field('Border character','outline_char');
    field('Border palette','outline_gradient','text',palettes); field('Custom border colours','outline_stops');
    field('Border direction','outline_direction','text',[...directions,'opposite']); field('Border colour bands','outline_bands','checkbox');
    field('Border motion speed','outline_speed','number'); field('Distance from letters','outline_distance','number');
    field('Border placement','outline_place','text',['both','inside','outside']); field('Border scope','outline_scope','text',['word','letter']);
    field('Border sides · t b l r','outline_sides'); field('Border offset X','outline_dx','number'); field('Border offset Y','outline_dy','number');
    field('Shadow enabled','shadow','checkbox'); field('Shadow colour','shadow_color','color');
    field('Shadow offset X','shadow_dx','number'); field('Shadow offset Y','shadow_dy','number'); field('Shadow character · blank uses letters','shadow_char');
  } else if (kind === 'motion') {
    field('Animation','name','text',config.motions.map(v => v[1]),'animation');
    field('Speed','speed','number',null,'animation'); field('Direction','direction','text',['forward','backward','pingpong'],'animation');
    field('Colour travel · 1–360°','travel','number',null,'animation'); field('Animated layers','layers','text',['all','roles','letters','outline'],'animation');
    field('Trace path','pattern','text',['outline','rows','letter','centre'],'animation'); field('Trace mode','reveal','text',['draw','runner'],'animation');
    const p = document.createElement('p'); p.textContent = 'Draw reveals the whole artwork and holds. Runner, hue, march, pulse, scan and sparkle repeat. Export limits are reported before any file is downloaded.'; $('tune-controls').append(p);
  } else {
    const p = document.createElement('p'); p.textContent = 'Choose a character and colour, close this panel, then click cells in the artwork. Painting pauses playback. Undo reverses each stroke.'; $('tune-controls').append(p);
    for (const [name,type,value,fn] of [['Character','text',paintChar,v=>paintChar=[...v][0]||' '],['Colour','color',paintColor,v=>paintColor=v]]) {
      const label = document.createElement('label'); label.textContent=name; const input=document.createElement('input'); input.type=type; input.value=value; input.oninput=()=>fn(input.value); label.append(input); $('tune-controls').append(label);
    }
  }
  $('tune').showModal();
}
function downloadBytes(bytes, name, type) {
  const url = URL.createObjectURL(new Blob([bytes], {type})); const a = document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),30000);
}
async function download(fmt, name) {
  if (!valid) return status('Fix the render error before exporting, so the download matches your design.',true);
  $('download').disabled = true; status('Rendering the complete export…');
  try {
    const result = await rpc('export', {format:fmt, frame:displayedFrame});
    const bytes = Uint8Array.from(atob(result.data), c => c.charCodeAt(0));
    downloadBytes(bytes,name,{html:'text/html',png:'image/png',apng:'image/apng',project:'application/json',json:'application/json'}[fmt]||'text/plain');
    status('Downloaded ' + name + '. ' + result.notice);
  } catch(error) { report(error); }
  finally { $('download').disabled = !valid; }
}
$('download').onclick = () => download($('format').value,$('filename').value || slug()+'.'+extension());
$('save').onclick = $('save-copy').onclick = () => download('project',slug()+'.meowtext');
$('format').onchange = () => { const name = $('filename').value; if (filenameOwned) $('filename').value = name.replace(/\.[^.]+$/, '') + '.' + extension(); else nameFile(); notice().catch(report); };
$('filename').oninput = () => filenameOwned = true;
let wordTimer, searchTimer;
$('words').oninput = () => { if (!ready) return; clearTimeout(wordTimer); wordTimer=setTimeout(()=>{ remember(); project.text=$('words').value; project.patches=[]; commit().then(()=>gallery()); },200); };
$('search').oninput = () => { clearTimeout(searchTimer); searchTimer=setTimeout(()=>compare('reset'),200); };
$('more').onclick = () => compare('more'); $('back').onclick = () => compare('back'); $('similar').onclick = () => compare('narrow');
$('browse').onclick = () => { browse=!browse; compare('reset'); };
$('undo').onclick = () => { if(history.length){project=history.pop(); $('words').value=project.text; commit().then(()=>gallery());} };
$('pause').onclick = () => { playing=!playing; lastTick=performance.now(); syncControls(); };
$('restart').onclick = () => { frame=0; playing=true; commit(); };
$('inspect').onclick = () => { $('full-art').src=$('art').src; $('full-size').showModal(); };
$('paint').onclick = () => { painting=!painting; $('art').classList.toggle('painting',painting); $('paint').textContent=painting?'Finish painting':'Paint cells'; if(painting){playing=false;syncControls();tune('paint');} };
$('art').onclick = event => {
  if(!painting||!valid) return;
  const bounds=$('art').getBoundingClientRect(), x=Math.min(width-1,Math.floor((event.clientX-bounds.left)/bounds.width*width)), y=Math.min(height-1,Math.floor((event.clientY-bounds.top)/bounds.height*height));
  remember(); project.patches=project.patches.filter(p=>p.x!==x||p.y!==y);
  project.patches.push({x,y,c:paintChar,fg:paintColor}); commit({reset:false});
};
$('open').onclick = () => $('project-file').click(); $('import-font').onclick = () => $('font-file').click();
$('project-file').onchange = async event => {
  const file=event.target.files[0]; if(!file)return;
  try { if(file.size>2000000)throw Error('Projects must be smaller than 2 MB.'); const candidate=JSON.parse(await file.text()); if(candidate.meowtext!=='project')throw Error('Choose a .meowtext project file.'); remember(); project=candidate; playing=project.animation?.name!=='none'&&samplesMoving; await commit(); if(!valid)status('Could not open this project. Import its original .tdf font first, or install the Kitty edition for TOIlet fonts. Undo returns to your previous artwork.',true); }
  catch(error){report(error);} finally {event.target.value='';}
};
$('font-file').onchange = async event => {
  const file=event.target.files[0];if(!file)return;
  try { if(file.size>2000000)throw Error('Font files must be smaller than 2 MB.'); const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(const b of bytes)raw+=String.fromCharCode(b); const data=btoa(raw), result=await rpc('font',{name:file.name,data});
    let cached=false;try{const cache=await caches.open('meowtext-user-fonts-v1');await cache.put(new URL('user-fonts/'+encodeURIComponent(file.name),location.href),new Response(data));cached=true;}catch(_){}
    choices=result.choices;browse=false;page=0;await gallery();tab('fonts');status('Imported '+result.name+'. Select a specimen or reopen its project. '+(cached?'Font saved in this browser.':'The font stays in this tab; import it again next visit.')); }
  catch(error){report(error);}finally{event.target.value='';}
};
async function tick(now) {
  if(ready&&valid&&playing&&!busyFrame&&project.animation.name!=='none'&&!document.hidden&&now-lastTick>=120){
    const steps=Math.floor((now-lastTick)/120);frame+=steps;lastTick+=steps*120;busyFrame=true;const ownRevision=revision;
    try{const result=await rpc('frame',{frame});if(ownRevision===revision&&playing){image(result, frame);syncControls();}}catch(error){playing=false;report(error);}finally{busyFrame=false;}
  }
  requestAnimationFrame(tick);
}
document.addEventListener('visibilitychange',()=>lastTick=performance.now());
function title(value) { return value.replaceAll('-',' ').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase()); }
function readout(kind, value) {
  const node = $(kind+'-readout'); node.replaceChildren();
  node.append(document.createTextNode('◆ '+value));
  const hint=document.createElement('span');hint.textContent='arrows try · ↵ tune';node.append(hint);
}
function roving(grid) {
  const buttons=[...grid.querySelectorAll('button')];
  const chosen=buttons.includes(document.activeElement)?document.activeElement:buttons.find(b=>b.getAttribute('aria-pressed')==='true')||buttons[0];
  for(const b of buttons)b.tabIndex=b===chosen?0:-1;
}
function samples() {
  for (const img of document.querySelectorAll('#motions img')) {
    const name=img.closest('button').dataset.value;
    img.src=`assets/motion-${name}${samplesMoving?'':'-still'}.png`;
  }
  if(!ready)$('art').src=`assets/startup${samplesMoving?'':'-still'}.png`;
  $('ui-motion').textContent=samplesMoving?'Pause samples':'Play samples';
}
$('ui-motion').onclick=()=>{samplesMoving=!samplesMoving;samples();};
$('help').onclick=()=>$('shortcuts').showModal();
document.querySelectorAll('.tune-button').forEach(b=>b.tabIndex=-1);
document.addEventListener('keydown',event=>{
  if(!event.altKey||event.ctrlKey||event.metaKey)return;
  const key=event.key.toLowerCase();
  if(!['1','2','3','t','p','z'].includes(key))return;
  if(document.querySelector('dialog[open]'))return;
  event.preventDefault();
  if(['1','2','3'].includes(key)){
    tab({'1':'fonts','2':'decorate','3':'export'}[key]);
    const target=key==='1'?$('font-grid').querySelector('[tabindex="0"]'):key==='2'?$('looks').querySelector('[tabindex="0"]'):$('format');
    target?.focus();
  }else if(key==='t')$('words').focus();
  else if(key==='p'&&ready)$('pause').click();
  else if(key==='z'&&ready)$('undo').click();
});
async function start(retry = false) {
  const generation=++startGeneration;
  clearInterval(loadTimer); ready=false; loadBytes=0; loadPhase='download';
  loadStarted=loadChanged=performance.now(); $('loader').hidden=false; $('loader').classList.remove('stalled');
  $('retry').hidden=true; $('load-progress').removeAttribute('value');
  $('load-heading').textContent=retry?'Reconnecting your studio':'Opening your studio';
  $('load-step').textContent='Your words stay on your device. Downloaded tools are cached for later visits.';
  document.body.classList.add('loading');
  loadTimer=setInterval(()=>{
    const seconds=Math.floor((performance.now()-loadStarted)/1000);
    $('load-clock').textContent=seconds<60?seconds+'s':Math.floor(seconds/60)+'m '+seconds%60+'s';
    if(seconds>=10)$('retry').hidden=false;
    if(performance.now()-loadChanged>25000){
      $('loader').classList.add('stalled');
      $('load-detail').textContent=loadPhase==='download'?'No new data for 25 seconds. The connection may be stalled; Retry reconnects.':'Downloads are complete. Your browser is still preparing the renderer; Retry is available if it stays here.';
    }
  },500);
  createWorker(retry);
  try {
    const result=await rpc('init'); if(generation!==startGeneration)return;
    config=result;
    const typed=$('words').value, changed=typed!==bootstrap.project.text;
    let restored=false;
    if(!retry){
      project=clone(config.project);
      try{const saved=JSON.parse(localStorage.getItem('meowtext-project-v1'));if(saved?.meowtext==='project'){project=saved;restored=true;}}catch(_){}
    }
    if(changed){project.text=typed;project.patches=[];}
    goodProject=null;
    if(project.engine==='tdf')await restoreFonts();
    ready=true;
    document.querySelectorAll('[disabled]').forEach(el=>el.disabled=false);
    let ok=await commit();
    if(!ok&&restored){
      const lost=clone(project);project=clone(config.project);if(changed)project.text=typed;
      await commit();history.push(lost);
      status('Your saved draft needs its original font. Import the .tdf file, then Undo to restore that draft.',true);
    }else if(restored&&!changed)status('Restored your last draft. Save a project for an editable copy on your device.');
    else status('Ready. Click an effect, or use arrows to try its neighbours.');
    clearInterval(loadTimer);$('loader').hidden=true;document.body.classList.remove('loading');
    lastTick=performance.now();
    await gallery();
    samples();
  }catch(error){if(generation===startGeneration)loadFailure(error);}
}
async function restoreFonts(){
  try{
    const cache=await caches.open('meowtext-user-fonts-v1');
    for(const key of await cache.keys()){
      const response=await cache.match(key);const data=await response.text();
      await rpc('font',{name:decodeURIComponent(new URL(key.url).pathname.split('/').pop()),data});
    }
  }catch(error){status('Saved font files could not be restored. Import the original .tdf file again.',true);}
}
$('retry').onclick=()=>start(true);
config=bootstrap;project=clone(config.project);choices=config.choices;
for(const [value,label] of Object.entries(config.formats)){const option=document.createElement('option');option.value=value;option.textContent=label;$('format').append(option);}
effectBank('looks',Object.keys(config.looks).map(k=>[k,k]),'look','look',value=>project.style=clone(config.looks[value]));
effectBank('edges',[['No border','off'],...config.edges],'edge','edge',value=>{project.style.outline=value!=='off';if(value!=='off')project.style.outline_mode=value;});
effectBank('motions',config.motions,'motion','motion',value=>{project.animation.name=value;playing=value!=='none'&&samplesMoving;});
gallery(true);samples();syncControls();
const reducedPreference=matchMedia('(prefers-reduced-motion: reduce)');
reducedPreference.addEventListener('change',event=>{if(event.matches){playing=false;samplesMoving=false;samples();syncControls();}});
$('motion-state').textContent='ANIMATED SAMPLE · TOOLS LOADING';
requestAnimationFrame(tick);
start();
