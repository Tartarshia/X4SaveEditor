// Uses the synthetic SECTOR_SAVE and make_game fixtures from test_gameplay.py.
const {chromium}=require(process.env.X4_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  const wait=()=>page.waitForFunction(()=>!busy);
  try{
    await page.goto(process.env.X4_WEB_URL||'http://127.0.0.1:8765');
    await page.waitForFunction(()=>token.length>10);await wait();
    await page.locator('#open').click();await page.locator('#file').setInputFiles(path.resolve(__dirname,'../.local/gameplay-smoke/sectors.xml'));
    await page.locator('#moneyAmount').waitFor();await wait();
    await page.locator('#gameSettings').click();await page.locator('#gamePath').fill(path.resolve(__dirname,'../.local/gameplay-smoke/game'));await page.locator('#loadGameData').click();await wait();
    await page.locator('[data-tab=cargo]').click();await wait();
    assert.equal(await page.locator('#featureShip optgroup').count(),3);
    const regions=await page.locator('#featureSector option').evaluateAll(items=>items.map(i=>({value:i.value,label:i.textContent})));
    const a=regions.find(i=>i.label.includes('测试星区甲')).value;
    const b=regions.find(i=>i.label.includes('测试星区乙')).value;
    await page.locator('#featureSector').selectOption(b);await wait();
    assert.equal(await page.locator('#featureShip').inputValue(),'');
    assert.equal(await page.locator('#featureShip optgroup').count(),1);
    assert((await page.locator('#featureShip').textContent()).includes('Other'));
    assert(!(await page.locator('#featureShip').textContent()).includes('Docked'));
    await page.locator('[data-tab=crew]').click();await wait();
    assert.equal(await page.locator('#featureSector').inputValue(),b);
    assert.equal(await page.locator('#featureBody tbody tr').count(),1);
    assert((await page.locator('#featureBody tbody').textContent()).includes('Other'));
    await page.locator('#featureSector').selectOption(a);await wait();
    assert.equal(await page.locator('#featureBody tbody tr').count(),2);
    assert((await page.locator('#featureBody tbody').textContent()).includes('Manager'));
    const ship=await page.locator('#featureShip option').evaluateAll(items=>items.find(i=>i.textContent.includes('Docked')).value);
    await page.locator('#featureShip').selectOption(ship);await wait();
    assert.equal(await page.locator('#featureBody tbody tr').count(),1);
    await page.locator('#selectFeaturePage').check();await page.getByRole('button',{name:'应用到所选船员'}).click();await wait();
    assert.equal(await page.locator('#changeCount').textContent(),'1');
    await page.locator('#featureSector').selectOption('unknown');await wait();
    assert.equal(await page.locator('#featureShip').inputValue(),'');
    assert.equal(await page.locator('#featureBody tbody tr').count(),1);
    assert((await page.locator('#featureBody tbody').textContent()).includes('Unknown'));
    assert.equal(await page.locator('#selectFeaturePage').isChecked(),false);
    await page.setViewportSize({width:700,height:850});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);
    console.log('PASS: sector grouping, docked ship location, shared filters, station crew, stale selection reset, scoped bulk edits, unknown sector, narrow layout');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
