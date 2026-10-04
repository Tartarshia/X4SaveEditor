// Optional Edge check with test_encyclopedia synthetic provenance fixtures.
const {chromium}=require(process.env.X4_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  const base=process.env.X4_WEB_URL||'http://127.0.0.1:8765',wait=()=>page.waitForFunction(()=>!busy);
  try{
    await page.goto(base);await page.waitForFunction(()=>token.length>10);await wait();
    await page.locator('#gameSettings').click();await page.locator('#gamePath').fill(path.resolve(__dirname,'../.local/encyclopedia-smoke/game'));await page.locator('#loadGameData').click();await wait();
    await page.locator('#open').click();await page.locator('#file').setInputFiles(path.resolve(__dirname,'../.local/encyclopedia-smoke/save.xml'));await page.locator('#moneyAmount').waitFor();await wait();
    await page.locator('[data-tab=encyclopedia]').click();await wait();
    await page.getByRole('combobox',{name:'百科 DLC 筛选'}).selectOption('ego_dlc_split');await wait();
    await page.getByRole('combobox',{name:'百科分类'}).selectOption('inventory_wares');await wait();
    assert.equal(await page.locator('#featureBody tbody tr').count(),100);
    assert.equal(await page.locator('#featureBody .sector-source-badge').filter({hasText:'Test Split'}).count(),100);
    const first=page.locator('#featureBody tbody tr').filter({has:page.getByText('dlc_item_0',{exact:false})}).first();
    await first.getByRole('button',{name:'解锁此条目'}).click();await wait();
    await page.getByRole('button',{name:'下一页',exact:true}).click();await wait();assert.equal(await page.locator('#featureBody tbody tr').count(),21);
    await page.getByRole('combobox',{name:'百科 DLC 筛选'}).selectOption('base');await wait();
    assert(await page.locator('#featureBody tbody tr').filter({hasText:'Updated Training'}).isVisible());
    await page.getByRole('combobox',{name:'百科分类'}).selectOption('');await wait();
    await page.getByRole('combobox',{name:'百科解锁状态'}).selectOption('known');await wait();
    await page.getByRole('combobox',{name:'百科 DLC 筛选'}).selectOption('unknown');await wait();
    assert.equal(await page.locator('#featureBody tbody tr').count(),1);assert(await page.locator('#featureBody .sector-source-badge').filter({hasText:'来源未确认'}).isVisible());
    await page.locator('#stageAll').click();await wait();assert.equal(await page.locator('#errorDialog').isVisible(),false);
    await page.locator('[data-tab=map]').click();await wait();
    const station=page.locator('#featureBody tbody tr').filter({hasText:'Factory A'}).filter({hasText:'station'});
    assert(await station.getByText('玩家资产 · 已知',{exact:true}).isVisible());assert.equal(await station.getByRole('button',{name:'发现',exact:true}).count(),0);
    const enemy=page.locator('#featureBody tbody tr').filter({hasText:'Enemy Factory'});assert(await enemy.getByText('未发现',{exact:true}).isVisible());
    await page.locator('#export').click();await page.locator('#exportName').fill('encyclopedia-source.xml');await page.locator('#confirmExport').click();await page.locator('#resultDialog').waitFor();await wait();
    const url=await page.locator('#download').getAttribute('href');const xml=await(await page.request.get(base+url)).text();
    const result=await page.evaluate(xml=>{const d=new DOMParser().parseFromString(xml,'text/xml');return {unlocked:d.querySelectorAll('known entries[type="inventory_wares"] entry[id="dlc_item_0"]').length,stationKnown:d.querySelector('component[name="Factory A"]').getAttribute('known')};},xml);
    assert.deepEqual(result,{unlocked:1,stationKnown:null});
    await page.locator('#resultDialog [data-close]').click();await page.locator('[data-tab=encyclopedia]').click();await wait();await page.setViewportSize({width:700,height:900});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
    console.log('PASS: encyclopedia DLC labels/filter/pagination, patched base provenance, retained unlock draft, unknown origin, owned station discovery display, unchanged station XML, export, narrow layout');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
