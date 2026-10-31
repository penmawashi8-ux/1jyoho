const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({viewport:{width:1280,height:670}});
  for (const n of ['free','paid','steps']) {
    await p.goto('file://'+process.cwd()+'/'+n+'.html', {waitUntil:'networkidle'});
    await p.evaluate(()=>document.fonts.ready);
    await p.screenshot({path:n+'.png'});
  }
  await b.close();
})();
