'use strict';
const $ = id => document.getElementById(id);
const worker = new Worker('worker.js', {type:'module'});
let requestId = 0, pending = new Map(), project, config, revision = 0, goodProject;
let frame = 0, playing = !matchMedia('(prefers-reduced-motion: reduce)').matches, busyFrame = false, ready = false, valid = false;
let lastTick = performance.now(), choices = [], browse = false, page = 0, selected = 0, history = [], painting = false;
let paintChar = '█', paintColor = '#65e8ed', filenameOwned = false, width = 0, height = 0;
const clone = value => JSON.parse(JSON.stringify(value));
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
worker.onmessage = ({data}) => {
  if (data.status) return status(data.status);
  const handler = pending.get(data.id); if (!handler) return;
  pending.delete(data.id); data.error ? handler.reject(new Error(data.error)) : handler.resolve(data.result);
};
worker.onerror = event => { status('The renderer could not start. Check your connection and reload to retry. ' + event.message, true); for (const p of pending.values()) p.reject(new Error(event.message)); pending.clear(); };
function rpc(action, values = {}) { return new Promise((resolve, reject) => { const id = ++requestId; pending.set(id, {resolve, reject}); worker.postMessage({id, action, ...values}); }); }
function report(error) { status(error.message || String(error), true); }
function image(result) { if (result.image) { $('art').src = result.image; $('full-art').src = result.image; } }
function remember() { if (project) { history.push(clone(goodProject || project)); if (history.length > 50) history.shift(); $('undo').disabled = false; } }
function extension() { return {project:'meowtext', plain:'txt', ansi:'ans', markdown:'md'}[$('format').value] || $('format').value; }
function slug() { return project.text.replace(/[^a-z0-9_-]+/gi, '-').replace(/^-+|-+$/g, '').slice(0,60) || 'my-artwork'; }
function nameFile(force = false) { if (!filenameOwned || force) $('filename').value = slug() + '.' + extension(); }
function syncControls() {
  $('words').value = project.text; $('font-name').textContent = project.font_name;
  $('pause').textContent = playing ? 'Pause' : 'Play';
  $('motion-state').textContent = project.animation.name === 'none' ? 'STILL ARTWORK' : `${project.animation.name.toUpperCase()} / ${playing ? 'PLAYING' : 'PAUSED'} / FRAME ${frame}`;
  document.querySelectorAll('.font-card').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.name === project.font_name)));
  document.querySelectorAll('#motions button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === project.animation.name)));
  document.querySelectorAll('#edges button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.value === (project.style.outline ? project.style.outline_mode : 'off'))));
  $('undo').disabled = !history.length;
}
async function notice() {
  if (!ready) return;
  const fmt = $('format').value;
  const text = config.notices[fmt][project.animation.name === 'none' ? 0 : 1];
  if ($('format').value !== fmt) return;
  $('export-notice').textContent = text;
  $('export-notice').classList.toggle('loss', !['html','apng','project'].includes(fmt));
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
    status('Your preview and exports use the same renderer.');
    try { localStorage.setItem('meowtext-project-v1', JSON.stringify(project)); } catch (_) {}
    await notice();
  } catch (error) { if (ownRevision === revision) report(error); }
}
async function chooseFont(index) {
  selected = index; const choice = choices[index]; if (!choice) return;
  remember(); project.engine = choice.engine; project.font_name = choice.name;
  project.font_source = choice.source; project.font_index = choice.index;
  project.roles = {}; project.role_splits = []; project.letters = {}; project.patches = [];
  await commit();
}
let galleryVersion = 0;
async function gallery() {
  const version = ++galleryVersion, grid = $('font-grid'); grid.replaceChildren();
  const shown = browse ? choices.slice(page * 12, page * 12 + 12) : choices;
  $('font-count').textContent = browse ? `${choices.length} fonts · page ${page + 1} of ${Math.max(1,Math.ceil(choices.length/12))}` : `${choices.length} choices · cyan is selected · amber labels are wildcards`;
  $('browse').textContent = browse ? 'Back to comparisons' : 'Browse all';
  if (!shown.length) { grid.textContent = 'No fonts match. Try a different name or shape.'; return; }
  await Promise.all(shown.map(async (choice, localIndex) => {
    const index = (browse ? page * 12 : 0) + localIndex;
    const button = document.createElement('button'); button.className = 'font-card'; button.dataset.name = choice.name; button.dataset.index = index;
    button.setAttribute('aria-pressed', String(choice.name === project.font_name));
    const specimen = document.createElement('span'); specimen.className = 'specimen';
    const picture = document.createElement('img'); picture.alt = ''; specimen.append(picture);
    const name = document.createElement('b'); name.textContent = choice.name;
    const desc = document.createElement('small'); desc.textContent = choice.description;
    button.append(specimen, name, desc);
    if (choice.wildcard) { const tag = document.createElement('small'); tag.className = 'wildcard'; tag.textContent = '↗ Wildcard · another direction'; button.append(tag); }
    button.onclick = () => chooseFont(index);
    button.onkeydown = event => { if (event.key === 'Enter' && !browse) { event.preventDefault(); selected = index; compare('narrow'); } };
    grid.append(button);
    try {
      const result = await rpc('specimen', {font:{engine:choice.engine,name:choice.name,source:choice.source,index:choice.index},text:project.text});
      if (version === galleryVersion) picture.src = result;
    } catch (error) { desc.textContent = error.message; button.disabled = true; }
  }));
}
async function compare(mode) {
  try {
    if (browse && ['more','back'].includes(mode)) { page = Math.max(0, Math.min(Math.ceil(choices.length / 12) - 1, page + (mode === 'more' ? 1 : -1))); return gallery(); }
    const result = await rpc('compare', {mode, index:selected, query:$('search').value, browse});
    choices = result.choices; selected = 0; page = 0; await gallery();
  } catch (error) { report(error); }
}
function effectBank(id, values, kind, asset, callback) {
  for (const [label, value] of values) {
    const button = document.createElement('button'); button.className = 'effect'; button.dataset.value = value; button.setAttribute('aria-pressed','false');
    const img = document.createElement('img'); img.src = `assets/${asset}-${value}.png`; img.alt = ''; img.loading = 'lazy';
    const text = document.createElement('span'); text.textContent = label; button.append(img,text);
    button.onclick = () => { remember(); callback(value); document.querySelectorAll(`#${id} button`).forEach(b => b.setAttribute('aria-pressed', String(b === button))); commit(); };
    button.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); tune(kind); } };
    $(id).append(button);
  }
}
// Directional navigation applies the next specimen immediately.
document.addEventListener('keydown', event => {
  const button = event.target.closest('.inventory button');
  if (!button || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
  event.preventDefault(); const grid = button.parentElement, items = [...grid.querySelectorAll('button:not(:disabled)')];
  const cols = getComputedStyle(grid).gridTemplateColumns.split(' ').length;
  const delta = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-cols,ArrowDown:cols}[event.key];
  const next = items[Math.max(0, Math.min(items.length-1, items.indexOf(button) + delta))]; next.focus(); next.click();
});
function tab(name) {
  document.querySelectorAll('main>.panel').forEach(p => p.hidden = p.id !== name + '-panel');
  document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.tab === name)));
  if (name === 'export') notice().catch(report);
}
document.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => tab(b.dataset.tab));
document.querySelectorAll('[data-tune]').forEach(b => b.onclick = () => tune(b.dataset.tune));
function field(label, key, type = 'text', options, group = 'style') {
  const wrap = document.createElement('label'); wrap.append(document.createTextNode(label));
  const obj = group ? project[group] : project;
  const input = document.createElement(options ? 'select' : type === 'textarea' ? 'textarea' : 'input');
  if (options) for (const value of options) { const opt = document.createElement('option'); opt.value = value; opt.textContent = value === '' ? 'None / original' : value; input.append(opt); }
  else input.type = type;
  if (type === 'number') { input.step = 'any'; }
  if (type === 'checkbox') input.checked = !!obj[key];
  else input.value = Array.isArray(obj[key]) ? obj[key].join(',') : obj[key] ?? '';
  input.onchange = () => {
    remember(); let value = type === 'checkbox' ? input.checked : type === 'number' ? Number(input.value) : input.value;
    if (['stops','outline_stops'].includes(key)) value = value.trim() ? value.split(',').map(x => x.trim()) : null;
    if (['gradient','outline_gradient'].includes(key) && value === '') value = null;
    (group ? project[group] : project)[key] = value; commit();
  };
  wrap.append(input); $('tune-controls').append(wrap);
}
const directions = ['horizontal','horizontal-back','vertical','vertical-back','diagonal','diagonal-back'];
function tune(kind) {
  if (!ready) return;
  $('tune-controls').replaceChildren(); $('tune-title').textContent = {look:'Tune the look',edge:'Tune the edges',motion:'Tune the motion',paint:'Paint cells'}[kind];
  const palettes = ['', ...config.palettes];
  if (kind === 'look') {
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
    const result = await rpc('export', {format:fmt, frame});
    const bytes = Uint8Array.from(atob(result.data), c => c.charCodeAt(0));
    downloadBytes(bytes,name,{html:'text/html',png:'image/png',apng:'image/apng',project:'application/json',json:'application/json'}[fmt]||'text/plain');
    status('Downloaded ' + name + '. ' + result.notice);
  } catch(error) { report(error); }
  finally { $('download').disabled = !valid; }
}
$('download').onclick = () => download($('format').value,$('filename').value || slug()+'.'+extension());
$('save').onclick = () => download('project',slug()+'.meowtext');
$('format').onchange = () => { const name = $('filename').value; if (filenameOwned) $('filename').value = name.replace(/\.[^.]+$/, '') + '.' + extension(); else nameFile(); notice().catch(report); };
$('filename').oninput = () => filenameOwned = true;
let wordTimer, searchTimer;
$('words').oninput = () => { clearTimeout(wordTimer); wordTimer=setTimeout(()=>{ remember(); project.text=$('words').value; project.patches=[]; commit().then(gallery); },200); };
$('search').oninput = () => { clearTimeout(searchTimer); searchTimer=setTimeout(()=>compare('reset'),200); };
$('more').onclick = () => compare('more'); $('back').onclick = () => compare('back'); $('similar').onclick = () => { if(browse){browse=false;compare('reset');}else compare('narrow'); };
$('browse').onclick = () => { browse=!browse; compare('reset'); };
$('undo').onclick = () => { if(history.length){project=history.pop();commit();} };
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
  try { if(file.size>2000000)throw Error('Projects must be smaller than 2 MB.'); const candidate=JSON.parse(await file.text()); if(candidate.meowtext!=='project')throw Error('Choose a .meowtext project file.'); remember(); project=candidate; await commit(); if(!valid)status('Could not open this project. Import its original .tdf font first, or install the Kitty edition for TOIlet fonts. Undo returns to your previous artwork.',true); }
  catch(error){report(error);} finally {event.target.value='';}
};
$('font-file').onchange = async event => {
  const file=event.target.files[0];if(!file)return;
  try { if(file.size>2000000)throw Error('Font files must be smaller than 2 MB.'); const bytes=new Uint8Array(await file.arrayBuffer());let raw='';for(const b of bytes)raw+=String.fromCharCode(b); const result=await rpc('font',{name:file.name,data:btoa(raw)}); choices=result.choices;browse=false;page=0;await gallery();status('Imported '+result.name+'. Select a specimen or reopen its project. The font stays in this tab.'); }
  catch(error){report(error);}finally{event.target.value='';}
};
async function tick(now) {
  if(ready&&valid&&playing&&!busyFrame&&project.animation.name!=='none'&&!document.hidden&&now-lastTick>=120){
    const steps=Math.floor((now-lastTick)/120);frame+=steps;lastTick+=steps*120;busyFrame=true;const ownRevision=revision;
    try{const result=await rpc('frame',{frame});if(ownRevision===revision){image(result);syncControls();}}catch(error){playing=false;report(error);}finally{busyFrame=false;}
  }
  requestAnimationFrame(tick);
}
document.addEventListener('visibilitychange',()=>lastTick=performance.now());
async function start() {
  try {
    config=await rpc('init');project=config.project;choices=config.choices;
    for(const [value,label] of Object.entries(config.formats)){const option=document.createElement('option');option.value=value;option.textContent=label;$('format').append(option);}
    effectBank('looks',Object.keys(config.looks).map(k=>[k.replaceAll('-',' '),k]),'look','look',value=>project.style=clone(config.looks[value]));
    effectBank('edges',[['Off','off'],...config.edges],'edge','edge',value=>{project.style.outline=value!=='off';if(value!=='off')project.style.outline_mode=value;});
    effectBank('motions',config.motions,'motion','motion',value=>project.animation.name=value);
    document.querySelectorAll('[disabled]').forEach(el=>el.disabled=false); ready=true;
    let restored=false;try{const saved=JSON.parse(localStorage.getItem('meowtext-project-v1'));if(saved&&saved.engine==='figlet'){project=saved;restored=true;}}catch(_){}
    await commit();if(restored)status('Restored your last browser draft. Save a project to keep a file on your device.');
    await gallery();requestAnimationFrame(tick);
  } catch(error){report(error);}
}
start();
