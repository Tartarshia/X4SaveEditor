// Optional Edge check using only the synthetic test_terraforming fixture.
const {chromium}=require(process.env.X4_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  const base=process.env.X4_WEB_URL||'http://127.0.0.1:8765';const wait=()=>page.waitForFunction(()=>!busy);
  try{
    await page.goto(base);await page.waitForFunction(()=>token.length>10);await wait();
    await page.locator('#gameSettings').click();await page.locator('#gamePath').fill(path.resolve(__dirname,'../.local/terraforming-smoke/game'));await page.locator('#loadGameData').click();await wait();
    await page.locator('#open').click();await page.locator('#file').setInputFiles(path.resolve(__dirname,'../.local/terraforming-smoke/save.xml'));await page.locator('#moneyAmount').waitFor();await wait();
    await page.locator('[data-tab=hq]').click();await wait();
    const temperature=page.getByRole('spinbutton',{name:'temperature 改造指标',exact:true});await temperature.fill('5');
    assert.equal(await page.getByRole('spinbutton',{name:'population 改造指标'}).count(),0);
    await temperature.locator('..').getByRole('button',{name:'查看原始 XML'}).first().click();await wait();
    assert(await page.locator('#workspace').isVisible());await page.getByRole('button',{name:'返回功能页面'}).click();await wait();assert.equal(await temperature.inputValue(),'5');
    await page.getByRole('button',{name:'补齐总部资源',exact:true}).click();await wait();
    await page.getByRole('textbox',{name:'筛选改造项目',exact:true}).fill('Housing');await page.getByRole('button',{name:'筛选项目',exact:true}).click();await wait();
    assert.equal(await temperature.inputValue(),'5');assert.equal(await page.getByRole('button',{name:'补齐总部资源',exact:true}).count(),0);
    await page.locator('#stageAll').click();await wait();assert.equal(await page.locator('#errorDialog').isVisible(),false);
    await page.locator('#export').click();await page.locator('#exportName').fill('terraforming-browser.xml');await page.locator('#confirmExport').click();await page.locator('#resultDialog').waitFor();await wait();
    const url=await page.locator('#download').getAttribute('href');const xml=await(await page.request.get(base+url)).text();
    const result=await page.evaluate(xml=>{const d=new DOMParser().parseFromString(xml,'text/xml');return {temperature:d.querySelector('terraforming stat[id="temperature"]').getAttribute('value'),population:d.querySelector('terraforming stat[id="population"]').getAttribute('value'),mission:d.querySelector('terraforming').getAttribute('missioncue'),start:d.querySelector('terraforming project[id="water"]').getAttribute('starttime'),stock:d.querySelector('component[macro="station_pla_headquarters_base_01_macro"] cargo ware').getAttribute('amount')};},xml);
    assert.deepEqual(result,{temperature:'5',population:'250000000',mission:'123',start:'-1',stock:'2'});
    await page.locator('#resultDialog [data-close]').click();await page.setViewportSize({width:700,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.deepEqual(errors,[]);console.log('PASS: terraforming indicators, read-only population, project resource supply, XML return, retained drafts, combined export, narrow layout');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
