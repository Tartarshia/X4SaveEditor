'use strict';
const commands = new Map();
const drafts = new Map();
let gameHome=null, feature='money', featurePage=0, featureSearch='', selectedShip='', blueprintOwnership='missing';
let selectedSector='', shipSearch='';
let includeInternalFactions=false;
let stationSearch='', stationSector='', stationPage=0;
let resourceStation='';
let inventoryHolder='';
let inventoryGroup='other';
let blueprintGroup='';
let diplomacySource='', diplomacyTarget='';
let gamePathValue='';
try { gamePathValue=localStorage.getItem('x4-game-path')||''; } catch {}
const titles={money:'玩家金钱',station_resources:'空间站资源',hq:'总部 / 科研',ship_mods:'已安装飞船改装',relations:'势力关系',diplomacy:'外交与特工',cargo:'飞船货仓',inventory:'特殊物品',blueprints:'解锁蓝图',crew:'船员技能',ammunition:'弹药与部署物',ship_service:'飞船维护与换装',crew_roster:'船员数量与岗位',map:'星区地图',encyclopedia:'百科解锁'};
const skillNames={all:'全部五项技能',piloting:'驾驶',management:'管理',engineering:'工程',boarding:'登舰',morale:'士气'};
titles.assets='资产详情';
const groups={ships:'舰船',engines:'引擎',shields:'护盾',weapons:'武器',turrets:'炮塔',missiles:'导弹',drones:'无人机',countermeasures:'干扰弹',deployables:'部署物',modules:'空间站模块'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,fn,cls=''){const b=el('button',text,cls);b.dataset.work='';b.onclick=work(fn);return b;}
function numberInput(value,min=0,max=''){const n=el('input');n.type='number';n.min=min;n.max=max;n.step='1';n.value=value;n.dataset.work='';return n;}
function commandKey(c){return [c.kind,c.id||'',c.storage||'',c.skill||''].join(':');}
function currentValue(c){const key=commandKey(c), all=c.kind==='crew'?`crew:${c.id}::all`:'';return drafts.get(key)?.value??drafts.get(all)?.value??commands.get(key)?.value??commands.get(all)?.value??c.original;}
function updateDraftCount(){const count=drafts.size+advancedDrafts.size;const button=$('stageAll');button.textContent=count?`暂存修改 (${count})`:'暂存修改';button.dataset.unavailable=count?'false':'true';button.disabled=!count||busy;}
function queueDraft(c){
  const key=commandKey(c), all=c.kind==='crew'&&c.skill!=='all'?`crew:${c.id}::all`:'';
  const baseline=drafts.get(all)?.value??commands.get(key)?.value??commands.get(all)?.value??c.original;
  if(!['blueprint','mod_config'].includes(c.kind)&&String(c.value)===String(baseline))drafts.delete(key);
  else drafts.set(key,c);
  updateDraftCount();
}
function bindDraft(input,make){input.xmlCommand=()=>make(input.value);input.addEventListener(input.tagName==='SELECT'?'change':'input',()=>queueDraft(make(input.value)));return input;}
let sourceContext=null;
function xmlButton(command){return button('查看原始 XML',()=>openOriginal(typeof command==='function'?command():command),'xml-link');}
function attachSourceButtons(parent){for(const input of parent.querySelectorAll('input,select'))if(input.xmlCommand)input.after(xmlButton(input.xmlCommand));}
async function openOriginal(command){
  const data=await job('gameplay',{kind:'source_nodes',command,gamePath:gamePathValue});
  const origin=feature==='advanced'?(sourceContext?.origin||'money'):feature;
  sourceContext={origin,label:command.label||titles[command.kind]||command.kind,nodes:data.nodes};
  if($('reviewDialog').open)$('reviewDialog').close();
  await openOriginalNode(data.nodes[0].id);
}
async function openOriginalNode(node){
  feature='advanced';showMode();await navigate('node',node);
  if(rows.length)await selectRow(rows[0]);
}
function renderSourceContext(){
  const section=$('sourceContext');section.replaceChildren();section.hidden=feature!=='advanced'||!sourceContext;
  if(section.hidden)return;
  section.append(el('strong',sourceContext.label),el('p','显示加载时的原始 XML。新增记录定位到原有父节点，暂存修改尚未写入这里。','muted'));
  const links=el('div',undefined,'feature-toolbar');
  for(const node of sourceContext.nodes)links.append(button(node.label,()=>openOriginalNode(node.id)));
  links.append(button('返回功能页面',async()=>{feature=sourceContext.origin;await renderFeature();}));section.append(links);
}
async function stagePending(){
  if(!drafts.size&&!advancedDrafts.size)throw new Error('没有尚未暂存的修改');
  await stage([...drafts.values()]);drafts.clear();advancedDrafts.clear();updateDraftCount();
  if(feature==='advanced')renderAttributes();else await renderFeature();
}
function advancedChanges(source=changes){const result={};for(const c of source.values())(result[c.node]??={})[c.key]=c.value;return result;}
async function stage(list){
  if(!list.length&&!advancedDrafts.size)throw new Error('请先修改内容');
  const next=new Map(commands);for(const c of list){
    if(c.kind==='mod_config')for(const [k,v] of next)if(v.kind==='mod_value'&&String(v.id)===String(c.id))next.delete(k);
    if(c.kind==='crew'&&c.skill==='all')for(const [k,v] of next)if(v.kind==='crew'&&v.id===c.id)next.delete(k);
    next.delete(commandKey(c));next.set(commandKey(c),c);
  }
  const nextChanges=new Map(changes);for(const [key,edit] of advancedDrafts){if(edit.value===edit.original)nextChanges.delete(key);else nextChanges.set(key,edit);}
  const preview=await job('plan',{commands:[...next.values()],changes:advancedChanges(nextChanges),gamePath:gamePathValue});
  changes.clear();for(const [key,edit] of nextChanges)changes.set(key,edit);
  commands.clear();for(const [key,c] of next)commands.set(key,c);updateCount();
  $('status').textContent=`已暂存 ${changes.size+commands.size} 项修改；导出时写入 ${preview.patches} 处。`;
}
function appendCommandReview(body){
  for(const [key,c] of commands){
    const tr=el('tr');cell(tr,c.label||titles[c.kind]||c.kind);
    cell(tr,c.displayOriginal??(c.kind==='research'?(Number(c.original)?'已完成':'未完成'):c.kind==='licence'?(Number(c.original)?'持有':'未持有'):c.original??'新增'));
    cell(tr,c.displayValue??(c.kind==='blueprint'?'解锁':c.kind==='crew'?`${Number(c.value)/3} 星`:c.kind==='research'?(Number(c.value)?'完成（含前置）':'取消完成（含后续）'):c.kind==='licence'?(Number(c.value)?'授予（含前置）':'撤销（含依赖）'):c.value));
    cell(tr,'').append(xmlButton(c),button('撤销',async()=>{commands.delete(key);updateCount();tr.remove();await renderFeature();}));body.append(tr);
  }
}
function showMode(){
  const advanced=feature==='advanced';
  $('gameplay').hidden=advanced;$('workspace').hidden=!advanced;$('shortcutSection').hidden=!advanced;document.querySelector('.search').hidden=!advanced;
  document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===feature));
  if(!advanced)$('featureTitle').textContent=titles[feature];
  renderSourceContext();
}
async function loadGameplay(){
  licenceFaction='';
  gameHome=await job('gameplay',{kind:'home',gamePath:gamePathValue});
  if(selectedSector&&!gameHome.sectors.some(s=>s.id===selectedSector))selectedSector='';
  if(selectedShip&&!gameHome.ships.some(s=>String(s.id)===String(selectedShip)&&(!selectedSector||s.sector.id===selectedSector)))selectedShip='';
  if(!selectedShip&&!selectedSector)selectedShip=gameHome.current||'';
  $('gameWarnings').hidden=!gameHome.warnings.length;$('gameWarningText').textContent=gameHome.warnings.join('\n');
  $('gamePath').value=gamePathValue||gameHome.gamePath;
  await renderFeature();
}
function table(headers){const wrap=el('div',undefined,'feature-table');const t=el('table');const head=el('thead');const tr=el('tr');for(const h of headers)tr.append(el('th',h));head.append(tr);const body=el('tbody');t.append(head,body);wrap.append(t);return {wrap,body};}
function shipLabel(ship){return `${ship.name} · ${ship.code} · ${ship.type}${ship.model!==ship.name?` · ${ship.model}`:''}`;}
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
  const search=el('input');search.placeholder='筛选名称 / 识别码 / 船型 / 型号';search.setAttribute('aria-label','筛选飞船');search.dataset.work='';search.value=shipSearch;
  const fill=()=>{
    select.replaceChildren();
    const placeholder=el('option',allowAll?(selectedSector?'此星区全部玩家人员（含空间站）':'全部玩家人员（含空间站和未分配人员）'):'选择一艘玩家飞船');placeholder.value='';select.append(placeholder);
    for(const sector of gameHome.sectors){
      if(selectedSector&&sector.id!==selectedSector)continue;
      const group=el('optgroup');group.label=sector.name;
      for(const ship of gameHome.ships.filter(s=>s.sector.id===sector.id)){
        if(!(`${ship.name} ${ship.code} ${ship.type} ${ship.model}`.toLowerCase().includes(search.value.toLowerCase()))&&String(ship.id)!==String(selectedShip))continue;
        const option=el('option',`${ship.id===gameHome.current?'当前飞船 · ':''}${shipLabel(ship)}`);option.value=ship.id;group.append(option);
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
async function renderFeature(){await renderFeatureContent();if(feature!=='advanced')attachSourceButtons($('featureBody'));}
async function renderFeatureContent(){
  showMode();if(feature==='advanced'||!gameHome)return;
  const parent=$('featureBody');parent.replaceChildren();
  if(feature==='assets'){await renderAssets(parent);return;}
  if(feature==='money'){
    const moneyCommand=value=>({kind:'money',value,original:gameHome.money,label:'玩家金钱（同步共享账户）'});
    const saved=commands.get('money:::');parent.append(el('p','玩家可用资金','muted'),el('div',`${fmt(gameHome.money||0)} Cr`,'money-value'));
    const box=el('div',undefined,'feature-toolbar');const input=bindDraft(numberInput(currentValue(moneyCommand(gameHome.money))??0,0,999999999999999),moneyCommand);input.id='moneyAmount';input.setAttribute('aria-label','玩家金钱');box.append(input);
    parent.append(box);const presets=el('div',undefined,'feature-toolbar');for(const [label,value] of [['100 万',1000000],['1000 万',10000000],['1 亿',100000000],['10 亿',1000000000]])presets.append(button(label,()=>{input.value=value;input.dispatchEvent(new Event('input'));}));parent.append(presets,el('p','统一修改玩家主账户、同 ID 账户和金钱摘要。修改后点击上方“暂存修改”，再导出新存档。','hint'));if(saved)parent.append(el('p',`待导出：${fmt(saved.value)} Cr`,'pending'));
    await renderStationMoney(parent);return;
  }
  if(feature==='cargo'){await renderCargo(parent);return;}
  if(feature==='inventory'){await renderInventory(parent);return;}
  if(feature==='ship_mods'){await renderShipMods(parent);return;}
  if(feature==='ammunition'){await renderAmmunition(parent);return;}
  if(feature==='ship_service'){await renderShipService(parent);return;}
  if(feature==='crew_roster'){await renderCrewRoster(parent);return;}
  if(feature==='map'){await renderGalaxy(parent);return;}
  if(feature==='encyclopedia'){await renderEncyclopedia(parent);return;}
  if(feature==='hq'){await renderHeadquarters(parent);return;}
  if(feature==='station_resources'){await renderStationResources(parent);return;}
  if(feature==='diplomacy'){await renderDiplomacy(parent);return;}
  const bar=searchBar(parent);
  if(feature==='crew')shipPicker(bar,true);
  if(feature==='blueprints'){
    const filter=el('select');filter.id='blueprintOwnership';filter.setAttribute('aria-label','蓝图拥有状态');for(const [v,l] of [['missing','未拥有'],['owned','已有'],['all','全部']]){const o=el('option',l);o.value=v;filter.append(o);}filter.value=blueprintOwnership;filter.onchange=work(async()=>{blueprintOwnership=filter.value;featurePage=0;await renderFeature();});bar.append(filter);
    parent.append(el('p','从本机游戏目录列出未拥有的可制造蓝图。可按名称或 ID 搜索，勾选后批量解锁；不会重复添加已有蓝图。','muted'));
  }
  if(feature==='crew')parent.append(el('p','每 3 点技能 = 1 星。可编辑单人的单项技能，也可勾选本页人员批量设置。不会改变船员岗位。','muted'));
  if(feature==='relations')parent.append(el('p','同步双方基础关系，并将双方对彼此的临时加成归零。被游戏锁定的势力显示为只读；剧情仍可能再次改变关系。','muted'));
  const data=await job('gameplay',{kind:feature,search:featureSearch,page:featurePage,ship:selectedShip,sector:selectedSector,ownership:blueprintOwnership,group:blueprintGroup,includeInternal:includeInternalFactions,gamePath:gamePathValue});
  if(feature==='blueprints'){
    const group=el('select');group.setAttribute('aria-label','蓝图分类');group.dataset.work='';
    const all=el('option','全部分类');all.value='';group.append(all);
    for(const value of data.groups){const option=el('option',groups[value]||value);option.value=value;group.append(option);}
    group.value=blueprintGroup;group.onchange=work(async()=>{blueprintGroup=group.value;featurePage=0;await renderFeature();});bar.append(group);
  }
  if(feature==='relations'){
    const label=el('label');const toggle=el('input');toggle.type='checkbox';toggle.id='includeInternalFactions';toggle.checked=includeInternalFactions;toggle.dataset.work='';
    toggle.onchange=work(async()=>{includeInternalFactions=toggle.checked;featurePage=0;await renderFeature();});
    label.append(toggle,document.createTextNode(` 显示 visitor 内部势力（${data.internalCount}）`));bar.append(label);
  }
  const selected=new Set();
  const bulk=el('div',undefined,'feature-toolbar');
  if(feature!=='relations'){
    const all=el('input');all.type='checkbox';all.id='selectFeaturePage';all.setAttribute('aria-label','选择本页');all.onchange=()=>{for(const box of parent.querySelectorAll('[data-pick]')){box.checked=all.checked;box.onchange();}};bulk.append(all,el('label','选择本页'));
    if(feature==='blueprints')bulk.append(el('span','勾选即加入草稿，点击上方“暂存修改”统一校验。','muted'));
    else {
      const skill=el('select');skill.id='bulkSkill';skill.setAttribute('aria-label','批量技能');for(const [v,l] of Object.entries(skillNames)){const o=el('option',l);o.value=v;skill.append(o);}const stars=starSelect(15);stars.id='bulkStars';
      bulk.append(skill,stars,button('设置所选船员',async()=>{
        const rows=data.rows.filter(r=>selected.has(r.id));if(!rows.length)throw new Error('请先选择船员');
        for(const r of rows)queueDraft({kind:'crew',id:r.id,skill:skill.value,value:stars.value,label:`${r.ship} / ${r.name} / ${skillNames[skill.value]}`,original:skill.value==='all'?'多项':r.skills[skill.value]});
        await renderFeature();
      }));
    }
    parent.append(bulk);
  }
  const t=table(feature==='relations'?['势力','玩家 → 势力','势力 → 玩家','设为']:feature==='blueprints'?['选择','蓝图名称 / ID','分类','状态']:['选择','船员 / 岗位','星区','所属资产','技能（星级）']);
  for(const r of data.rows){
    const tr=el('tr');
    if(feature==='relations'){
      cell(tr,`${r.name} [${r.id}]`);cell(tr,r.outgoing.toFixed(6));cell(tr,r.incoming.toFixed(6));
      const relationCommand=value=>({kind:'relation',id:r.id,value,original:`${r.outgoing} / ${r.incoming}`,label:`势力关系：${r.name}`});
      const select=el('select');select.setAttribute('aria-label',`${r.id} 关系`);const placeholder=el('option','选择目标关系');placeholder.value='';select.append(placeholder);for(const [value,label] of [[-1,'完全敌对 (-1)'],[-0.1,'敌对 (-0.1)'],[0,'中立 (0)'],[0.01,'友好 (0.01)'],[0.1,'盟友 (0.1)'],[1,'最高关系 (1)']]){const o=el('option',label);o.value=value;select.append(o);}select.value=String(drafts.get(commandKey(relationCommand('')))?.value??commands.get(commandKey(relationCommand('')))?.value??'');select.disabled=r.locked;
      select.onchange=()=>{if(select.value)queueDraft(relationCommand(select.value));else{drafts.delete(commandKey(relationCommand('')));updateDraftCount();}};cell(tr,'').append(select);
      select.xmlCommand=()=>relationCommand(select.value);
      if(r.locked)cell(tr,'游戏锁定');
    }else{
      const pick=el('input');pick.type='checkbox';pick.setAttribute('aria-label',`选择 ${r.name}`);pick.dataset.pick=r.id;
      if(feature==='blueprints' && (r.owned||commands.has(`blueprint:${r.id}::`)))pick.disabled=true;
      if(!pick.disabled)pick.onchange=()=>{if(pick.checked)selected.add(r.id);else selected.delete(r.id);if(feature==='blueprints'){const c={kind:'blueprint',id:r.id,label:`蓝图：${r.name} [${r.id}]`};if(pick.checked)queueDraft(c);else{drafts.delete(commandKey(c));updateDraftCount();}}};else pick.removeAttribute('data-pick');
      if(feature==='blueprints'&&drafts.has(`blueprint:${r.id}::`)){pick.checked=true;selected.add(r.id);}
      cell(tr,'').append(pick);
      if(feature==='blueprints')pick.xmlCommand=()=>({kind:'blueprint',id:r.id,label:`蓝图：${r.name} [${r.id}]`});
      if(feature==='blueprints'){
        cell(tr,`${r.name}\n${r.id}`).className='named-cell';cell(tr,groups[r.group]||r.group);
        const status=cell(tr,r.owned?'已拥有':commands.has(`blueprint:${r.id}::`)?'待解锁':'未拥有');
        if(r.owned){const c={kind:'blueprint_remove',id:r.id,value:0,original:1,label:`撤销蓝图：${r.name} [${r.id}]`,displayOriginal:'已拥有',displayValue:'撤销'};
          status.append(button('撤销此蓝图',async()=>{queueDraft(c);await renderFeature();}));
          if(drafts.has(commandKey(c))||commands.has(commandKey(c)))status.append(el('small',' 待撤销'));}
      }
      else{
        cell(tr,`${r.name}\n${r.role} · #${r.id}`).className='named-cell';cell(tr,r.sector.name);cell(tr,r.ship);
        const skillBox=el('div',undefined,'crew-skills');const inputs={};
        for(const k of Object.keys(r.skills)){const label=el('label',skillNames[k]);const make=value=>({kind:'crew',id:r.id,skill:k,value,original:r.skills[k],label:`${r.ship} / ${r.name} / ${skillNames[k]}`});const input=bindDraft(starSelect(currentValue(make(r.skills[k]))),make);input.setAttribute('aria-label',`${r.id} ${skillNames[k]}`);inputs[k]=input;label.append(input);skillBox.append(label);}cell(tr,'').append(skillBox);
      }
    }
    t.body.append(tr);
  }
  parent.append(t.wrap);if(!data.rows.length)parent.append(el('p','没有匹配项目。可以调整搜索条件或检查游戏资源目录。','empty'));pages(parent,data);
  if(feature==='relations')await renderLicences(parent);
}
async function renderDiplomacy(parent){
  const data=await job('gameplay',{kind:'diplomacy',source:diplomacySource,target:diplomacyTarget,gamePath:gamePathValue});
  const card=(title,description)=>{const section=el('section',undefined,'diplomacy-card');section.append(el('h3',title),el('p',description,'muted'));parent.append(section);return section;};
  const influence=card('外交影响力',`玩家当前可用的外交影响力。最高显示档位从 33 开始；游戏余额的绝对上限未确认。编辑器允许写入 0–${data.influenceEditMax}，这是保守限制。`);
  if(data.available){
    const make=value=>({kind:'influence',value,original:data.influence,label:'外交影响力'});
    const input=bindDraft(numberInput(currentValue(make(data.influence)),0,data.influenceEditMax),make);
    input.setAttribute('aria-label','外交影响力目标值');
    influence.append(el('p',`当前：${fmt(data.influence)}`,'diplomacy-current'),input);
  }else influence.append(el('p','此存档没有玩家外交记录，暂不能修改影响力或特工。','hint'));

  const section=card('势力之间的关系','选择两个非玩家势力，设置双方的基础关系值。此操作会把这对势力现有的临时关系加成归零。');
  const pair=data.pair;
  if(pair){diplomacySource=pair.source;diplomacyTarget=pair.target;}
  const bar=el('div',undefined,'feature-toolbar');
  const picker=(label,value)=>{
    const select=el('select');select.setAttribute('aria-label',label);select.dataset.work='';
    for(const faction of data.factions){const option=el('option',`${faction.name} [${faction.id}]${faction.locked?' · 关系锁定':''}${faction.notSelectable?' · 不参与外交':''}`);option.value=faction.id;select.append(option);}
    select.value=value||'';return select;
  };
  const source=picker('势力 A',diplomacySource),target=picker('势力 B',diplomacyTarget);
  source.onchange=work(async()=>{diplomacySource=source.value;diplomacyTarget=target.value;await renderFeature();});
  target.onchange=work(async()=>{diplomacySource=source.value;diplomacyTarget=target.value;await renderFeature();});
  bar.append(source,el('span','↔'),target);section.append(bar);
  if(pair){
    const show=side=>`${side.base===null?'存档未单独保存（游戏默认）':side.base.toFixed(6)}${side.temporary?`；临时加成 ${side.temporary.toFixed(6)}`:''}`;
    section.append(el('p',`${pair.source} → ${pair.target}：${show(pair.forward)}`,'diplomacy-current'),el('p',`${pair.target} → ${pair.source}：${show(pair.reverse)}`,'diplomacy-current'));
    const ids=[pair.source,pair.target].sort();
    const first=data.factions.find(f=>f.id===ids[0]),second=data.factions.find(f=>f.id===ids[1]);
    const make=value=>({kind:'npc_relation',id:ids[0],storage:ids[1],value,
      original:`${pair.forward.base??'默认'} / ${pair.reverse.base??'默认'}`,label:`势力关系：${first.name} ↔ ${second.name}`});
    const key=commandKey(make(''));
    const input=numberInput(drafts.get(key)?.value??commands.get(key)?.value??'',-1,1);input.step='0.01';
    input.xmlCommand=()=>make(input.value);
    input.placeholder='输入 -1 至 1';input.setAttribute('aria-label','势力间目标关系');input.disabled=!pair.editable;
    input.oninput=()=>{if(input.value===''){drafts.delete(key);updateDraftCount();}else queueDraft(make(input.value));};
    const control=el('label','目标基础关系（双方）');control.append(input);section.append(control);
    if(!pair.editable)section.append(el('p','这对势力的关系被游戏锁定或存档记录不唯一，只读。','hint'));
    else section.append(el('p','剧情和动态外交事件仍可能在游戏中重新调整关系。','muted'));
  }else section.append(el('p','没有足够的可见势力。','empty'));

  const agents=card(`特工 · ${data.agents.length} 人`,`谈判与谍报是两套独立经验。每项到 200 经验即为最高的 5 级，游戏内经验仍可继续累计；编辑器写入上限为每项 ${data.experienceEditMax}。选择等级会把经验设为该等级的最低值。`);
  if(!data.available)return;
  if(!data.agents.length){agents.append(el('p','当前没有登记特工。','empty'));return;}
  const t=table(['特工 / 势力','谈判经验与等级','谍报经验与等级']);
  for(const agent of data.agents){
    const tr=el('tr');cell(tr,`${agent.name}\n${agent.faction} · #${agent.id}`).className='named-cell';
    for(const [skill,label] of [['negotiation','谈判'],['espionage','谍报']]){
      const box=el('div',undefined,'agent-exp');
      const make=value=>({kind:'agent_exp',id:agent.id,storage:skill,value,original:agent.experience[skill],label:`${agent.name} / ${label}经验`});
      const xp=bindDraft(numberInput(currentValue(make(agent.experience[skill])),0,data.experienceEditMax),make);
      xp.setAttribute('aria-label',`${agent.id} ${label}经验`);xp.disabled=!agent.editable;
      const level=el('select');level.setAttribute('aria-label',`${agent.id} ${label}等级`);level.disabled=!agent.editable;
      for(let n=0;n<data.levelMinimums.length;n++){const option=el('option',`${n} 级（${data.levelMinimums[n]} 经验起）`);option.value=n;level.append(option);}
      const sync=()=>{const value=Number(xp.value);level.value=String(data.levelMinimums.reduce((result,minimum,i)=>value>=minimum?i:result,0));};
      xp.addEventListener('input',sync);level.onchange=()=>{xp.value=String(data.levelMinimums[Number(level.value)]);xp.dispatchEvent(new Event('input'));};sync();
      box.append(xp,level);cell(tr,'').append(box);
    }
    if(!agent.editable){tr.title=agent.reason;tr.classList.add('readonly');}
    t.body.append(tr);
  }
  agents.append(t.wrap);
}
async function renderStationMoney(parent,asset=''){
  const section=el('section',undefined,'station-money');
  section.append(el('h3',asset?'资产资金':`玩家空间站资金 · ${fmt(gameHome.stationCount)} 座`),
                 el('p','空间站账户和建造仓储账户分别修改。余额为 0 的账户可能在存档中省略 amount，暂存时会补入。','muted'),
                 el('p','预算栏显示存档账户的 min / max 区间；“未保存”表示存档没有这两个值，游戏内建议预算可能会动态计算。','muted'));
  const bar=el('div',undefined,'feature-toolbar');
  const search=el('input');search.id='stationSearch';search.placeholder='搜索空间站名称 / 识别码 / 星区';search.setAttribute('aria-label','搜索空间站');search.dataset.work='';search.value=stationSearch;
  const filter=async()=>{stationSearch=search.value.trim();stationPage=0;await renderFeature();};
  search.onkeydown=work(e=>e.key==='Enter'?filter():null);bar.append(search,button('搜索空间站',filter));
  const data=await job('gameplay',{kind:'station_money',station:asset,search:asset?'':stationSearch,sector:asset?'':stationSector,page:asset?0:stationPage,gamePath:gamePathValue});
  const sector=el('select');sector.id='stationSector';sector.setAttribute('aria-label','筛选空间站星区');sector.dataset.work='';
  const all=el('option','全部星区');all.value='';sector.append(all);
  for(const item of data.sectors){const option=el('option',item.name);option.value=item.id;sector.append(option);}
  sector.value=stationSector;sector.onchange=work(async()=>{stationSector=sector.value;stationPage=0;await renderFeature();});bar.append(sector);if(!asset)section.append(bar);
  const budget=account=>account.min===null&&account.max===null?'未保存':`${account.min===null?'—':fmt(account.min)} / ${account.max===null?'—':fmt(account.max)} Cr`;
  const t=table(['空间站','星区','空间站资金','建造资金','存档预算区间（站 / 建造）']);
  for(const row of data.rows){
    const tr=el('tr');cell(tr,`${row.name}${row.code?` · ${row.code}`:''}`).className='named-cell';cell(tr,row.sector.name);
    const stationCommand=value=>({kind:'station_money',id:row.id,value,original:row.amount??0,label:`空间站资金：${row.name} · ${row.code||row.id}`});
    const pending=commands.get(`station_money:${row.id}::`);
    const stationCell=cell(tr,'');stationCell.append(el('span',`${fmt(row.amount??0)} Cr`));
    const input=bindDraft(numberInput(currentValue(stationCommand(row.amount??0)),0,999999999999999),stationCommand);input.setAttribute('aria-label',`${row.name} 空间站资金目标余额`);input.disabled=!row.editable;
    const stationControls=el('div',undefined,'account-controls');stationControls.append(input);
    if(!row.editable)stationControls.append(el('small',row.reason));
    stationCell.append(stationControls);
    const build=row.construction;const buildCommand=value=>({kind:'construction_money',id:row.id,value,original:build.amount??0,label:`建造资金：${row.name} · ${row.code||row.id}`});const buildCell=cell(tr,'');buildCell.append(el('span',build.amount===null?'未找到':`${fmt(build.amount)} Cr`));
    const buildPending=commands.get(`construction_money:${row.id}::`);
    if(build.node){
      const buildInput=bindDraft(numberInput(currentValue(buildCommand(build.amount??0)),0,999999999999999),buildCommand);buildInput.setAttribute('aria-label',`${row.name} 建造资金目标余额`);buildInput.disabled=!build.editable;
      const buildControls=el('div',undefined,'account-controls');buildControls.append(buildInput);
      if(!build.editable)buildControls.append(el('small',build.reason));
      buildCell.append(buildControls);
    }else buildCell.append(el('small',build.reason));
    cell(tr,`站：${budget(row)}\n建造：${budget(build)}`).className='named-cell';
    if(pending||buildPending)tr.classList.add('pending');
    t.body.append(tr);
  }
  section.append(t.wrap,el('p',`匹配 ${fmt(data.total)} 座空间站 · 第 ${data.page+1} 页`,'muted'));
  if(!asset&&stationPage)section.append(button('上一页',async()=>{stationPage--;await renderFeature();}));
  if(!asset&&(stationPage+1)*100<data.total)section.append(button('下一页',async()=>{stationPage++;await renderFeature();}));
  parent.append(section);
}
async function renderStationResources(parent,embedded=false){
  const data=await job('gameplay',{kind:'station_resources',station:resourceStation,gamePath:gamePathValue});
  resourceStation=String(data.station);
  const current=data.stations.find(s=>String(s.id)===resourceStation);
  const pickerBar=el('div',undefined,'feature-toolbar');
  const search=el('input');search.placeholder='搜索空间站名称 / 识别码';search.setAttribute('aria-label','搜索空间站');
  const sector=el('select');sector.setAttribute('aria-label','筛选空间站星区');sector.dataset.work='';
  const all=el('option','全部星区');all.value='';sector.append(all);
  const sectors=[...new Map(data.stations.map(s=>[s.sector.id,s.sector])).values()].sort((a,b)=>a.name.localeCompare(b.name));
  for(const s of sectors){const option=el('option',s.name);option.value=s.id;sector.append(option);}
  const picker=el('select');picker.setAttribute('aria-label','选择空间站');picker.dataset.work='';
  const fill=()=>{
    picker.replaceChildren();const groups=new Map();const query=search.value.trim().toLowerCase();
    for(const s of data.stations){
      if(String(s.id)!==resourceStation && ((sector.value&&sector.value!==s.sector.id)||!(s.name+' '+s.code).toLowerCase().includes(query)))continue;
      if(!groups.has(s.sector.id)){const group=el('optgroup');group.label=s.sector.name;groups.set(s.sector.id,group);picker.append(group);}
      const option=el('option',`${s.name}${s.code?' · '+s.code:''}`);option.value=s.id;groups.get(s.sector.id).append(option);
    }
    picker.value=resourceStation;
  };
  search.oninput=fill;sector.onchange=fill;picker.onchange=work(async()=>{resourceStation=picker.value;await renderFeature();});fill();
  pickerBar.append(search,sector,picker);if(!embedded)parent.append(pickerBar);
  if(!current){parent.append(el('p','没有玩家空间站。','empty'));return;}
  parent.append(el('p',`${current.name}${current.code?' · '+current.code:''}　|　${current.sector.name}`,'resource-station-title'),
                el('p','按物资汇总空间站实体货仓；建造仓储独立列出。修改的是库存总量，暂存时按货仓类型、单件体积和剩余容量分配到实体货仓。经理的自动配额、交易订单和生产逻辑不会随库存一同修改。','muted'));
  if(!embedded)renderWorkforce(parent,data,current);
  const renderGroup=(title,kind,storages,listed,indicators,reason='')=>{
    const section=el('section',undefined,'resource-group');
    section.append(el('h3',`${title} · ${storages.length} 个货仓 · ${listed.length} 种现有物资`));
    if(reason)section.append(el('p',reason,'hint'));
    const editable=storages.length>0&&storages.every(s=>s.capacity!==null&&!s.ambiguous);
    if(!editable&&storages.length)section.append(el('p','部分货仓的容量或结构无法确认，此组库存暂时只读。','hint'));
    if(storages.length){
      const details=el('details',undefined,'resource-storage-details');details.append(el('summary','查看实体货仓与容量'));
      const tableData=table(['货仓','类型','已用 / 总容量']);
      for(const s of storages){const tr=el('tr');cell(tr,`${s.name}\n${s.macro}`).className='named-cell';cell(tr,s.types.join(' / ')||'未知');cell(tr,`${s.used===null?'未知':fmt(s.used)} / ${s.capacity===null?'未知':fmt(s.capacity)} m³`);tableData.body.append(tr);}
      details.append(tableData.wrap);section.append(details);
    }
    const rows=new Map(listed.map(w=>[w.id,{...w}]));
    for(const c of [...commands.values(),...drafts.values()])if(c.kind===kind&&String(c.id)===resourceStation&&!rows.has(c.storage)){
      const ware=data.wares.find(w=>w.id===c.storage);rows.set(c.storage,{id:c.storage,name:ware?.name||c.storage,amount:0,volume:ware?.volume,transport:ware?.transport,locations:0});
    }
    const filter=el('input');filter.placeholder='筛选物资名称 / ID';filter.setAttribute('aria-label',`${title}筛选物资`);section.append(filter);
    const t=table(['物资 / ID','当前总量','目标总量','单件体积','分布货仓']);
    for(const w of [...rows.values()].sort((a,b)=>a.name.localeCompare(b.name)||a.id.localeCompare(b.id))){
      const tr=el('tr');cell(tr,`${w.name}\n${w.id}${w.editable===false?' · 非库存物资，只读':''}`).className='named-cell';cell(tr,fmt(w.amount));
      const make=value=>({kind,id:data.station,storage:w.id,value,original:w.amount,label:`${current.name} / ${title} / ${w.name} [${w.id}]`});
      const input=bindDraft(numberInput(currentValue(make(w.amount)),0,2147483647),make);input.setAttribute('aria-label',`${title} ${w.id} 目标总量`);input.disabled=!editable||w.editable===false;cell(tr,'').append(input);
      cell(tr,w.volume===undefined?'未知':`${fmt(w.volume)} m³`);cell(tr,fmt(w.locations));
      if(commands.has(commandKey(make(w.amount)))||drafts.has(commandKey(make(w.amount))))tr.classList.add('pending');
      t.body.append(tr);
    }
    filter.oninput=()=>{const q=filter.value.trim().toLowerCase();for(const tr of t.body.rows)tr.hidden=!tr.cells[0].textContent.toLowerCase().includes(q);};
    section.append(t.wrap);
    if(!rows.size)section.append(el('p','当前没有存储物资。','muted'));
    if(indicators.length){
      const details=el('details',undefined,'resource-storage-details');details.append(el('summary',`查看交易预留与存档缺口 · ${indicators.length} 条`));
      details.append(el('p','这些是单独的状态记录，不计入上方实体货仓库存。','muted'));
      const t=table(['记录类型','物资 / ID','数量']);for(const item of indicators){const tr=el('tr');cell(tr,item.kind);cell(tr,`${item.name}\n${item.id}`).className='named-cell';cell(tr,fmt(item.amount));t.body.append(tr);}details.append(t.wrap);section.append(details);
    }
    if(editable){
      const types=new Set(storages.flatMap(s=>s.types));const compatible=data.wares.filter(w=>types.has(w.transport));
      const add=el('div',undefined,'feature-toolbar');const wareSearch=el('input');wareSearch.placeholder='搜索可加入物资';wareSearch.setAttribute('aria-label',`${title}搜索可加入物资`);
      const ware=el('select');ware.setAttribute('aria-label',`${title}选择物资`);ware.dataset.work='';
      const fillWares=()=>{ware.replaceChildren();for(const w of compatible.filter(w=>(w.name+' '+w.id).toLowerCase().includes(wareSearch.value.toLowerCase()))){const option=el('option',`${w.name} [${w.id}]`);option.value=w.id;ware.append(option);}};
      wareSearch.oninput=fillWares;fillWares();const amount=numberInput(1,0,2147483647);amount.setAttribute('aria-label',`${title}新增目标总量`);
      add.append(wareSearch,ware,amount,button('加入待修改物资',async()=>{
        if(!ware.value)throw new Error('请选择物资');const item=rows.get(ware.value),catalog=data.wares.find(w=>w.id===ware.value);
        queueDraft({kind,id:data.station,storage:ware.value,value:amount.value,original:item?.amount??0,
                    label:`${current.name} / ${title} / ${catalog?.name||ware.value} [${ware.value}]`});await renderFeature();
      }));section.append(add);
    }
    parent.append(section);
  };
  renderGroup('空间站库存','station_stock',data.ordinary,data.ordinaryWares,data.ordinaryIndicators);
  renderGroup('建造仓储物资','build_stock',data.building,data.buildingWares,data.buildingIndicators,data.constructionReason);
  const production=el('section',undefined,'resource-group');production.append(el('h3',`生产模块 · ${data.production.reduce((sum,p)=>sum+p.count,0)} 个`));
  if(data.production.length){const t=table(['模块名称','数量','macro']);for(const p of data.production){const tr=el('tr');cell(tr,p.name);cell(tr,fmt(p.count));cell(tr,p.macro);t.body.append(tr);}production.append(t.wrap);}
  else production.append(el('p','没有识别到生产模块。','muted'));
  parent.append(production);
  if(!embedded)await renderStationSettings(parent,data.station);
}
function starSelect(value){const s=el('select');s.dataset.work='';for(let i=0;i<=15;i++){const o=el('option',`${Number((i/3).toFixed(2))} 星`);o.value=i;s.append(o);}s.value=String(value);return s;}
async function renderCargo(parent,embedded=false){
  if(!embedded){const bar=el('div',undefined,'feature-toolbar');shipPicker(bar);parent.append(bar);}
  if(!selectedShip){parent.append(el('p',gameHome.ships.length?'请在上方选择飞船，可先按星区和名称缩小范围。':'没有可用的玩家飞船。'));return;}
  const data=await job('gameplay',{kind:'cargo',ship:selectedShip,gamePath:gamePathValue});
  const currentShip=gameHome.ships.find(ship=>String(ship.id)===String(selectedShip));
  if(currentShip)parent.append(el('p',shipLabel(currentShip),'resource-station-title'));
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
    const add=el('div',undefined,'feature-toolbar');add.append(search,ware,amount,button('加入待修改货物',async()=>{if(!ware.value)throw new Error('请选择货物');queueDraft({kind:'cargo',id:ware.value,ship:Number(selectedShip),storage:storage.id,value:amount.value,label:`货仓：${compatible.find(w=>w.id===ware.value)?.name||ware.value}`,original:storage.items.find(w=>w.id===ware.value)?.amount??0});await renderFeature();}));box.append(add);
    const items=new Map(storage.items.map(w=>[w.id,{...w}]));
    for(const c of commands.values())if(c.kind==='cargo'&&c.storage===storage.id){const w=compatible.find(w=>w.id===c.id);items.set(c.id,{...items.get(c.id),id:c.id,name:w?.name||c.id,amount:c.value,pending:true});}
    for(const c of drafts.values())if(c.kind==='cargo'&&c.storage===storage.id){const w=compatible.find(w=>w.id===c.id);items.set(c.id,{...items.get(c.id),id:c.id,name:w?.name||c.id,amount:c.value,pending:true});}
    const t=table(['货物','数量']);for(const w of items.values()){
      const make=value=>({kind:'cargo',id:w.id,ship:Number(selectedShip),storage:storage.id,value,label:`货仓：${w.name}`,original:storage.items.find(v=>v.id===w.id)?.amount??0});
      const tr=el('tr');cell(tr,`${w.name} [${w.id}]${w.pending?' · 待修改':''}`);const input=bindDraft(numberInput(currentValue(make(w.amount))),make);input.setAttribute('aria-label',`${w.id} 数量`);cell(tr,'').append(input);t.body.append(tr);
    }box.append(t.wrap);if(!items.size)box.append(el('p','货仓为空，可在上方添加货物。','muted'));parent.append(box);
  }
  if(!data.storages.length)parent.append(el('p','未找到这艘船的货物仓储组件。弹药和个人背包不属于货仓。','hint'));
}
document.querySelectorAll('[data-tab]').forEach(b=>{b.dataset.work='';b.onclick=work(async()=>{feature=b.dataset.tab;featurePage=0;featureSearch='';await renderFeature();});});
async function renderInventory(parent,asset=''){
  const data=await job('gameplay',{kind:'inventory',holder:inventoryHolder,asset,gamePath:gamePathValue});
  inventoryHolder=String(data.holder);
  parent.append(el('p','管理玩家随身物品、已记录的玩家船员背包，以及存档中有独立 inventory 节点的玩家飞船和空间站。按分类查看物品；“删除”会将该位置的数量设为 0，统一暂存后仍可在修改清单撤销。','muted'));
  const bar=el('div',undefined,'feature-toolbar');
  const holderSearch=el('input');holderSearch.placeholder='筛选持有人 / 飞船 / 星区';holderSearch.setAttribute('aria-label','筛选物品持有人');
  const picker=el('select');picker.setAttribute('aria-label','选择物品持有人');picker.dataset.work='';
  const label=l=>l.type==='player'?l.name:`${l.type==='crew'?'船员':l.type==='station'?'空间站':'飞船'} · ${l.name} · ${l.ship||''} · ${l.sector?.name||''} [${l.id}]`;
  const fillHolders=()=>{picker.replaceChildren();const q=holderSearch.value.trim().toLowerCase();
    const groups=new Map();for(const location of data.locations){const name=label(location);if(String(location.id)!==inventoryHolder&&!name.toLowerCase().includes(q))continue;
      const type=location.type;let group=groups.get(type);if(!group){group=el('optgroup');group.label={player:'玩家',ship:'飞船',station:'空间站',crew:'船员背包'}[type]||type;groups.set(type,group);picker.append(group);}
      const option=el('option',name);option.value=location.id;group.append(option);}
    picker.value=inventoryHolder;};
  holderSearch.oninput=fillHolders;picker.onchange=work(async()=>{inventoryHolder=picker.value;await renderFeature();});fillHolders();bar.append(holderSearch,picker);parent.append(bar);
  const location=data.locations.find(l=>String(l.id)===inventoryHolder);
  parent.append(el('h3',`${location?.name||'玩家'} · ${data.items.length} 种物品`));
  const items=new Map(data.items.map(item=>[item.id,{...item}]));
  for(const c of [...commands.values(),...drafts.values()])if(c.kind==='inventory'&&String(c.storage)===inventoryHolder&&!items.has(c.id)){
    const ware=data.wares.find(w=>w.id===c.id);items.set(c.id,{id:c.id,name:ware?.name||c.id,amount:0,group:ware?.group||'other'});}
  const groups=[['other','其他物品'],['paint','喷漆 Paint MOD'],['mod','改装 MOD / 材料']];
  const tabs=el('div',undefined,'feature-toolbar inventory-groups');
  for(const [group,title] of groups){const count=[...items.values()].filter(item=>item.group===group).length;
    const pick=button(`${title} (${count})`,async()=>{inventoryGroup=group;await renderFeature();},group===inventoryGroup?'active':'');
    pick.setAttribute('aria-pressed',String(group===inventoryGroup));tabs.append(pick);}
  parent.append(tabs);
  const filter=el('input');filter.placeholder='筛选已有物品名称 / ID';filter.setAttribute('aria-label','筛选已有特殊物品');parent.append(filter);
  const t=table(['物品 / ID','当前数量','目标数量','操作']);
  const visibleItems=[...items.values()].filter(item=>item.group===inventoryGroup).sort((a,b)=>a.name.localeCompare(b.name)||a.id.localeCompare(b.id));
  for(const item of visibleItems){
    const tr=el('tr');const make=value=>({kind:'inventory',id:item.id,storage:Number(inventoryHolder),value,original:item.amount,
      label:`${location?.name||'玩家'} / ${item.name} [${item.id}]`});
    cell(tr,`${item.name}\n${item.id}${item.editable===false?' · 剧情或弃用物品，只读':''}`).className='named-cell';cell(tr,fmt(item.amount));
    const input=bindDraft(numberInput(currentValue(make(item.amount)),0,2147483647),make);input.setAttribute('aria-label',`${item.id} 目标数量`);input.disabled=item.editable===false;cell(tr,'').append(input);
    const key=commandKey(make(item.amount)),draft=drafts.get(key),staged=commands.get(key);
    const actions=cell(tr,'');
    if(item.editable!==false&&Number(item.amount)>0){
      if(draft&&Number(draft.value)===0)actions.append(button('取消删除',async()=>{drafts.delete(key);updateDraftCount();await renderFeature();}));
      else if(staged&&Number(staged.value)===0&&!draft){const marked=el('span','已暂存删除 · 可在修改清单撤销','muted');actions.append(marked);}
      else actions.append(button('删除',async()=>{queueDraft(make(0));await renderFeature();},'inventory-delete'));
    }
    if(staged||draft)tr.classList.add('pending');t.body.append(tr);
  }
  filter.oninput=()=>{const q=filter.value.trim().toLowerCase();for(const tr of t.body.rows)tr.hidden=!tr.cells[0].textContent.toLowerCase().includes(q);};
  parent.append(t.wrap);if(!visibleItems.length)parent.append(el('p','这一组目前没有物品，可在下方添加。','muted'));
  const add=el('div',undefined,'feature-toolbar');const search=el('input');search.placeholder='搜索可添加特殊物品';search.setAttribute('aria-label','搜索可添加特殊物品');
  const ware=el('select');ware.setAttribute('aria-label','选择特殊物品');ware.dataset.work='';
  const fillWares=()=>{ware.replaceChildren();const q=search.value.trim().toLowerCase();for(const item of data.wares){
    if(item.group!==inventoryGroup)continue;
    if(!(item.name+' '+item.id).toLowerCase().includes(q))continue;const option=el('option',`${item.name} [${item.id}]`);option.value=item.id;ware.append(option);}};
  search.oninput=fillWares;fillWares();const amount=numberInput(1,0,2147483647);amount.setAttribute('aria-label','特殊物品目标数量');
  add.append(search,ware,amount,button('加入待修改物品',async()=>{if(!ware.value)throw new Error('请选择物品');const item=data.wares.find(w=>w.id===ware.value);
    queueDraft({kind:'inventory',id:ware.value,storage:Number(inventoryHolder),value:amount.value,original:items.get(ware.value)?.amount??0,
      label:`${location?.name||'玩家'} / ${item?.name||ware.value} [${ware.value}]`});await renderFeature();}));parent.append(add);
}
$('stageAll').onclick=work(stagePending);
$('gameSettings').onclick=()=>$('gameSettingsDialog').showModal();
$('loadGameData').onclick=work(async()=>{gamePathValue=$('gamePath').value.trim().replace(/^"|"$/g,'');try{localStorage.setItem('x4-game-path',gamePathValue);}catch{}$('gameSettingsDialog').close();if(revision)await loadGameplay();});
showMode();
updateDraftCount();
