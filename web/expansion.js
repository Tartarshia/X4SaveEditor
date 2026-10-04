'use strict';
let mapSector='',mapPage=0,encyclopediaGroup='',encyclopediaStatus='unknown',encyclopediaSource='';
const ammoNames={missile:'导弹',countermeasure:'干扰弹',deployable:'部署物',unit:'无人机'};
const sectorSourceColors={base:'#2563eb',ego_dlc_split:'#c2410c',ego_dlc_terran:'#7c3aed',ego_dlc_pirate:'#a16207',ego_dlc_boron:'#0e7490',ego_dlc_timelines:'#be185d',ego_dlc_mini_01:'#15803d',ego_dlc_mini_02:'#854d0e',unknown:'#64748b'};
function sectorSource(sector){const source=sector.source||{id:'unknown',name:'来源未确认'};return {...source,color:sectorSourceColors[source.id]||sectorSourceColors.unknown};}
function choice(options,value,label){const select=el('select');select.dataset.work='';select.setAttribute('aria-label',label);for(const [id,name] of options){const option=el('option',name);option.value=id;select.append(option);}select.value=String(value);return select;}
function section(parent,title,note){const node=el('section',undefined,'resource-group');node.append(el('h3',title));if(note)node.append(el('p',note,'muted'));parent.append(node);return node;}
function draftAction(text,c){return button(text,async()=>{queueDraft(c);await renderFeature();});}

let assetSelection='',assetKind='all',assetSector='',assetSearch='',assetListPage=0,assetPane='';
let mapSourceFilter='',mapOwnerFilter='',mapAssetPage=0;
function resetAssetNavigation(){assetSelection='';assetKind='all';assetSector='';assetSearch='';assetListPage=0;assetPane='';mapSourceFilter='';mapOwnerFilter='';mapAssetPage=0;}
async function openAsset(row){
  assetSelection=String(row.id);assetSector=row.sector.id;assetKind='all';assetSearch='';assetListPage=0;assetPane='';featurePage=0;featureSearch='';feature='assets';await renderFeature();
}
async function renderAssets(parent){
  const data=await job('gameplay',{kind:'assets',assetKind,sector:assetSector,search:assetSearch,page:assetListPage,gamePath:gamePathValue});
  const directory=el('details',undefined,'asset-directory');directory.open=!assetSelection;directory.append(el('summary',`选择资产 · 匹配 ${fmt(data.total)} 项`));
  const bar=el('div',undefined,'feature-toolbar');const kind=choice([['all','全部资产'],['ship','飞船'],['station','空间站']],assetKind,'资产分类');
  const sector=choice([['','全部星区'],...data.sectors.map(s=>[s.id,s.name])],assetSector,'资产星区');
  const search=el('input');search.placeholder='名称 / ID / 船型 / 型号';search.setAttribute('aria-label','搜索资产');search.value=assetSearch;
  const filter=async()=>{assetKind=kind.value;assetSector=sector.value;assetSearch=search.value.trim();assetListPage=0;assetSelection='';assetPane='';featurePage=0;await renderFeature();};
  kind.onchange=work(filter);sector.onchange=work(filter);search.onkeydown=work(e=>e.key==='Enter'?filter():null);bar.append(kind,sector,search,button('搜索资产',filter));directory.append(bar);
  const t=table(['名称 / ID / 型号','类别','星区','操作']);for(const row of data.rows){const tr=el('tr');cell(tr,`${row.name} · ${row.code}\n${row.model}`).className='named-cell';cell(tr,row.type);cell(tr,row.sector.name);const pick=button('查看详情',async()=>{assetSelection=String(row.id);assetPane='';featurePage=0;featureSearch='';await renderFeature();});pick.setAttribute('aria-label',`查看资产 ${row.code}`);cell(tr,'').append(pick);t.body.append(tr);}directory.append(t.wrap);
  const page=el('div',undefined,'feature-toolbar');page.append(el('span',`第 ${assetListPage+1} 页 · 每页 100 项`));if(assetListPage)page.append(button('上一页资产',async()=>{assetListPage--;await renderFeature();}));if((assetListPage+1)*100<data.total)page.append(button('下一页资产',async()=>{assetListPage++;await renderFeature();}));directory.append(page);parent.append(directory);
  if(!assetSelection){parent.append(el('p','展开资产列表，选择飞船或空间站。修改草稿会保留，切换资产不会清除。','hint'));return;}
  const asset=await job('gameplay',{kind:'asset_detail',id:assetSelection,gamePath:gamePathValue});
  if(asset.kind==='ship')selectedShip=String(asset.id);else resourceStation=String(asset.id);
  const header=section(parent,`${asset.name} · ${asset.code}`,`${asset.type} · ${asset.model} · ${asset.sector.name} · ${asset.crewCount} 名人员`);header.classList.add('asset-summary');
  header.append(button('更换资产',()=>{directory.open=true;directory.scrollIntoView({block:'start'});}));
  if(asset.sector.id!=='unknown')header.append(button('在地图中查看',async()=>{mapSector=asset.sector.id;mapPage=0;mapAssetPage=0;mapSourceFilter='';mapOwnerFilter='';feature='map';await renderFeature();}));
  const panels=asset.kind==='ship'?[['cargo','货仓'],['ammunition','弹药与部署物'],['mods','改装'],['service','维修与换装'],['crew','船员技能'],['roster','人数与岗位']]:[['funds','账户与建造资金'],['resources','资源与生产'],['workforce','劳动力'],['trade','交易设置'],['crew','经理与人员技能']];
  if(asset.inventoryLocations.length)panels.push(['inventory','特殊物品']);if(asset.headquarters)panels.push(['research','总部科研']);
  if(!panels.some(([id])=>id===assetPane))assetPane=panels[0][0];
  const tabs=el('div',undefined,'feature-toolbar asset-panels');tabs.setAttribute('aria-label','资产管理项目');
  for(const [id,name] of panels){const b=button(name,async()=>{assetPane=id;featurePage=0;featureSearch='';await renderFeature();},assetPane===id?'active':'');b.dataset.assetPanel=id;b.setAttribute('aria-pressed',String(assetPane===id));tabs.append(b);}parent.append(tabs);
  const content=el('div');content.id='assetContent';parent.append(content);
  if(assetPane==='cargo')await renderCargo(content,true);
  else if(assetPane==='ammunition')await renderAmmunition(content,true);
  else if(assetPane==='mods')await renderShipMods(content,true);
  else if(assetPane==='service')await renderShipService(content,true);
  else if(assetPane==='roster')await renderCrewRoster(content,true);
  else if(assetPane==='crew')await renderAssetCrew(content,asset);
  else if(assetPane==='funds')await renderStationMoney(content,asset.id);
  else if(assetPane==='resources')await renderStationResources(content,true);
  else if(assetPane==='workforce'){const data=await job('gameplay',{kind:'station_resources',station:asset.id,gamePath:gamePathValue});renderWorkforce(content,data,asset);}
  else if(assetPane==='trade')await renderStationSettings(content,asset.id);
  else if(assetPane==='inventory'){if(!asset.inventoryLocations.some(l=>String(l.id)===inventoryHolder))inventoryHolder=String(asset.inventoryLocations[0].id);await renderInventory(content,asset.id);}
  else if(assetPane==='research')await renderHeadquarters(content);
}
async function renderAssetCrew(parent,asset){
  searchBar(parent);const data=await job('gameplay',{kind:'crew',ship:asset.id,search:featureSearch,page:featurePage,gamePath:gamePathValue});
  const selected=new Set();const bulk=el('div',undefined,'feature-toolbar');const skill=choice(Object.entries(skillNames),'all','资产人员批量技能');const stars=starSelect(15);stars.setAttribute('aria-label','资产人员批量星级');
  bulk.append(skill,stars,button('设置所选人员',async()=>{if(!selected.size)throw new Error('请先勾选人员');for(const row of data.rows)if(selected.has(row.id))queueDraft({kind:'crew',id:row.id,skill:skill.value,value:stars.value,original:skill.value==='all'?'多项':row.skills[skill.value],label:`${asset.name} / ${row.name} / ${skillNames[skill.value]}`});await renderFeature();}));parent.append(bulk);
  const t=table(['选择','人员 / 岗位','技能（星级）']);for(const row of data.rows){const tr=el('tr');const pick=el('input');pick.type='checkbox';pick.setAttribute('aria-label',`选择 ${row.name}`);pick.onchange=()=>pick.checked?selected.add(row.id):selected.delete(row.id);cell(tr,'').append(pick);cell(tr,`${row.name}\n${row.role} · #${row.id}`).className='named-cell';const box=el('div',undefined,'crew-skills');for(const [key,value] of Object.entries(row.skills)){const label=el('label',skillNames[key]);const make=value=>({kind:'crew',id:row.id,skill:key,value,original:row.skills[key],label:`${asset.name} / ${row.name} / ${skillNames[key]}`});const input=bindDraft(starSelect(currentValue(make(value))),make);input.setAttribute('aria-label',`${row.id} ${skillNames[key]}`);label.append(input);box.append(label);}cell(tr,'').append(box);t.body.append(tr);}parent.append(t.wrap);if(!data.total)parent.append(el('p','此资产没有可编辑的人员。','muted'));pages(parent,data);
}

async function renderAmmunition(parent,embedded=false){
  if(!embedded){const bar=el('div',undefined,'feature-toolbar');shipPicker(bar);parent.append(bar);}if(!selectedShip)return;
  const data=await job('gameplay',{kind:'ammunition',ship:selectedShip,gamePath:gamePathValue});
  parent.append(el('p','编辑舰船尚可用的弹药与部署物；已部署、发射中和不可用记录保留，容量校验计入已识别的占用。0 表示删除。','muted'));
  if(data.reason)parent.append(el('p',data.reason,'hint'));
  const rows=new Map(data.items.map(r=>[r.id,r]));
  for(const c of [...commands.values(),...drafts.values()])if(c.kind==='ammunition'&&String(c.ship)===String(selectedShip)&&!rows.has(c.id)){const spec=data.catalogue.find(r=>r.id===c.id);if(spec)rows.set(c.id,{...spec,amount:0,editable:true});}
  for(const [group,title] of Object.entries(ammoNames)){
    const items=[...rows.values()].filter(r=>r.group===group);const used=items.reduce((sum,r)=>sum+r.amount,0);
    const box=section(parent,`${title} · 可用 ${used} · 其他占用 ${data.reserved[group]} / 容量 ${data.capacity[group]}`);
    const filter=el('input');filter.placeholder='筛选名称 / ID';filter.setAttribute('aria-label',`${title}筛选`);box.append(filter);
    const t=table(['名称 / macro','原数量','目标数量']);
    for(const r of items){const tr=el('tr');cell(tr,`${r.name}\n${r.id}`).className='named-cell';cell(tr,fmt(r.amount));
      const make=value=>({kind:'ammunition',ship:Number(selectedShip),id:r.id,value,original:r.amount,label:`${title} / ${r.name}`});
      const input=bindDraft(numberInput(currentValue(make(r.amount)),0,2147483647),make);input.disabled=!data.editable||!r.editable;input.setAttribute('aria-label',`${r.id} 弹药部署物数量`);cell(tr,'').append(input);t.body.append(tr);}
    filter.oninput=()=>{for(const row of t.body.rows)row.hidden=!row.cells[0].textContent.toLowerCase().includes(filter.value.toLowerCase());};box.append(t.wrap);
    const catalogue=data.catalogue.filter(r=>r.group===group);if(!data.editable||!catalogue.length)continue;
    const add=el('div',undefined,'feature-toolbar');const search=el('input');search.placeholder='筛选可添加项目';const picker=choice(catalogue.map(r=>[r.id,`${r.name} [${r.id}]`]),catalogue[0].id,`${title}可添加项目`);
    search.oninput=()=>{for(const option of picker.options)option.hidden=!option.textContent.toLowerCase().includes(search.value.toLowerCase());const first=[...picker.options].find(o=>!o.hidden);picker.value=first?.value||'';};
    const amount=numberInput(1,0,2147483647);amount.setAttribute('aria-label',`${title}添加数量`);
    amount.xmlCommand=()=>({kind:'ammunition',ship:Number(selectedShip),id:picker.value,value:amount.value});
    add.append(search,picker,amount,button('加入待修改',async()=>{const spec=catalogue.find(r=>r.id===picker.value);if(!spec)throw new Error('请选择项目');queueDraft({kind:'ammunition',ship:Number(selectedShip),id:spec.id,value:amount.value,original:rows.get(spec.id)?.amount||0,label:`${title} / ${spec.name}`});await renderFeature();}));box.append(add);
  }
  for(const r of data.items.filter(r=>!r.group))parent.append(el('p',`未知弹药（保留）：${r.id} · ${r.amount}`,'hint'));
}

async function renderShipService(parent,embedded=false){
  if(!embedded){const bar=el('div',undefined,'feature-toolbar');shipPicker(bar);parent.append(bar);}if(!selectedShip)return;
  const data=await job('gameplay',{kind:'ship_service',ship:selectedShip,page:featurePage,gamePath:gamePathValue});
  const intro=section(parent,'维修与换装','维修按本机游戏定义及现有船体改装计算容量。换装只替换现有装备节点，保留组件 ID 和连接，不创建额外装备。');
  const expLabel=el('label');const experimental=el('input');experimental.type='checkbox';experimental.setAttribute('aria-label','启用实验换装');expLabel.append(experimental,document.createTextNode(' 允许同类别的特殊搭配（跳过连接标签校验）'));intro.append(expLabel,el('p','实验搭配尚未经游戏内验证。请先导出测试副本，检查模型、攻击、护盾及重新存档。','hint'));
  for(const row of data.rows){
    const box=section(parent,`${row.name} · ${row.class}`,`${row.macro} · ${row.connection} · #${row.id}`);
    if(row.maxHull!==null){const make=value=>({kind:'repair',id:row.id,ship:data.ship,value,original:row.hull/row.maxHull*100,label:`${row.name} / 船体比例`,displayOriginal:`${(row.hull/row.maxHull*100).toFixed(2)}%`,displayValue:`${value}%`});
      const input=bindDraft(numberInput(currentValue(make(100)),0.001,100),make);input.step='any';input.disabled=!row.editableHull;input.setAttribute('aria-label',`${row.id} 船体百分比`);
      box.append(el('p',`船体：${fmt(row.hull)} / ${fmt(row.maxHull)}`),input,button('修复至满',async()=>{queueDraft(make(100));await renderFeature();}));}
    if(row.refittable){
      const options=data.catalogue.filter(s=>s.class===row.class);const saved=drafts.get(commandKey({kind:'refit',id:row.id}))||commands.get(commandKey({kind:'refit',id:row.id}));
      const picker=choice([[row.macro,`当前：${row.name}`],...options.filter(s=>s.macro!==row.macro).map(s=>[s.macro,`${s.name} [${s.macro}]`])],saved?.value||row.macro,`${row.id} 更换装备`);
      const make=value=>({kind:'refit',id:row.id,ship:data.ship,value,original:row.macro,experimental:experimental.checked,label:`${row.name} / 更换装备`,displayOriginal:row.name,displayValue:data.catalogue.find(s=>s.macro===value)?.name||value});
      picker.xmlCommand=()=>make(picker.value);box.append(picker,button('加入换装草稿',async()=>{queueDraft(make(picker.value));await renderFeature();}));}
  }
  pages(parent,data);
}

async function renderCrewRoster(parent,embedded=false){
  if(!embedded){const bar=el('div',undefined,'feature-toolbar');shipPicker(bar);parent.append(bar);}if(!selectedShip)return;
  const data=await job('gameplay',{kind:'crew_roster',ship:selectedShip,page:featurePage,gamePath:gamePathValue});
  parent.append(el('p',`船员容量：${data.capacity??'未确认'}；另有 ${data.officers} 名具名人员。可调整普通船员人数和勤务 / 陆战队岗位。具名船长、临时与转移中的人员保持原样。减少人数优先移除技能总分较低的普通船员。`,'muted'));
  const counts=section(parent,'目标人数','新增人员复用本船已存在的人员型号，以新的 seed 和 0 技能创建；不会复制具名人员。');
  for(const role of data.roles){const original=data.counts[role.id];
    const make=value=>({kind:'crew_count',id:data.ship,storage:role.id,value,original,label:`${role.name}人数`});
    const label=el('label',role.name);const input=bindDraft(numberInput(currentValue(make(original)),0,data.capacity??0),make);input.disabled=!data.editable;input.setAttribute('aria-label',`${role.id} 目标船员人数`);label.append(input);counts.append(label);}
  const t=table(['人员 / ID','岗位','技能总分','目标岗位']);
  for(const r of data.rows){const tr=el('tr');cell(tr,`${r.name}\n#${r.id} · ${r.macro}`).className='named-cell';cell(tr,r.role);cell(tr,Object.values(r.skills).reduce((a,b)=>a+b,0));
    const make=value=>({kind:'crew_role',id:r.id,value,original:r.role,label:`船员 #${r.id} 岗位`});
    const picker=bindDraft(choice(data.roles.map(x=>[x.id,x.name]),currentValue(make(r.role)),`${r.id} 船员岗位`),make);picker.disabled=!r.editable||!data.roles.some(role=>role.id===r.role);cell(tr,'').append(picker);t.body.append(tr);}
  parent.append(t.wrap);pages(parent,data);
}

async function renderGalaxy(parent){
  const data=await job('gameplay',{kind:'map',sector:mapSector,page:mapPage,assetPage:mapAssetPage,gamePath:gamePathValue});mapSector=String(data.selected);
  parent.append(el('p','选择星区可查看玩家资产及势力归属，按 DLC 或势力筛选。连线来自本机地图定义，不代表当前剧情下已开放通行。重叠星区展开显示；未知位置单列。','muted'));
  const bar=el('div',undefined,'feature-toolbar');const search=el('input');search.placeholder='筛选星区名称 / ID';search.setAttribute('aria-label','筛选地图星区');
  const sources=[...new Map(data.sectors.map(s=>[sectorSource(s).id,sectorSource(s)])).values()];const owners=[...new Map(data.sectors.map(s=>[s.owner||'__unknown__',s.ownerName||s.owner||'归属未确认'])).entries()];
  const sourceFilter=choice([['','全部 DLC / 基础游戏'],...sources.map(s=>[s.id,s.name])],mapSourceFilter,'地图 DLC 筛选');
  const ownerFilter=choice([['*','全部势力'],...owners],mapOwnerFilter||'*','地图势力筛选');
  const matches=s=>(!mapSourceFilter||sectorSource(s).id===mapSourceFilter)&&(!mapOwnerFilter||mapOwnerFilter==='*'||(s.owner||'__unknown__')===mapOwnerFilter);
  const visible=data.sectors.filter(matches);
  const filter=async()=>{mapSourceFilter=sourceFilter.value;mapOwnerFilter=ownerFilter.value;const next=data.sectors.filter(matches);if(!next.some(s=>String(s.id)===mapSector))mapSector=String(next[0]?.id||'');mapPage=0;mapAssetPage=0;await renderFeature();};
  sourceFilter.onchange=work(filter);ownerFilter.onchange=work(filter);
  const picker=choice(visible.map(s=>[s.id,`${s.name} · ${s.ownerName||s.owner||'归属未确认'} · ${sectorSource(s).name} · ${s.known?'已发现':'未发现'}`]),mapSector,'地图星区');
  picker.onchange=work(async()=>{mapSector=picker.value;mapPage=0;mapAssetPage=0;await renderFeature();});bar.append(sourceFilter,ownerFilter,search,picker);parent.append(bar);
  const legend=el('div',undefined,'sector-source-legend');legend.setAttribute('aria-label','星区 DLC 来源图例');
  for(const source of new Map(data.sectors.map(s=>{const source=sectorSource(s);return [source.id,source];})).values()){const item=el('span',undefined,'sector-source-badge');const swatch=el('i');swatch.style.backgroundColor=source.color;swatch.setAttribute('aria-hidden','true');item.title=source.id;item.append(swatch,document.createTextNode(source.name));legend.append(item);}parent.append(legend);
  const wrap=el('div',undefined,'galaxy-map');const ns='http://www.w3.org/2000/svg';const svg=document.createElementNS(ns,'svg');svg.setAttribute('role','img');svg.setAttribute('aria-label','可选择的星区地图');
  const positions=new Map();
  const located=data.sectors.filter(s=>s.positionKnown);const positioned=located.length>data.sectors.length/2&&(new Set(located.map(s=>`${s.x}:${s.z}`)).size>located.length/2);
  const xs=data.sectors.map(s=>s.x),zs=data.sectors.map(s=>s.z);const loX=Math.min(...xs),hiX=Math.max(...xs),loZ=Math.min(...zs),hiZ=Math.max(...zs);
  const columns=6,height=Math.max(300,Math.ceil(data.sectors.length/columns)*85+30);let unlocated=0;svg.setAttribute('viewBox',`0 0 1100 ${positioned?700+Math.ceil((data.sectors.length-located.length)/columns)*85:height}`);
  const expanded=positioned&&data.sectors.length>20;const mapColumns=15,mapRows=Math.max(20,Math.ceil(located.length/mapColumns)+5),occupied=new Set();
  const mapWidth=expanded?mapColumns*162+30:1100;const mapHeight=expanded?(mapRows+Math.ceil((data.sectors.length-located.length)/columns))*85+30:null;
  if(expanded){svg.setAttribute('viewBox',`0 0 ${mapWidth} ${mapHeight}`);svg.style.width=mapWidth+'px';}
  for(const [index,s] of data.sectors.entries()){
    const directoryIndex=positioned&&!s.positionKnown?unlocated++:index;
    let x=positioned&&s.positionKnown?30+(s.x-loX)/Math.max(1,hiX-loX)*900:20+(directoryIndex%columns)*162;
    let y=positioned&&s.positionKnown?30+(hiZ-s.z)/Math.max(1,hiZ-loZ)*600:(positioned?700:20)+Math.floor(directoryIndex/columns)*85;
    if(expanded&&s.positionKnown){
      const targetX=(s.x-loX)/Math.max(1,hiX-loX)*(mapColumns-1),targetY=(hiZ-s.z)/Math.max(1,hiZ-loZ)*(mapRows-1);let best=null,distance=Infinity;
      for(let cy=0;cy<mapRows;cy++)for(let cx=0;cx<mapColumns;cx++){const key=`${cx}:${cy}`,d=(cx-targetX)**2+(cy-targetY)**2;if(!occupied.has(key)&&d<distance){best={cx,cy,key};distance=d;}}
      occupied.add(best.key);x=20+best.cx*162;y=20+best.cy*85;
    }else if(expanded)y=20+(mapRows+Math.floor(directoryIndex/columns))*85;
    const source=sectorSource(s);const group=document.createElementNS(ns,'g');group.dataset.search=(s.name+' '+s.macro+' '+source.name+' '+source.id+' '+(s.ownerName||s.owner||'')).toLowerCase();group.dataset.source=source.id;group.dataset.sector=s.id;group.style.display=matches(s)?'':'none';group.setAttribute('transform',`translate(${x},${y})`);group.setAttribute('tabindex','0');group.setAttribute('role','button');group.setAttribute('aria-label',`${s.name} · ${s.ownerName||s.owner||'归属未确认'} · ${source.name}`);
    positions.set(String(s.id),{x:x+75,y:y+32,visible:matches(s),node:group});
    const rect=document.createElementNS(ns,'rect');rect.setAttribute('width','150');rect.setAttribute('height','64');rect.setAttribute('rx','10');rect.setAttribute('fill',String(s.id)===mapSector?'#245ed4':s.known?'#dce9ff':'#e9edf2');rect.setAttribute('stroke',s.known?'#6586ba':'#aab4c2');
    const stripe=document.createElementNS(ns,'rect');stripe.setAttribute('x','0');stripe.setAttribute('y','8');stripe.setAttribute('width','5');stripe.setAttribute('height','48');stripe.setAttribute('fill',source.color);stripe.setAttribute('class','sector-source-stripe');
    const text=document.createElementNS(ns,'text');text.setAttribute('x','10');text.setAttribute('y','22');text.setAttribute('fill',String(s.id)===mapSector?'white':'#21324a');text.textContent=s.name.slice(0,14);
    const note=document.createElementNS(ns,'text');note.setAttribute('x','10');note.setAttribute('y','40');note.setAttribute('fill',String(s.id)===mapSector?'white':'#59708d');note.textContent=`${(s.ownerName||s.owner||'归属未确认').slice(0,9)} · ${s.known?'已知':'未知'}`;
    const sourceText=document.createElementNS(ns,'text');sourceText.setAttribute('x','10');sourceText.setAttribute('y','56');sourceText.setAttribute('class','sector-source-name');sourceText.setAttribute('fill',String(s.id)===mapSector?'white':'#59708d');sourceText.textContent=source.name.slice(0,19);
    const title=document.createElementNS(ns,'title');title.textContent=`${s.name}\n${s.macro}\n归属：${s.ownerName||s.owner||'归属未确认'}\n来源：${source.name} (${source.id})`;group.append(rect,stripe,text,note,sourceText,title);
    const select=work(async()=>{mapSector=String(s.id);mapPage=0;mapAssetPage=0;await renderFeature();});group.onclick=select;group.onkeydown=e=>{if(e.key==='Enter')select();};svg.append(group);
  }
  const lines=[];for(const edge of data.connections||[]){const a=positions.get(String(edge.from)),b=positions.get(String(edge.to));if(!a||!b||!a.visible||!b.visible)continue;const line=document.createElementNS(ns,'line');for(const [key,value] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y}))line.setAttribute(key,value);line.setAttribute('stroke','#94a3b8');line.setAttribute('stroke-width','2');line.setAttribute('class','gate-connection');line.style.pointerEvents='none';svg.prepend(line);lines.push({line,a,b});}
  search.oninput=()=>{const q=search.value.toLowerCase();for(const node of svg.querySelectorAll('g'))node.style.opacity=node.dataset.search.includes(q)?'1':'0.12';for(const option of picker.options)option.hidden=!option.textContent.toLowerCase().includes(q);for(const {line,a,b} of lines)line.style.opacity=a.node.dataset.search.includes(q)||b.node.dataset.search.includes(q)?'1':'0.12';};
  const zoom=el('input');zoom.type='range';zoom.min='50';zoom.max='200';zoom.value='100';zoom.setAttribute('aria-label','地图缩放');zoom.oninput=()=>{svg.style.width=expanded?mapWidth*Number(zoom.value)/100+'px':zoom.value+'%';};parent.append(zoom);wrap.append(svg);parent.append(wrap);
  parent.append(el('p',`匹配 ${visible.length} / ${data.sectors.length} 个星区 · ${lines.length} 条资源定义连接`,'muted'));
  const sector=visible.find(s=>String(s.id)===mapSector);if(!sector){parent.append(el('p','当前 DLC 与势力条件下没有匹配星区。','hint'));return;}
  const actions=section(parent,sector.name,`归属：${sector.ownerName||sector.owner||'归属未确认'} · 来源：${sectorSource(sector).name} · ${sectorSource(sector).id}`);const known={kind:'map_known',id:sector.id,value:1,original:Number(sector.known),label:`发现星区：${sector.name}`,displayOriginal:sector.known?'已发现':'未发现',displayValue:'发现'};
  const connected=new Set((data.connections||[]).flatMap(e=>String(e.from)===mapSector?[String(e.to)]:String(e.to)===mapSector?[String(e.from)]:[]));
  const routes=el('div',undefined,'feature-toolbar');for(const neighbor of data.sectors.filter(s=>connected.has(String(s.id))))routes.append(button(`连接：${neighbor.name}`,async()=>{mapSector=String(neighbor.id);mapSourceFilter='';mapOwnerFilter='';mapPage=0;mapAssetPage=0;await renderFeature();}));if(routes.children.length)actions.append(routes);
  actions.append(draftAction('发现此星区',known),xmlButton(known));const reveal={kind:'map_reveal',id:sector.id,value:1,original:0,label:`揭示星区迷雾：${sector.name}`,displayValue:'揭示已保存探索区域'};
  const buttonReveal=draftAction('揭示探索区域',reveal);buttonReveal.disabled=!data.revealAvailable;actions.append(buttonReveal,xmlButton(reveal));if(!data.revealAvailable)actions.append(el('p','此星区没有已保存的探索树，请先在游戏中进入一次。','hint'));
  const assets=section(parent,`本星区玩家资产 · ${fmt(data.assets?.total||0)} 项`);const assetTable=table(['名称 / ID / 型号','类别','操作']);for(const row of data.assets?.rows||[]){const tr=el('tr');cell(tr,`${row.name} · ${row.code}\n${row.model}`).className='named-cell';cell(tr,row.type);const b=button('管理资产',()=>openAsset(row));b.setAttribute('aria-label',`管理资产 ${row.code}`);cell(tr,'').append(b);assetTable.body.append(tr);}assets.append(assetTable.wrap);if(!data.assets?.total)assets.append(el('p','此星区没有已定位的玩家飞船或空间站。','muted'));if(mapAssetPage)assets.append(button('上一页星区资产',async()=>{mapAssetPage--;await renderFeature();}));if((mapAssetPage+1)*100<(data.assets?.total||0))assets.append(button('下一页星区资产',async()=>{mapAssetPage++;await renderFeature();}));
  const t=table(['空间站 / 星门','类别','状态','操作']);for(const r of data.objects.rows){const tr=el('tr');cell(tr,`${r.name} #${r.id}`);cell(tr,r.class);cell(tr,r.knowledge==='owned'?'玩家资产 · 已知':r.known?'已发现':'未发现');const c={kind:'map_known',id:r.id,value:1,original:Number(r.known),label:`发现地图对象：${r.name}`,displayValue:'发现'};const action=cell(tr,'');if(!r.known)action.append(draftAction('发现',c));action.append(xmlButton(c));t.body.append(tr);}parent.append(t.wrap);
  const page=el('div',undefined,'feature-toolbar');page.append(el('span',`共 ${data.objects.total} 项 · 每页 100 项`));if(mapPage)page.append(button('上一页',async()=>{mapPage--;await renderFeature();}));if((mapPage+1)*100<data.objects.total)page.append(button('下一页',async()=>{mapPage++;await renderFeature();}));parent.append(page);
}

async function renderEncyclopedia(parent){
  const bar=searchBar(parent);const data=await job('gameplay',{kind:'encyclopedia',group:encyclopediaGroup,status:encyclopediaStatus,source:encyclopediaSource,page:featurePage,search:featureSearch,gamePath:gamePathValue});
  const group=choice([['','全部分类'],...data.groups.map(g=>[g,g])],encyclopediaGroup,'百科分类');group.onchange=work(async()=>{encyclopediaGroup=group.value;featurePage=0;await renderFeature();});bar.append(group);
  const status=choice([['unknown','未知（未解锁）'],['known','已知（已解锁）'],['all','全部状态']],encyclopediaStatus,'百科解锁状态');status.onchange=work(async()=>{encyclopediaStatus=status.value;featurePage=0;await renderFeature();});bar.append(status);
  const source=choice([['','全部 DLC / 基础游戏'],...data.sources.map(s=>[s.id,s.name])],encyclopediaSource,'百科 DLC 筛选');source.onchange=work(async()=>{encyclopediaSource=source.value;featurePage=0;await renderFeature();});bar.append(source);
  parent.append(el('p','从本机目录补齐百科知识；解锁百科不会授予蓝图、许可证或科研。已有知识保留，新增条目在游戏中标为未读。','muted'));
  const t=table(['名称 / ID','分类','DLC 来源','状态','操作']);for(const r of data.rows){const tr=el('tr');cell(tr,`${r.name}\n${r.identity}`).className='named-cell';cell(tr,r.group);const badge=el('span',undefined,'sector-source-badge');const swatch=el('i');swatch.style.backgroundColor=sectorSourceColors[r.source.id]||sectorSourceColors.unknown;swatch.setAttribute('aria-hidden','true');badge.title=r.source.id;badge.append(swatch,document.createTextNode(r.source.name));cell(tr,'').append(badge);cell(tr,r.known?'已知':'未知');const c={kind:'encyclopedia',id:r.identity,storage:r.group,value:1,original:Number(r.known),label:`百科：${r.name}`,displayValue:'解锁'};const action=cell(tr,'');if(!r.known)action.append(draftAction('解锁此条目',c));action.append(xmlButton(c));t.body.append(tr);}parent.append(t.wrap);pages(parent,data);
  if(!data.total)parent.append(el('p','当前分类、状态和搜索条件下没有百科条目。未知目录需要读取本机游戏资源。','hint'));
}

async function renderStationSettings(parent,station){
  const data=await job('gameplay',{kind:'station_settings',station,gamePath:gamePathValue});
  const box=section(parent,'空间站交易设置','只处理存档明确保存的价格、规则与分配记录。交易历史、已有订单和仓库实际库存不会自动改写。');
  const prices=table(['物资','已保存买入价','已保存卖出价']);
  for(const r of data.rows){const tr=el('tr');cell(tr,`${r.name} [${r.ware}]`);for(const key of ['buy','sell']){
    if(r[key]===null){cell(tr,'未保存');continue;}const make=value=>({kind:'station_price',id:r.id,station,storage:key,value,original:r[key],label:`${r.name} / ${key} 参考价格`});
    const input=bindDraft(numberInput(currentValue(make(r[key])),0,r.priceRange.max??2147483647),make);input.setAttribute('aria-label',`${r.ware} ${key} 价格`);cell(tr,'').append(input);}
    prices.body.append(tr);}if(data.rows.length)box.append(prices.wrap);else box.append(el('p','未保存可编辑的手动价格字段。自动参考价及交易历史保持只读。','hint'));
  if(data.referenceRows.length){const details=el('details');details.append(el('summary','查看自动参考价格（只读）'));const t=table(['物资','买入参考','卖出参考']);for(const r of data.referenceRows){const tr=el('tr');cell(tr,r.name);cell(tr,r.buy??'未保存');cell(tr,r.sell??'未保存');t.body.append(tr);}details.append(t.wrap);box.append(details);}
  const rules=table(['物资','方向','原规则','目标规则']);for(const r of data.ruleRows)for(const [key,value] of Object.entries(r.settings)){
    const tr=el('tr');cell(tr,r.name);cell(tr,key);cell(tr,value);const make=target=>({kind:'station_rule',station,id:r.id,storage:key,value:target,original:value,label:`${r.name} / ${key} 交易规则`});
    const picker=bindDraft(choice([['-1','原生值 -1'],['0','原生值 0'],...data.rules.map(rule=>[rule.id,`${rule.name} [${rule.id}]`])],currentValue(make(value)),`${r.ware} ${key} 交易规则`),make);cell(tr,'').append(picker);rules.body.append(tr);}box.append(rules.wrap);
  const label=el('label','限制列表中的势力 ID（空格分隔，方向沿用游戏记录）');const make=value=>({kind:'station_restriction',id:station,value,original:data.restrictions,label:'空间站交易限制列表'});
  const restriction=bindDraft(el('input'),make);restriction.value=currentValue(make(data.restrictions));restriction.setAttribute('aria-label','空间站交易限制势力');label.append(restriction);box.append(label);
  const allocations=table(['物资 / 已保存字段','当前配额','目标配额']);for(const r of data.allocations){const tr=el('tr');cell(tr,`${r.name} / ${r.key}`);cell(tr,fmt(r.amount));const make=value=>({kind:'station_allocation',id:r.id,station,storage:r.key,value,original:r.amount,label:`${r.name} 仓储配额`});const input=bindDraft(numberInput(currentValue(make(r.amount))),make);input.setAttribute('aria-label',`${r.ware} 仓储配额`);cell(tr,'').append(input);allocations.body.append(tr);}if(data.allocations.length)box.append(allocations.wrap);else box.append(el('p','未识别到明确保存的手动仓储配额，自动配额保持由游戏计算。','hint'));
}

async function renderResearchTimers(parent){
  const data=await job('gameplay',{kind:'research_tasks',gamePath:gamePathValue});
  const box=section(parent,'进行中的科研计时','将剩余时间设为 0 后，由游戏继续处理完成过程及关联任务；不会直接伪造剧情奖励。');
  if(!data.rows.length){box.append(el('p','没有保存可确认结束时间的科研任务。','muted'));return;}
  for(const r of data.rows){const make=value=>({kind:'research_time',id:r.id,value,original:r.remaining,label:`${r.name} 科研剩余秒数`});const label=el('label',r.name);const input=bindDraft(numberInput(currentValue(make(r.remaining)),0,r.duration),make);input.step='any';input.disabled=!r.editable;input.setAttribute('aria-label',`${r.ware} 科研剩余时间`);label.append(input);box.append(label);}
}
