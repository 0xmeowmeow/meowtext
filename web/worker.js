/* Python runs off the UI thread. Nothing the visitor types leaves this worker. */
let runtime;
let serial = Promise.resolve();
self.onmessage = event => {
  serial = serial.then(async () => {
    const {id, ...request} = event.data;
    try {
      if (!runtime) {
        postMessage({status: 'Loading the renderer…'});
        await import('./pyodide/pyodide.js');
        runtime = await self.loadPyodide({indexURL: new URL('pyodide/', self.location.href).href});
        postMessage({status: 'Loading image tools and fonts…'});
        const [response] = await Promise.all([fetch('runtime.zip'), runtime.loadPackage('pillow')]);
        if (!response.ok) throw new Error('Could not load the Meowtext renderer. Reload to retry.');
        runtime.unpackArchive(await response.arrayBuffer(), 'zip', {extractDir: '/app'});
        runtime.runPython("import sys; sys.path.insert(0, '/app')\nimport bridge\nbridge.raster.MONO_FONT = '/app/DejaVuSansMono.ttf'");
      }
      runtime.globals.set('browser_request', JSON.stringify(request));
      const result = JSON.parse(runtime.runPython('bridge.dispatch(browser_request)'));
      postMessage({id, result});
    } catch (error) {
      postMessage({id, error: String(error.message || error).split('\n').filter(Boolean).slice(-1)[0]});
    }
  });
};
