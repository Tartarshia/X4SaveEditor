'use strict';
const commands = new Map();
let gameHome=null, feature='money', featurePage=0, featureSearch='', selectedShip='', blueprintOwnership='missing';
let selectedSector='', shipSearch='';
let includeInternalFactions=false;
let stationSearch='', stationSector='', stationPage=0;
let gamePathValue='';
try { gamePathValue=localStorage.getItem('x4-game-path')||''; } catch {}
const titles={money:'玩家金钱',relations:'势力关系',cargo:'飞船货仓',blueprints:'解锁蓝图',crew:'船员技能'};
const skillNames={all:'全部五项技能',piloting:'驾驶',management:'管理',engineering:'工程',boarding:'登舰',morale:'士气'};
const groups={ships:'舰船',engines:'引擎',shields:'护盾',weapons:'武器',turrets:'炮塔',missiles:'导弹',drones:'无人机',countermeasures:'干扰弹',deployables:'部署物',modules:'空间站模块'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,fn,cls=''){const b=el('button',text,cls);b.dataset.work='';b.onclick=work(fn);return b;}
function numberInput(value,min=0,max=''){const n=el('input');n.type='number';n.min=min;n.max=max;n.step='1';n.value=value;n.dataset.work='';return n;}
function commandKey(c){return [c.kind,c.id||'',c.storage||'',c.skill||''].join(':');}
function advancedChanges(){const result={};for(const c of changes.values())(result[c.node]??={})[c.key]=c.value;return result;}
async function stage(list){
  if(!list.length)throw new Error('请先勾选要修改的项目');
  const next=new Map(commands);for(const c of list){
    if(c.kind==='crew'&&c.skill==='all')for(const [k,v] of next)if(v.kind==='crew'&&v.id===c.id)next.delete(k);
    next.delete(commandKey(c));next.set(commandKey(c),c);
  }
  const preview=await job('plan',{commands:[...next.values()],changes:advancedChanges(),gamePath:gamePathValue});
  commands.clear();for(const [key,c] of next)commands.set(key,c);updateCount();
  $('status').textContent=`已暂存 ${commands.size} 项功能修改；导出时写入 ${preview.patches} 处。`;
  await renderFeature();
}
function appendCommandReview(body){
  for(const [key,c] of commands){
    const tr=el('tr');cell(tr,c.label||titles[c.kind]||c.kind);cell(tr,c.original??'新增');cell(tr,c.kind==='blueprint'?'解锁':c.kind==='crew'?`${Number(c.value)/3} 星`:c.value);
    cell(tr,'').append(button('撤销',async()=>{commands.delete(key);updateCount();tr.remove();await renderFeature();}));body.append(tr);
  }
}
function showMode(){
  const advanced=feature==='advanced';
  $('gameplay').hidden=advanced;$('workspace').hidden=!advanced;$('shortcutSection').hidden=!advanced;document.querySelector('.search').hidden=!advanced;
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===feature));
  if(!advanced)$('featureTitle').textContent=titles[feature];
}
async function loadGameplay(){
  gameHome=await job('gameplay',{kind:'home',gamePath:gamePathValue});
  if(selectedSector&&!gameHome.sectors.some(s=>s.id===selectedSector))selectedSector='';
  if(selectedShip&&!gameHome.ships.some(s=>String(s.id)===String(selectedShip)&&(!selectedSector||s.sector.id===selectedSector)))selectedShip='';
  if(!selectedShip&&!selectedSector)selectedShip=gameHome.current||'';
  $('gameWarnings').hidden=!gameHome.warnings.length;$('gameWarningText').textContent=gameHome.warnings.join('\n');
  $('gamePath').value=gamePathValue||gameHome.gamePath;
  await renderFeature();
}
function table(headers){const wrap=el('div',undefined,'feature-table');const t=el('table');const head=el('thead');const tr=el('tr');for(const h of headers)tr.append(el('th',h));head.append(tr);const body=el('tbody');t.append(head,body);wrap.append(t);return {wrap,body};}
function shipPicker(parent,allowAll=false){
  const region=el('select');region.id='featureSector';region.setAttribute('aria-label','筛选星区');region.dataset.work='';
  const all=el('option','全部星区');all.value='';region.append(all);
  for(const sector of gameHome.sectors){
    if(!allowAll&&!sector.ships)continue;
    const option=el('option',`${sector.name} · ${sector.ships} 艘${allowAll?` / ${sector.crew} 人`:''}`);option.value=sector.id;region.append(option);
  }
  region.value=selectedSector;
  region.onchange=work(async()=>{selectedSector=region.value;selectedShip='';shipSearch='';featurePage=0;await renderFeature();});
  const select=el('select');select.id='featureShip';select.setAttribute('aria-label','选择飞船');select.dataset.work='';
  const search=el('input');search.placeholder='筛选飞船名称 / 识别码';search.setAttribute('aria-label','筛选飞船');search.dataset.work='';search.value=shipSearch;
  const fill=()=>{
    select.replaceChildren();
    const placeholder=el('option',allowAll?(selectedSector?'此星区全部玩家人员（含空间站）':'全部玩家人员（含空间站和未分配人员）'):'选择一艘玩家飞船');placeholder.value='';select.append(placeholder);
    for(const sector of gameHome.sectors){
      if(selectedSector&&sector.id!==selectedSector)continue;
      const group=el('optgroup');group.label=sector.name;
      for(const ship of gameHome.ships.filter(s=>s.sector.id===sector.id)){
        if(!(`${ship.name} ${ship.code}`.toLowerCase().includes(search.value.toLowerCase()))&&String(ship.id)!==String(selectedShip))continue;
        const option=el('option',`${ship.id===gameHome.current?'当前飞船 · ':''}${ship.name} ${ship.code}`);option.value=ship.id;group.append(option);
      }
      if(group.children.length)select.append(group);
    }
    select.value=String(selectedShip);
  };search.oninput=()=>{shipSearch=search.value;fill();};fill();
  select.onchange=work(async()=>{selectedShip=select.value;featurePage=0;await renderFeature();});
  parent.append(region,search,select);
}
function searchBar(parent){const bar=el('div',undefined,'feature-toolbar');const search=el('input');search.placeholder='搜索名称 / ID';search.setAttribute('aria-label','功能列表搜索');search.value=featureSearch;search.id='featureSearch';search.dataset.work='';const run=async()=>{featureSearch=search.value.trim();featurePage=0;await renderFeature();};search.onkeydown=work(e=>e.key==='Enter'?run():null);bar.append(search,button('搜索',run));parent.append(bar);return bar;}
function pages(parent,data){const bar=el('div',undefined,'feature-toolbar');bar.append(el('span',`共 ${fmt(data.total)} 项 · 第 ${data.page+1} 页 · 每页 100 项`));if(featurePage)bar.append(button('上一页',async()=>{featurePage--;await renderFeature();}));if((featurePage+1)*100<data.total)bar.append(button('下一页',async()=>{featurePage++;await renderFeature();}));parent.append(bar);}
async function renderFeature(){
  showMode();if(feature==='advanced'||!gameHome)return;
  const parent=$('featureBody');parent.replaceChildren();
  if(feature==='money'){
    const saved=commands.get('money:::');parent.append(el('p','玩家可用资金','muted'),el('div',`${fmt(gameHome.money||0)} Cr`,'money-value'));
    const box=el('div',undefined,'feature-toolbar');const input=numberInput(saved?.value??gameHome.money??0,0,999999999999999);input.id='moneyAmount';input.setAttribute('aria-label','玩家金钱');box.append(input,button('暂存金钱',()=>stage([{kind:'money',value:input.value,original:gameHome.money,label:'玩家金钱（同步共享账户）'}]),'primary'));
    parent.append(box);const presets=el('div',undefined,'feature-toolbar');for(const [label,value] of [['100 万',1000000],['1000 万',10000000],['1 亿',100000000],['10 亿',1000000000]])presets.append(button(label,()=>{input.value=value;}));parent.append(presets,el('p','统一修改玩家主账户、同 ID 账户和金钱摘要。输入完成后暂存，再点击右上角导出新存档。','hint'));if(saved)parent.append(el('p',`待导出：${fmt(saved.value)} Cr`,'pending'));
    await renderStationMoney(parent);return;
  }
  if(feature==='cargo'){await renderCargo(parent);return;}
  const bar=searchBar(parent);
  if(feature==='crew')shipPicker(bar,true);
  if(feature==='blueprints'){
    const filter=el('select');filter.id='blueprintOwnership';filter.setAttribute('aria-label','蓝图拥有状态');for(const [v,l] of [['missing','未拥有'],['owned','已有'],['all','全部']]){const o=el('option',l);o.value=v;filter.append(o);}filter.value=blueprintOwnership;filter.onchange=work(async()=>{blueprintOwnership=filter.value;featurePage=0;await renderFeature();});bar.append(filter);
    parent.append(el('p','从本机游戏目录列出未拥有的可制造蓝图。可按名称或 ID 搜索，勾选后批量解锁；不会重复添加已有蓝图。','muted'));
  }
  if(feature==='crew')parent.append(el('p','每 3 点技能 = 1 星。可编辑单人的单项技能，也可勾选本页人员批量设置。不会改变船员岗位。','muted'));
  if(feature==='relations')parent.append(el('p','同步双方基础关系，并将双方对彼此的临时加成归零。被游戏锁定的势力显示为只读；剧情仍可能再次改变关系。','muted'));
  const data=await job('gameplay',{kind:feature,search:featureSearch,page:featurePage,ship:selectedShip,sector:selectedSector,ownership:blueprintOwnership,includeInternal:includeInternalFactions,gamePath:gamePathValue});
  if(feature==='relations'){
    const label=el('label');const toggle=el('input');toggle.type='checkbox';toggle.id='includeInternalFactions';toggle.checked=includeInternalFactions;toggle.dataset.work='';
    toggle.onchange=work(async()=>{includeInternalFactions=toggle.checked;featurePage=0;await renderFeature();});
    label.append(toggle,document.createTextNode(` 显示 visitor 内部势力（${data.internalCount}）`));bar.append(label);
  }
  const selected=new Set();
  const bulk=el('div',undefined,'feature-toolbar');
  if(feature!=='relations'){
    const all=el('input');all.type='checkbox';all.id='selectFeaturePage';all.setAttribute('aria-label','选择本页');all.onchange=()=>{for(const box of parent.querySelectorAll('[data-pick]')){box.checked=all.checked;box.onchange();}};bulk.append(all,el('label','选择本页'));
    if(feature==='blueprints')bulk.append(button('解锁所选蓝图',()=>stage(data.rows.filter(r=>selected.has(r.id)).map(r=>({kind:'blueprint',id:r.id,label:`蓝图：${r.name} [${r.id}]`}))),'primary'));
    else {
      const skill=el('select');skill.id='bulkSkill';skill.setAttribute('aria-label','批量技能');for(const [v,l] of Object.entries(skillNames)){const o=el('option',l);o.value=v;skill.append(o);}const stars=starSelect(15);stars.id='bulkStars';
      bulk.append(skill,stars,button('应用到所选船员',()=>stage(data.rows.filter(r=>selected.has(r.id)).map(r=>({kind:'crew',id:r.id,skill:skill.value,value:stars.value,label:`${r.ship} / ${r.name} / ${skillNames[skill.value]}`,original:skill.value==='all'?'多项':`${r.skills[skill.value]/3} 星`}))),'primary'));
    }
    parent.append(bulk);
  }
  const t=table(feature==='relations'?['势力','玩家 → 势力','势力 → 玩家','设为','']:feature==='blueprints'?['选择','蓝图名称 / ID','分类','状态']:['选择','船员 / 岗位','星区','所属资产','技能（星级）','操作']);
  for(const r of data.rows){
    const tr=el('tr');
    if(feature==='relations'){
      cell(tr,`${r.name} [${r.id}]`);cell(tr,r.outgoing.toFixed(6));cell(tr,r.incoming.toFixed(6));
      const select=el('select');select.setAttribute('aria-label',`${r.id} 关系`);for(const [value,label] of [[-1,'完全敌对 (-1)'],[-0.1,'敌对 (-0.1)'],[0,'中立 (0)'],[0.01,'友好 (0.01)'],[0.1,'盟友 (0.1)'],[1,'最高关系 (1)']]){const o=el('option',label);o.value=value;select.append(o);}select.value=String(commands.get(`relation:${r.id}::`)?.value??0.1);select.disabled=r.locked;cell(tr,'').append(select);
      if(r.locked)cell(tr,'游戏锁定');else cell(tr,'').append(button('暂存',()=>stage([{kind:'relation',id:r.id,value:select.value,original:`${r.outgoing} / ${r.incoming}`,label:`势力关系：${r.name}`}])));
    }else{
      const pick=el('input');pick.type='checkbox';pick.setAttribute('aria-label',`选择 ${r.name}`);pick.dataset.pick=r.id;
      if(feature==='blueprints' && (r.owned||commands.has(`blueprint:${r.id}::`)))pick.disabled=true;
      if(!pick.disabled)pick.onchange=()=>{if(pick.checked)selected.add(r.id);else selected.delete(r.id);};else pick.removeAttribute('data-pick');cell(tr,'').append(pick);
      if(feature==='blueprints'){cell(tr,`${r.name}\n${r.id}`).className='named-cell';cell(tr,groups[r.group]||r.group);cell(tr,r.owned?'已拥有':commands.has(`blueprint:${r.id}::`)?'待解锁':'未拥有');}
      else{
        cell(tr,`${r.name}\n${r.role} · #${r.id}`).className='named-cell';cell(tr,r.sector.name);cell(tr,r.ship);
        const skillBox=el('div',undefined,'crew-skills');const inputs={};
        for(const k of Object.keys(r.skills)){const label=el('label',skillNames[k]);const pending=commands.get(`crew:${r.id}::${k}`)||commands.get(`crew:${r.id}::all`);const input=starSelect(pending?.value??r.skills[k]);input.setAttribute('aria-label',`${r.id} ${skillNames[k]}`);inputs[k]=input;label.append(input);skillBox.append(label);}cell(tr,'').append(skillBox);
        cell(tr,'').append(button('暂存此人',()=>stage(Object.entries(inputs).map(([k,input])=>({kind:'crew',id:r.id,skill:k,value:input.value,original:`${r.skills[k]/3} 星`,label:`${r.ship} / ${r.name} / ${skillNames[k]}`})))));
      }
    }
    t.body.append(tr);
  }
  parent.append(t.wrap);if(!data.rows.length)parent.append(el('p','没有匹配项目。可以调整搜索条件或检查游戏资源目录。','empty'));pages(parent,data);
}
async function renderStationMoney(parent){
  const section=el('section',undefined,'station-money');
  section.append(el('h3',`玩家空间站资金 · ${fmt(gameHome.stationCount)} 座`),
                 el('p','每座空间站的账户单独修改。余额为 0 的账户可能在存档中省略 amount，暂存时会补入。','muted'));
  const bar=el('div',undefined,'feature-toolbar');
  const search=el('input');search.id='stationSearch';search.placeholder='搜索空间站名称 / 识别码 / 星区';search.setAttribute('aria-label','搜索空间站');search.dataset.work='';search.value=stationSearch;
  const filter=async()=>{stationSearch=search.value.trim();stationPage=0;await renderFeature();};
  search.onkeydown=work(e=>e.key==='Enter'?filter():null);bar.append(search,button('搜索空间站',filter));
  const data=await job('gameplay',{kind:'station_money',search:stationSearch,sector:stationSector,page:stationPage,gamePath:gamePathValue});
  const sector=el('select');sector.id='stationSector';sector.setAttribute('aria-label','筛选空间站星区');sector.dataset.work='';
  const all=el('option','全部星区');all.value='';sector.append(all);
  for(const item of data.sectors){const option=el('option',item.name);option.value=item.id;sector.append(option);}
  sector.value=stationSector;sector.onchange=work(async()=>{stationSector=sector.value;stationPage=0;await renderFeature();});bar.append(sector);section.append(bar);
  const t=table(['空间站','星区','原余额','目标余额','']);
  for(const row of data.rows){
    const tr=el('tr');cell(tr,`${row.name}${row.code?` · ${row.code}`:''}`).className='named-cell';cell(tr,row.sector.name);cell(tr,`${fmt(row.amount??0)} Cr`);
    const pending=commands.get(`station_money:${row.id}::`);
    const input=numberInput(pending?.value??row.amount??0,0,999999999999999);input.setAttribute('aria-label',`${row.name} 目标余额`);input.disabled=!row.editable;
    cell(tr,'').append(input);
    if(row.editable)cell(tr,'').append(button('暂存',()=>stage([{kind:'station_money',id:row.id,value:input.value,original:row.amount??0,label:`空间站资金：${row.name} · ${row.code||row.id}`}])));
    else cell(tr,row.reason);
    if(pending)tr.classList.add('pending');
    t.body.append(tr);
  }
  section.append(t.wrap,el('p',`匹配 ${fmt(data.total)} 座空间站 · 第 ${data.page+1} 页`,'muted'));
  if(stationPage)section.append(button('上一页',async()=>{stationPage--;await renderFeature();}));
  if((stationPage+1)*100<data.total)section.append(button('下一页',async()=>{stationPage++;await renderFeature();}));
  parent.append(section);
}
function starSelect(value){const s=el('select');s.dataset.work='';for(let i=0;i<=15;i++){const o=el('option',`${Number((i/3).toFixed(2))} 星`);o.value=i;s.append(o);}s.value=String(value);return s;}
async function renderCargo(parent){
  const bar=el('div',undefined,'feature-toolbar');shipPicker(bar);parent.append(bar);
  if(!selectedShip){parent.append(el('p',gameHome.ships.length?'请在上方选择飞船，可先按星区和名称缩小范围。':'没有可用的玩家飞船。'));return;}
  const data=await job('gameplay',{kind:'cargo',ship:selectedShip,gamePath:gamePathValue});
  parent.append(el('p','选择货物并输入目标总数量；0 表示移除。多个修改会合并校验总体积，不能超过货仓容量。','muted'));
  for(const storage of data.storages){
    const box=el('section',undefined,'cargo-box');const used=storage.items.reduce((v,w)=>v+(w.volume??0)*w.amount,0);
    box.append(el('h3',`${storage.types.join(' / ')||'未知类型'} 货仓 · ${fmt(used)} / ${storage.capacity===null?'未知':fmt(storage.capacity)} m³`));
    if(storage.capacity===null||storage.ambiguous){box.append(el('p','无法确认此货仓容量或结构，暂不可修改。请检查游戏目录。','hint'));parent.append(box);continue;}
    const compatible=data.wares.filter(w=>storage.types.includes(w.transport));
    const search=el('input');search.placeholder='筛选可添加货物';search.setAttribute('aria-label','筛选货物');
    const ware=el('select');ware.setAttribute('aria-label','选择货物');ware.dataset.work='';
    const amount=numberInput(1,0,2147483647);amount.setAttribute('aria-label','货物目标数量');
    const fill=()=>{ware.replaceChildren();for(const w of compatible.filter(w=>(w.name+' '+w.id).toLowerCase().includes(search.value.toLowerCase()))){const o=el('option',`${w.name} [${w.id}] · ${w.volume} m³`);o.value=w.id;ware.append(o);}};search.oninput=fill;fill();
    const add=el('div',undefined,'feature-toolbar');add.append(search,ware,amount,button('暂存货物',()=>{if(!ware.value)throw new Error('请选择货物');return stage([{kind:'cargo',id:ware.value,ship:Number(selectedShip),storage:storage.id,value:amount.value,label:`货仓：${compatible.find(w=>w.id===ware.value)?.name||ware.value}`,original:storage.items.find(w=>w.id===ware.value)?.amount??0}]);},'primary'));box.append(add);
    const items=new Map(storage.items.map(w=>[w.id,{...w}]));
    for(const c of commands.values())if(c.kind==='cargo'&&c.storage===storage.id){const w=compatible.find(w=>w.id===c.id);items.set(c.id,{...items.get(c.id),id:c.id,name:w?.name||c.id,amount:c.value,pending:true});}
    const t=table(['货物','数量','操作']);for(const w of items.values()){
      const tr=el('tr');cell(tr,`${w.name} [${w.id}]${w.pending?' · 待修改':''}`);const input=numberInput(w.amount);input.setAttribute('aria-label',`${w.id} 数量`);cell(tr,'').append(input);cell(tr,'').append(button('暂存',()=>stage([{kind:'cargo',id:w.id,ship:Number(selectedShip),storage:storage.id,value:input.value,label:`货仓：${w.name}`,original:storage.items.find(v=>v.id===w.id)?.amount??0}])));t.body.append(tr);
    }box.append(t.wrap);if(!items.size)box.append(el('p','货仓为空，可在上方添加货物。','muted'));parent.append(box);
  }
  if(!data.storages.length)parent.append(el('p','未找到这艘船的货物仓储组件。弹药和个人背包不属于货仓。','hint'));
}
document.querySelectorAll('[data-tab]').forEach(b=>{b.dataset.work='';b.onclick=work(async()=>{feature=b.dataset.tab;featurePage=0;featureSearch='';await renderFeature();});});
$('gameSettings').onclick=()=>$('gameSettingsDialog').showModal();
$('loadGameData').onclick=work(async()=>{gamePathValue=$('gamePath').value.trim().replace(/^"|"$/g,'');try{localStorage.setItem('x4-game-path',gamePathValue);}catch{}$('gameSettingsDialog').close();if(revision)await loadGameplay();});
showMode();
