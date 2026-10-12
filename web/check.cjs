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
  assert.equal(await page.locator('#tune').evaluate(dialog=>dialog.open),true,`Tune must open: ${errors.join('; ')}`);
  await page.getByLabel('Palette',{exact:true}).selectOption('fire');await page.waitForFunction(()=>valid&&project.style.gradient==='fire');
  assert.equal(await page.evaluate(()=>project.style.stops),null,'a previous solid must not override a chosen gradient');
  await page.keyboard.press('Escape');await page.click('#motions [data-value="hue"]');await page.waitForFunction(()=>valid);
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
  for(const width of [320,390,768,1024,1366,1920]){
    await page.setViewportSize({width,height:800});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`overflow at ${width}`);
  }
  assert.deepEqual(errors,[]);await context.close();
  const failure=await browser.newContext();let fail=true;
  await failure.route('**/pyodide.asm.wasm',route=>{if(fail){fail=false;return route.fulfill({status:503,body:'temporary outage'});}return route.continue();});
  const retry=await failure.newPage();await retry.goto(base);await retry.fill('#words','KEEP ME');
  await retry.waitForFunction(()=>document.querySelector('#load-heading').textContent.includes('could not'));
  assert((await retry.locator('#load-detail').innerText()).includes('503'));
  await retry.click('#retry');await retry.waitForFunction(()=>document.querySelector('#loader').hidden);
  assert.equal(await retry.evaluate(()=>project.text),'KEEP ME');await failure.close();
  const reduced=await browser.newPage({reducedMotion:'reduce'});await reduced.goto(base);await reduced.waitForFunction(()=>document.querySelector('#loader').hidden);
  assert.equal(await reduced.evaluate(()=>playing),false);assert((await reduced.locator('#motions img').first().getAttribute('src')).includes('-still'));
  console.log('PASS: comparisons, keyboard controls, palette precedence, exact PNG, animated Kitty, phone layouts, failed startup/retry, typed words, reduced motion');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();server.close();});
