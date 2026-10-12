/* Optional browser regression suite: npm install --no-save playwright
 * MEOWTEXT_PLAYWRIGHT and MEOWTEXT_BROWSER can select an existing installation.
 * Build first. This test serves only web/dist, on a temporary loopback port.
 */
const {chromium}=require(process.env.MEOWTEXT_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const root=path.join(__dirname,'dist');
const server=http.createServer((req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const file=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  const mime={'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.wasm':'application/wasm','.json':'application/json','.png':'image/png','.woff2':'font/woff2'}[path.extname(file)]||'application/octet-stream';
  res.writeHead(200,{'content-type':mime,'content-length':fs.statSync(file).size});fs.createReadStream(file).pipe(res);
});
let browser;
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port;
  browser=await chromium.launch({headless:true,...(process.env.MEOWTEXT_BROWSER?{executablePath:process.env.MEOWTEXT_BROWSER}:{})});
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message);});
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#loader').hidden);
  await page.keyboard.press('Alt+1');
  await page.waitForFunction(()=>document.querySelectorAll('.font-card img[src]').length===6);
  assert.equal(await page.locator('.font-card b').first().innerText(),'ansi_shadow');
  await page.locator('.font-card').first().focus();await page.keyboard.press('ArrowRight');await page.waitForFunction(()=>valid);
  assert.equal(await page.locator('#font-name').innerText(),await page.locator('.font-card').nth(1).getAttribute('data-name'));
  await page.keyboard.press('Enter');await page.waitForTimeout(500);assert.equal(await page.locator('.font-card').count(),6);
  await page.keyboard.press('Alt+2');await page.click('#looks [data-value="cyan"]');await page.click('[data-tune="look"]');
  assert(await page.locator('#tune').isVisible(),`Tune must open: ${errors.join('; ')}`);
  assert.equal(await page.locator('dialog[open]').count(),0,'Tune must leave the artwork accessible');
  const artBox=await page.locator('.stage').boundingBox(),tuneBox=await page.locator('#tune').boundingBox(),banksBox=await page.locator('.banks').boundingBox();
  assert(tuneBox.y>=artBox.y+artBox.height&&banksBox.y>=tuneBox.y+tuneBox.height,'Tune belongs below the artwork and above the banks');
  await page.getByLabel('Palette',{exact:true}).selectOption('fire');await page.waitForFunction(()=>valid&&project.style.gradient==='fire');
  assert.equal(await page.evaluate(()=>project.style.stops),null,'a previous solid must not override a chosen gradient');
  assert(await page.getByLabel('Lift dark gradients',{exact:true}).isChecked());
  await page.getByLabel('Lift dark gradients',{exact:true}).uncheck();await page.waitForFunction(()=>valid&&!project.style.readable_gradients);
  await page.getByLabel('Lift dark gradients',{exact:true}).check();await page.waitForFunction(()=>valid&&project.style.readable_gradients);
  if(await page.evaluate(()=>playing))await page.click('#pause');
  const beforeTune=await page.locator('#art').getAttribute('src'),undoCount=await page.evaluate(()=>history.length);
  const solid=page.getByLabel('Solid colour',{exact:true});await solid.focus();
  for(const colour of ['#ea7592','#ecb860','#68d9c7']){
    await solid.evaluate((input,value)=>{input.value=value;input.dispatchEvent(new Event('input',{bubbles:true}));},colour);
    await page.waitForFunction(value=>valid&&project.style.stops?.[0]===value,colour);
  }
  assert.notEqual(await page.locator('#art').getAttribute('src'),beforeTune,'colour input previews without closing or blurring');
  assert.equal(await solid.evaluate(input=>input===document.activeElement),true);
  assert.equal(await page.evaluate(()=>history.length),undoCount+1,'a colour adjustment is one undo step');
  // A renderer response arriving during a newer edit must not erase that edit.
  await page.evaluate(()=>{window.originalRpc=rpc;rpc=async(action,values)=>{const result=await originalRpc(action,values);if(action==='set')await new Promise(resolve=>setTimeout(resolve,150));return result;};});
  await solid.evaluate(input=>{input.value='#a4e075';input.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForTimeout(90);
  await solid.evaluate(input=>{input.value='#d888ef';input.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>valid&&project.style.stops?.[0]==='#d888ef');
  await page.evaluate(()=>{rpc=originalRpc;delete window.originalRpc;});
  await page.keyboard.press('Alt+z');await page.waitForFunction(()=>valid&&project.style.gradient==='fire'&&project.style.stops===null);
  assert.equal(await page.getByLabel('Palette',{exact:true}).inputValue(),'fire','Undo also updates the open controls');
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#tune').isVisible(),false);
  assert.equal(await page.locator('[data-tune="look"]').evaluate(e=>e===document.activeElement),true,'Escape restores the originating control');
  await page.click('#motions [data-value="hue"]');await page.waitForFunction(()=>valid);
  await page.keyboard.press('Alt+p');const before=await page.locator('#art').getAttribute('src');
  await page.waitForTimeout(300);assert.equal(await page.locator('#art').getAttribute('src'),before);
  await page.keyboard.press('Alt+3');await page.selectOption('#format','png');
  assert((await page.locator('#export-notice').innerText()).includes('Animation will be lost'));
  const [png]=await Promise.all([page.waitForEvent('download'),page.click('#download')]);
  const stream=await png.createReadStream(),chunks=[];for await(const chunk of stream)chunks.push(chunk);
  assert.deepEqual(Buffer.concat(chunks),Buffer.from(before.split(',')[1],'base64'));
  await page.selectOption('#format','kitty');const [kitty]=await Promise.all([page.waitForEvent('download'),page.click('#download')]);
  const kstream=await kitty.createReadStream(),kchunks=[];for await(const chunk of kstream)kchunks.push(chunk);
  assert(Buffer.concat(kchunks).toString().includes('s=3,v=1'));
  await page.selectOption('#format','gif');assert((await page.locator('#export-notice').innerText()).includes('256'));
  const [gif]=await Promise.all([page.waitForEvent('download'),page.click('#download')]);
  const gs=await gif.createReadStream(),gc=[];for await(const chunk of gs)gc.push(chunk);
  assert.equal(Buffer.concat(gc).subarray(0,6).toString(),'GIF89a');
  await page.selectOption('#format','html');const [html]=await Promise.all([page.waitForEvent('download'),page.click('#download')]);
  const hs=await html.createReadStream(),hc=[];for await(const chunk of hs)hc.push(chunk);
  const document=Buffer.concat(hc).toString();assert(!document.includes('data:image'));
  const exported=await context.newPage();await exported.setContent(document);
  assert(await exported.locator('#art .cell').count()>0);assert.equal(await exported.locator('img,canvas').count(),0);
  const colours=await exported.locator('#art').getAttribute('style');await exported.waitForTimeout(300);assert.notEqual(await exported.locator('#art').getAttribute('style'),colours);
  await exported.click('#pause');const paused=await exported.locator('#art').getAttribute('style');await exported.waitForTimeout(300);assert.equal(await exported.locator('#art').getAttribute('style'),paused);
  await exported.close();
  await page.keyboard.press('Alt+2');
  await page.click('#motions [data-value="trace"]');await page.waitForFunction(()=>valid&&project.animation.name==='trace');
  await page.click('[data-tune="motion"]');
  assert(await page.getByLabel('Trace path',{exact:true}).locator('option[value="letter"]').innerText()==='Each letter together');
  await page.keyboard.press('Escape');
  await page.keyboard.press('Alt+3');await page.selectOption('#format','html');
  const [traceFile]=await Promise.all([page.waitForEvent('download'),page.click('#download')]);
  const ts=await traceFile.createReadStream(),tc=[];for await(const chunk of ts)tc.push(chunk);
  const traceDocument=Buffer.concat(tc).toString();
  const tracePayload=JSON.parse(traceDocument.match(/<script id="meowtext-animation" type="application\/json">(.*?)<\/script>/s)[1]);
  assert.equal(tracePayload.loop,false);assert(tracePayload.count>1&&tracePayload.count<100);
  const tracePage=await context.newPage();await tracePage.setContent(traceDocument);
  const starts=await tracePage.evaluate(()=>{paintFrame(0);return [...document.querySelectorAll('#art .glyph')].filter(e=>e.textContent.trim()).length;});
  assert(starts>=await page.evaluate(()=>project.text.replace(/\s/g,'').length),'every letter must start on the first frame');
  const full=await tracePage.evaluate(()=>{paintFrame(data.count-1);return document.querySelector('#art').textContent;});
  assert(full.trim().length>starts);await tracePage.close();
  await page.keyboard.press('Alt+2');assert.equal(await page.locator('#looks button').count(),40);
  for(const motion of ['shimmer','ripple','breathe','wave']){
    await page.click(`#motions [data-value="${motion}"]`);await page.waitForFunction(name=>valid&&project.animation.name===name,motion);
    const first=await page.locator('#art').getAttribute('src');await page.waitForTimeout(550);assert.notEqual(await page.locator('#art').getAttribute('src'),first,motion);
  }
  await page.click('#looks [data-value="aurora"]');await page.waitForFunction(()=>valid&&project.style.gradient==='aurora');
  await page.click('[data-tune="motion"]');assert.equal(await page.getByLabel('Animated layers',{exact:true}).isVisible(),false);await page.keyboard.press('Escape');
  for(const width of [320,390,768,1024,1366,1920]){
    await page.setViewportSize({width,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow at ${width}`);
    await page.click('[data-tune="edge"]');
    await page.getByLabel('Border enabled',{exact:true}).check();await page.waitForFunction(()=>valid&&project.style.outline);
    await page.getByLabel('Distance from letters',{exact:true}).fill('4');await page.waitForFunction(()=>valid&&project.style.outline_distance===4);
    assert.equal(await page.getByLabel('Distance from letters',{exact:true}).evaluate(e=>e===document.activeElement),true,'number inputs preview without blur');
    await page.getByLabel('Shadow character · blank uses letters',{exact:true}).focus();
    const visibleArt=await page.locator('.stage').boundingBox();
    assert(visibleArt.y>=-1&&visibleArt.y+visibleArt.height<800,`artwork stays visible while tuning at ${width}px`);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Tune overflow at ${width}`);
    if(width===390||width===1366)await page.screenshot({path:`/tmp/meowtext-inline-tune-${width}.png`});
    await page.keyboard.press('Escape');
  }
  assert.deepEqual(errors,[]);await context.close();
  const failure=await browser.newContext();let fail=true;
  await failure.route('**/pyodide.asm.wasm',route=>{if(fail){fail=false;return route.fulfill({status:503,body:'temporary outage'});}return route.continue();});
  const retry=await failure.newPage();await retry.goto(base);await retry.fill('#words','KEEP ME');
  await retry.waitForFunction(()=>document.querySelector('#load-heading').textContent.includes('could not'));
  await retry.waitForTimeout(300);assert((await retry.locator('#load-heading').innerText()).includes('could not'),'late downloads must not overwrite a failure');
  assert((await retry.locator('#load-detail').innerText()).includes('503'));
  await retry.click('#retry');await retry.waitForFunction(()=>document.querySelector('#loader').hidden);
  assert.equal(await retry.evaluate(()=>project.text),'KEEP ME');await failure.close();
  const reduced=await browser.newPage({reducedMotion:'reduce'});await reduced.goto(base);await reduced.waitForFunction(()=>document.querySelector('#loader').hidden);
  assert.equal(await reduced.evaluate(()=>playing),false);assert((await reduced.locator('#motions img').first().getAttribute('src')).includes('-still'));
  console.log('PASS: comparisons, keyboard controls, readable gradients, new presets/motions, exact PNG, animated GIF/Kitty, actual HTML5 colour cycling, phone layouts, failed startup/retry, typed words, reduced motion');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.close();});
