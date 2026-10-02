// Optional Edge check; prepare .local/management-smoke using test_management fixtures.
const {chromium}=require(process.env.X4_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.X4_WEB_URL||'http://127.0.0.1:8765';
  const wait=async()=>{await page.waitForFunction(()=>!busy);};
  const tab=async name=>{await page.locator(`[data-tab=${name}]`).click();await wait();};
  const stage=async()=>{await page.locator('#stageAll').click();await wait();};
  try{
    await page.goto(base);await page.waitForFunction(()=>token.length>10);await wait();page.on('dialog',d=>d.accept());
    await page.locator('#gameSettings').click();await page.locator('#gamePath').fill(path.resolve(__dirname,'../.local/management-smoke/game'));await page.locator('#loadGameData').click();await wait();
    await page.locator('#open').click();await page.locator('#file').setInputFiles(path.resolve(__dirname,'../.local/management-smoke/save.xml'));await page.locator('#moneyAmount').waitFor();await wait();
    await tab('blueprints');await page.getByRole('combobox',{name:'蓝图分类'}).selectOption('ships');await wait();
    await page.getByRole('checkbox',{name:'选择 Test Ship Blueprint',exact:true}).check();
    await page.getByRole('combobox',{name:'蓝图分类'}).selectOption('modules');await wait();
    await page.getByRole('checkbox',{name:'选择 Test Module Blueprint',exact:true}).check();await stage();
    assert.equal(await page.locator('#changeCount').textContent(),'2');
    await tab('ship_mods');
    const mass=page.getByRole('spinbutton',{name:/ mass 改装值$/});
    await mass.fill('-99');await page.locator('#stageAll').click();await page.locator('#errorDialog').waitFor();
    await page.locator('#errorDialog [data-close]').last().click();
    await page.getByRole('button',{name:'当前飞船全部改装取最优'}).click();await wait();
    assert.equal(await mass.inputValue(),'-25');
    assert.equal(await page.getByRole('spinbutton',{name:/ damage 改装值$/}).inputValue(),'25');
    assert(await page.getByRole('spinbutton',{name:/ mystery 改装值$/}).isDisabled());
    await stage();assert.equal(await page.locator('#changeCount').textContent(),'6');
    await page.screenshot({path:path.resolve(__dirname,'../.local/management-mods.png')});
    await tab('hq');await page.getByRole('combobox',{name:'research_top 科研状态',exact:true}).selectOption('1');await wait();
    assert.equal(await page.getByRole('combobox',{name:'research_advanced 科研状态',exact:true}).inputValue(),'1');
    assert.equal(await page.getByRole('combobox',{name:'research_aux 科研状态',exact:true}).inputValue(),'1');
    await stage();assert.equal(await page.locator('#changeCount').textContent(),'7');
    await tab('relations');await page.getByRole('combobox',{name:'选择许可证势力'}).selectOption('argon');await wait();
    await page.getByRole('combobox',{name:'argon trade 许可证',exact:true}).selectOption('1');await wait();
    assert.equal(await page.getByRole('combobox',{name:'argon friend 许可证',exact:true}).inputValue(),'1');
    await stage();assert.equal(await page.locator('#changeCount').textContent(),'8');
    await tab('station_resources');const factory=await page.getByRole('combobox',{name:'选择空间站'}).locator('option').filter({hasText:'Factory A'}).getAttribute('value');
    await page.getByRole('combobox',{name:'选择空间站'}).selectOption(factory);await wait();
    await page.getByRole('spinbutton',{name:'argon 劳动力目标人数'}).fill('100');
    await page.getByRole('spinbutton',{name:'boron 劳动力目标人数'}).fill('50');await stage();
    assert.equal(await page.locator('#changeCount').textContent(),'10');
    await tab('hq');assert.equal(await page.getByRole('combobox',{name:'research_top 科研状态',exact:true}).inputValue(),'1');
    await page.locator('#export').click();await page.locator('#exportName').fill('management-browser.xml');await page.locator('#confirmExport').click();await page.locator('#resultDialog').waitFor();
    const url=await page.locator('#download').getAttribute('href');const xml=await(await page.request.get(base+url)).text();
    for(const text of ['ware="ship_test"','ware="module_test"','mass="0.75"','damage="1.25"','ware="research_advanced"','ware="research_top"','type="friend" factions="teladi argon"','race="argon" amount="100"','race="boron" amount="50"'])assert(xml.includes(text),text);
    assert(xml.includes('ware="mod_ship_test" mass="0.9" drag="0.98"'));
    await page.locator('#resultDialog [data-close]').click();await page.setViewportSize({width:700,height:850});
    for(const name of ['hq','relations','ship_mods','station_resources']){await tab(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name);}
    await page.screenshot({path:path.resolve(__dirname,'../.local/management-mobile.png')});assert.deepEqual(errors,[]);
    console.log('PASS: ship/module blueprints, mod bounds/best values, research dependencies, licences, workforce, export, narrow layouts');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
