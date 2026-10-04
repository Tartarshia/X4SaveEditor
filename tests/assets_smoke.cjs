// Optional Edge check using test_assets synthetic data only.
const {chromium}=require(process.env.X4_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  const base=process.env.X4_WEB_URL||'http://127.0.0.1:8765';const wait=()=>page.waitForFunction(()=>!busy);
  const tab=async name=>{await page.locator(`[data-tab=${name}]`).click();await wait();};
  const panel=async name=>{await page.locator(`[data-asset-panel=${name}]`).click();await wait();};
  try{
    await page.goto(base);await page.waitForFunction(()=>token.length>10);await wait();
    await page.locator('#gameSettings').click();await page.locator('#gamePath').fill(path.resolve(__dirname,'../.local/assets-smoke/game'));await page.locator('#loadGameData').click();await wait();
    await page.locator('#open').click();await page.locator('#file').setInputFiles(path.resolve(__dirname,'../.local/assets-smoke/save.xml'));await page.locator('#moneyAmount').waitFor();await wait();
    await tab('assets');await page.getByRole('button',{name:'查看资产 ship',exact:true}).click();await wait();
    assert.equal(await page.getByRole('combobox',{name:'选择飞船',exact:true}).count(),0);
    const ore=page.getByRole('spinbutton',{name:'ore 数量',exact:true});await ore.fill('4');
    await panel('ammunition');await page.getByRole('spinbutton',{name:'missile_test_macro 弹药部署物数量'}).fill('4');
    await panel('mods');await page.getByRole('spinbutton',{name:/ mass 改装值$/}).fill('-25');
    await panel('roster');await page.getByRole('spinbutton',{name:'service 目标船员人数'}).fill('2');
    await panel('crew');const pilot=page.getByRole('combobox',{name:/ 驾驶$/}).first();await pilot.selectOption('15');
    await pilot.locator('..').getByRole('button',{name:'查看原始 XML'}).click();await wait();assert(await page.locator('#workspace').isVisible());
    await page.getByRole('button',{name:'返回功能页面'}).click();await wait();assert(await page.locator('#assetContent').isVisible());assert.equal(await page.getByRole('combobox',{name:/ 驾驶$/}).first().inputValue(),'15');
    await panel('inventory');assert.equal(await page.getByRole('combobox',{name:'选择物品持有人'}).locator('option').count(),1);await page.getByRole('spinbutton',{name:'inv_training 目标数量'}).fill('5');
    await panel('cargo');assert.equal(await ore.inputValue(),'4');
    await page.getByRole('button',{name:'在地图中查看'}).click();await wait();assert.equal(await page.locator('.gate-connection').count(),1);
    await page.getByRole('combobox',{name:'地图 DLC 筛选'}).selectOption('ego_dlc_split');await wait();assert.equal(await page.getByRole('combobox',{name:'地图星区'}).locator('option').count(),1);assert(await page.getByText('此星区没有已定位的玩家飞船或空间站。').isVisible());
    await page.getByRole('combobox',{name:'地图势力筛选'}).selectOption('argon');await wait();assert(await page.getByText('当前 DLC 与势力条件下没有匹配星区。').isVisible());
    await page.getByRole('combobox',{name:'地图 DLC 筛选'}).selectOption('');await wait();assert.equal(await page.locator('.galaxy-map g').filter({visible:true}).count(),1);
    await page.getByRole('button',{name:'管理资产 ST-A',exact:true}).click();await wait();
    await page.getByRole('spinbutton',{name:'Factory A 空间站资金目标余额'}).fill('100');
    await panel('resources');await page.getByRole('spinbutton',{name:'空间站库存 ore 目标总量',exact:true}).fill('4');
    await panel('workforce');await page.getByRole('spinbutton',{name:'argon 劳动力目标人数'}).fill('50');
    await panel('trade');await page.getByRole('spinbutton',{name:'ore buy 价格',exact:true}).fill('15');
    await panel('crew');const manager=page.getByRole('combobox',{name:/ 管理$/});assert.equal(await manager.count(),1);await manager.selectOption('6');
    await panel('inventory');assert.equal(await page.getByRole('spinbutton',{name:'inv_training 目标数量'}).count(),0);assert(await page.getByRole('spinbutton',{name:'inv_setapart 目标数量'}).isVisible());
    await page.locator('#stageAll').click();await wait();assert.equal(await page.locator('#errorDialog').isVisible(),false);
    await page.locator('#export').click();await page.locator('#exportName').fill('asset-browser.xml');await page.locator('#confirmExport').click();await page.locator('#resultDialog').waitFor();await wait();
    const url=await page.locator('#download').getAttribute('href');const xml=await(await page.request.get(base+url)).text();
    const result=await page.evaluate(xml=>{const d=new DOMParser().parseFromString(xml,'text/xml'),ship=d.querySelector('component[id="ship"]'),factory=d.querySelector('component[name="Factory A"]');return {cargo:ship.querySelector('component[class="storage"] cargo ware[ware="ore"]').getAttribute('amount'),missile:ship.querySelector('available item').getAttribute('amount'),mass:ship.querySelector('modification ship').getAttribute('mass'),service:ship.querySelectorAll('people person[role="service"]').length,training:ship.querySelector(':scope > inventory ware').getAttribute('amount'),funds:factory.querySelector(':scope > account').getAttribute('amount'),stock:String([...factory.querySelectorAll('component[class="storage"] cargo ware[ware="ore"]')].reduce((sum,w)=>sum+Number(w.getAttribute('amount')),0)),workforce:factory.querySelector('workforce[race="argon"]').getAttribute('amount'),price:factory.querySelector('prices > ware').getAttribute('buy'),manager:d.querySelector('component[name="Manager"] skills').getAttribute('management')};},xml);
    assert.deepEqual(result,{cargo:'4',missile:'4',mass:'0.75',service:2,training:'5',funds:'100',stock:'4',workforce:'50',price:'15',manager:'6'});
    await page.locator('#resultDialog [data-close]').click();await page.setViewportSize({width:700,height:900});
    for(const name of ['funds','resources','workforce','trade','crew','inventory']){await panel(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name);}
    await page.screenshot({path:path.resolve(__dirname,'../.local/assets-mobile.png')});assert.deepEqual(errors,[]);
    console.log('PASS: unified ship/station management, retained drafts, scoped skills/inventory/accounts, XML return, DLC/owner map filters, connections, sector asset navigation, export, narrow layout');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
