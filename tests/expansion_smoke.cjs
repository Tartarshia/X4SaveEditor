// Optional Edge checks with the wholly synthetic test_expansion fixture.
const {chromium}=require(process.env.X4_PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  const base=process.env.X4_WEB_URL||'http://127.0.0.1:8765';
  const wait=()=>page.waitForFunction(()=>!busy);
  const tab=async name=>{await page.locator(`[data-tab=${name}]`).click();await wait();};
  const stage=async()=>{await page.locator('#stageAll').click();await wait();assert.equal(await page.locator('#errorDialog').isVisible(),false);};
  try{
    await page.goto(base);await page.waitForFunction(()=>token.length>10);await wait();
    await page.locator('#gameSettings').click();await page.locator('#gamePath').fill(path.resolve(__dirname,'../.local/expansion-smoke/game'));await page.locator('#loadGameData').click();await wait();
    await page.locator('#open').click();await page.locator('#file').setInputFiles(path.resolve(__dirname,'../.local/expansion-smoke/save.xml'));await page.locator('#moneyAmount').waitFor();await wait();
    await tab('ship_mods');
    const hull=page.locator('#featureBody > .resource-group').filter({has:page.locator('h3',{hasText:'船体 ·'})});
    await hull.locator('summary').click();
    await hull.getByRole('checkbox',{name:/选择附加属性 drag$/}).uncheck();
    await hull.getByRole('checkbox',{name:/选择附加属性 unitcapacity$/}).check();
    await hull.getByRole('spinbutton',{name:/配置 mass$/}).fill('-25');
    await hull.getByRole('spinbutton',{name:/配置 unitcapacity$/}).fill('4');
    await hull.getByRole('button',{name:'加入改装配置草稿'}).click();await wait();await stage();
    await tab('blueprints');await page.locator('#blueprintOwnership').selectOption('owned');await wait();
    await page.getByRole('button',{name:'撤销此蓝图'}).click();await wait();await stage();
    await tab('ammunition');await page.getByRole('spinbutton',{name:'missile_test_macro 弹药部署物数量'}).fill('4');
    const deploy=page.locator('#featureBody > .resource-group').filter({has:page.locator('h3',{hasText:'部署物 ·'})});
    await deploy.getByRole('spinbutton',{name:'部署物添加数量'}).fill('3');await deploy.getByRole('button',{name:'加入待修改',exact:true}).click();await wait();await stage();
    await tab('ship_service');await page.getByRole('spinbutton',{name:/船体百分比$/}).first().fill('100');await stage();
    const engine=page.locator('#featureBody > .resource-group').filter({has:page.getByRole('combobox',{name:/更换装备$/})});
    await engine.getByRole('combobox',{name:/更换装备$/}).selectOption('engine_alt_macro');await engine.getByRole('button',{name:'加入换装草稿'}).click();await wait();await stage();
    await tab('crew_roster');await page.getByRole('spinbutton',{name:'service 目标船员人数'}).fill('3');await stage();
    await tab('map');await page.getByRole('button',{name:'发现此星区',exact:true}).click();await wait();
    await page.getByRole('button',{name:'揭示探索区域',exact:true}).click();await wait();await stage();
    await page.screenshot({path:path.resolve(__dirname,'../.local/expansion-map.png')});
    await tab('encyclopedia');assert.equal(await page.getByRole('combobox',{name:'百科解锁状态'}).inputValue(),'unknown');
    await page.getByRole('combobox',{name:'百科解锁状态'}).selectOption('known');await wait();assert.equal(await page.getByRole('button',{name:'解锁此条目'}).count(),0);assert(await page.locator('#featureBody tbody tr').count()>0);
    await page.getByRole('combobox',{name:'百科解锁状态'}).selectOption('unknown');await wait();
    await page.getByRole('combobox',{name:'百科分类'}).selectOption('missiletypes');await wait();await page.getByRole('button',{name:'解锁此条目'}).click();await wait();await stage();
    await tab('hq');await page.locator('#featureBody tr').filter({hasText:'Research Advanced'}).getByRole('button',{name:'补齐所需资源'}).click();await wait();
    await page.getByRole('spinbutton',{name:'research_aux 科研剩余时间'}).fill('0');await stage();
    await tab('station_resources');const factory=await page.getByRole('combobox',{name:'选择空间站'}).locator('option').filter({hasText:'Factory A'}).getAttribute('value');
    await page.getByRole('combobox',{name:'选择空间站'}).selectOption(factory);await wait();
    await page.getByRole('spinbutton',{name:'ore buy 价格',exact:true}).fill('15');await page.getByRole('combobox',{name:'ore buy 交易规则',exact:true}).selectOption('5');
    await page.getByRole('textbox',{name:'空间站交易限制势力'}).fill('player argon');await page.getByRole('spinbutton',{name:'ore 仓储配额'}).fill('8');await stage();
    await page.locator('#export').click();await page.locator('#exportName').fill('expansion-browser.xml');await page.locator('#confirmExport').click();await page.locator('#resultDialog').waitFor();await wait();
    const url=await page.locator('#download').getAttribute('href');const xml=await(await page.request.get(base+url)).text();
    const checks=await page.evaluate(xml=>{const doc=new DOMParser().parseFromString(xml,'text/xml');const ship=doc.querySelector('component[id="ship"]');const mod=ship.querySelector(':scope > modification > ship');const factory=doc.querySelector('component[name="Factory A"]');const hq=doc.querySelector('component[macro="station_pla_headquarters_base_01_macro"]');return {
      mass:mod.getAttribute('mass'),drag:mod.getAttribute('drag'),units:mod.getAttribute('unitcapacity'),blueprints:doc.querySelectorAll('blueprint[ware="old_engine"]').length,
      missile:ship.querySelector('ammunition > available > item[macro="missile_test_macro"]').getAttribute('amount'),deploy:ship.querySelector('ammunition > available > item[macro="deploy_test_macro"]').getAttribute('amount'),launched:ship.querySelector('ammunition > launched > item').getAttribute('amount'),
      hull:ship.querySelector(':scope > hull').getAttribute('value'),engine:ship.querySelector('component[class="engine"]').getAttribute('macro'),service:ship.querySelectorAll(':scope > people > person[role="service"]').length,
      known:doc.querySelector('component[class="sector"]').getAttribute('known'),fog:[...doc.querySelectorAll('discovered quadtree node')].map(n=>n.getAttribute('state')),
      encyclopedia:doc.querySelectorAll('known entries[type="missiletypes"] entry[id="missile_test_macro"]').length,
      time:hq.querySelector(':scope > production').getAttribute('endtime'),resources:hq.querySelector('cargo ware[ware="ore"]').getAttribute('amount'),
      price:factory.querySelector('trade > prices > ware').getAttribute('buy'),reference:factory.querySelector('trade > prices > reference > ware').getAttribute('buy'),rule:factory.querySelector('traderules wares ware').getAttribute('buy'),allocation:factory.querySelector('cargo ware[max]').getAttribute('max')};},xml);
    assert.deepEqual(checks,{mass:'0.75',drag:null,units:'4',blueprints:0,missile:'4',deploy:'3',launched:'1',hull:'100',engine:'engine_alt_macro',service:3,known:'1',fog:['1','1','1','1'],encyclopedia:1,time:'100',resources:'2',price:'15',reference:'9',rule:'5',allocation:'8'});
    await page.locator('#resultDialog [data-close]').click();await tab('map');
    const largeMap=await page.evaluate(async()=>{
      const originalJob=job;const data=await originalJob('gameplay',{kind:'map',gamePath:gamePathValue});
      try{
        job=async(type,args)=>args.kind==='map'?{...data,sectors:Array.from({length:153},(_,i)=>({...data.sectors[0],id:10000+i,name:`Sector ${i}`,source:i%2?{id:'ego_dlc_split',name:'Test Split'}:{id:'base',name:'基础游戏'},x:Math.floor(i/3)%12,z:Math.floor(i/36),positionKnown:true})),selected:10000,objects:{rows:[],total:0,page:0}}:originalJob(type,args);
        await renderFeature();const boxes=[...document.querySelectorAll('.galaxy-map svg g')].map(g=>{const m=g.transform.baseVal.getItem(0).matrix;return {x:m.e,y:m.f};});
        return {count:boxes.length,overlap:boxes.some((a,i)=>boxes.some((b,j)=>j>i&&Math.abs(a.x-b.x)<150&&Math.abs(a.y-b.y)<64)),legend:document.querySelectorAll('.sector-source-badge').length,colors:new Set([...document.querySelectorAll('.sector-source-stripe')].map(r=>r.getAttribute('fill'))).size,sourceLabel:document.querySelector('.sector-source-name').textContent};
      }finally{job=originalJob;mapSector='';await renderFeature();}
    });
    assert.equal(largeMap.count,153);assert.equal(largeMap.overlap,false);
    assert.equal(largeMap.legend,2);assert.equal(largeMap.colors,2);assert.equal(largeMap.sourceLabel,'基础游戏');
    await page.setViewportSize({width:700,height:850});
    for(const name of ['ship_mods','ammunition','ship_service','crew_roster','map','encyclopedia','hq','station_resources']){await tab(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),name);}
    await page.screenshot({path:path.resolve(__dirname,'../.local/expansion-mobile.png')});assert.deepEqual(errors,[]);
    console.log('PASS: mod configuration, blueprint revocation, ammunition/deployables, repair/refit, crew counts, map/fog, encyclopedia, research resources/timers, station settings, combined export, narrow layout');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
