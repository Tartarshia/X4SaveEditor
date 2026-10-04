'use strict';
let licenceFaction='';

function targetToggle(value,label,disabled,onchange){
  const select=el('select');select.dataset.work='';select.setAttribute('aria-label',label);
  for(const [v,text] of [[0,'未持有 / 未完成'],[1,'持有 / 已完成']]){const option=el('option',text);option.value=v;select.append(option);}
  select.value=String(value);select.disabled=disabled;select.onchange=work(()=>onchange(select.value));return select;
}
function dependencyPreview(rows,kind,storage){
  const known=new Map(rows.map(r=>[r.id,r]));
  const targets=new Set(rows.filter(r=>r.completed??r.owned).map(r=>r.id));
  const actions=new Map();
  for(const c of [...commands.values(),...drafts.values()])if(c.kind===kind&&(storage===undefined||String(c.id)===String(storage)))actions.set(kind==='licence'?c.storage:c.id,Number(c.value));
  const add=(id,trail=new Set())=>{if(trail.has(id)||!known.has(id))return;trail.add(id);const row=known.get(id);for(const pre of row.prerequisites??(row.precursor?[row.precursor]:[]))add(pre,new Set(trail));targets.add(id);};
  for(const [id,value] of actions)if(value)add(id);
  const removed=new Set([...actions].filter(([,value])=>!value).map(([id])=>id));
  let grew=true;while(grew){grew=false;for(const row of rows){const deps=row.prerequisites??(row.precursor?[row.precursor]:[]);if(!removed.has(row.id)&&deps.some(pre=>removed.has(pre))){removed.add(row.id);grew=true;}}}
  for(const id of removed)targets.delete(id);return targets;
}

async function renderShipMods(parent,embedded=false){
  if(!embedded){const bar=el('div',undefined,'feature-toolbar');shipPicker(bar);parent.append(bar);}
  if(!selectedShip){parent.append(el('p','请先按星区、船名或船型选择玩家飞船。','muted'));return;}
  const data=await job('gameplay',{kind:'ship_mods',ship:selectedShip,gamePath:gamePathValue});
  const ship=gameHome.ships.find(s=>String(s.id)===String(selectedShip));
  if(ship)parent.append(el('h3',shipLabel(ship)));
  parent.append(el('p','编辑已安装改装的现有随机属性。范围来自本机游戏资源；“取最优值”按属性方向选择上限或下限。修改后用顶部按钮统一暂存。','muted'));
  const make=(mod,field,value)=>({kind:'mod_value',id:mod.id,storage:field.id,value,original:field.value,
    displayOriginal:field.mode==='count'?field.value:`${Number(((field.value-(field.mode==='factor'?1:0))*100).toFixed(8))}%`,
    displayValue:field.mode==='count'?value:`${Number(((Number(value)-(field.mode==='factor'?1:0))*100).toFixed(8))}%`,
    label:`${ship?shipLabel(ship):selectedShip} / ${mod.location} / ${mod.name} / ${field.name}`});
  const best=async mods=>{for(const mod of mods)for(const field of mod.fields)if(field.editable)queueDraft(make(mod,field,field.best));await renderFeature();};
  const actions=el('div',undefined,'feature-toolbar');const optimal=button('当前飞船全部改装取最优',()=>best(data.mods));optimal.disabled=!data.mods.some(mod=>mod.editable);actions.append(optimal);parent.append(actions);
  const display=(value,field)=>['count','raw'].includes(field.mode)?fmt(value):field.mode==='direct'?`${Number((value*100).toFixed(3))}% (${value})`:`${value}× (${value>=1?'+':''}${Number(((value-1)*100).toFixed(3))}%)`;
  for(const mod of data.mods){
    const section=el('section',undefined,'resource-group');section.append(el('h3',`${mod.categoryName} · ${mod.name} · ${mod.quality===null?'未知品质':'品质 '+mod.quality}`));
    section.append(el('p',`${mod.location} · ${mod.ware} · #${mod.id}`,'muted'));
    if(mod.editable)section.append(button('本改装取最优值',()=>best([mod])));
    const configKey=commandKey({kind:'mod_config',id:mod.id});const pendingConfig=drafts.get(configKey)||commands.get(configKey);
    if(pendingConfig)section.append(el('p',`待配置：${pendingConfig.displayValue}；导出时应用。`,'pending'));
    const t=table(['属性','当前值','目标加成 / 数量','游戏随机范围','最优方向']);
    for(const field of mod.fields){const tr=el('tr');cell(tr,`${field.name}\n${field.id}`).className='named-cell';cell(tr,display(field.value,field));
      const scalar=['count','raw'].includes(field.mode);
      const toDisplay=value=>Number(((Number(value)-(field.mode==='factor'?1:0))*(scalar?1:100)).toFixed(8));
      const fromDisplay=value=>value.trim()===''?'':Number((Number(value)/(scalar?1:100)+(field.mode==='factor'?1:0)).toFixed(12));
      const input=bindDraft(numberInput(toDisplay(currentValue(make(mod,field,field.value))),field.min===null?'':toDisplay(field.min),field.max===null?'':toDisplay(field.max)),value=>make(mod,field,fromDisplay(value)));input.step=field.mode==='count'?'1':'any';input.setAttribute('aria-label',`${mod.id} ${field.id} 改装值`);input.disabled=!field.editable||!!pendingConfig;cell(tr,'').append(input,el('small',field.mode==='raw'?'':scalar?' 单位':' %'));
      cell(tr,field.min===null?'未识别，只读':`${toDisplay(field.min)} ～ ${toDisplay(field.max)}${scalar?'':' %'}`);cell(tr,field.editable?(field.lowerBetter?'越低越好':'越高越好'):'未确认');t.body.append(tr);
    }
    section.append(t.wrap);if(mod.editable)renderModConfiguration(section,mod,data.catalogue,ship,pendingConfig);parent.append(section);
  }
  if(!data.mods.length)parent.append(el('p','这艘飞船没有已记录的船体、引擎、护盾或武器改装。','hint'));
}

function renderModConfiguration(parent,mod,catalogue,ship,pending){
  const details=el('details');details.append(el('summary','更换改装 / 选择附加属性'));
  const choices=catalogue.filter(spec=>spec.category===mod.category);
  const picker=el('select');picker.setAttribute('aria-label',`${mod.id} 改装类型`);
  for(const spec of choices){const option=el('option',`${spec.name} · 品质 ${spec.quality} [${spec.ware}]`);option.value=spec.ware;picker.append(option);}
  picker.value=pending?.ware||mod.ware;
  const fields=el('div',undefined,'mod-config-fields');details.append(picker,fields);
  let inputs=[];
  const fill=()=>{
    fields.replaceChildren();inputs=[];const spec=choices.find(s=>s.ware===picker.value);if(!spec)return;
    fields.append(el('p',`必须保留主属性；最多 ${spec.bonusMax} 项附加属性。更换会替换本改装属性，装备本身保持原样。`,'muted'));
    for(const [key,limits] of Object.entries(spec.fields)){
      const old=mod.fields.find(f=>f.id===key);const row=el('label',undefined,'mod-config-field');
      const pick=el('input');pick.type='checkbox';pick.checked=key===spec.primary||!!(pending?.ware===spec.ware&&key in pending.fields)||(!pending&&picker.value===mod.ware&&!!old);pick.disabled=key===spec.primary;
      pick.setAttribute('aria-label',`${mod.id} 选择附加属性 ${key}`);
      const count=['unitcapacity','missilecapacity','deployablecapacity','countermeasurecapacity'].includes(key);
      const direct=['radarcloak','regiondamage','hidecargochance'].includes(key);
      const lower=['mass','drag','chargetime','travelchargetime','travelattacktime','rechargedelay','radarcloak'].includes(key);
      const toDisplay=n=>Number(((n-(count||direct?0:1))*(count?1:100)).toFixed(8));
      const toNative=n=>Number((Number(n)/(count?1:100)+(count||direct?0:1)).toFixed(12));
      const native=pending?.ware===spec.ware&&key in pending.fields?pending.fields[key]:picker.value===mod.ware&&old?old.value:lower?limits.min:limits.max;
      const input=numberInput(toDisplay(native),toDisplay(limits.min),toDisplay(limits.max));input.step=count?'1':'any';input.setAttribute('aria-label',`${mod.id} 配置 ${key}`);
      row.append(pick,el('span',`${old?.name||limits.name||key}${key===spec.primary?'（主属性）':''}`),input,el('small',count?'单位':'%'));fields.append(row);inputs.push({key,pick,input,toNative});
    }
  };picker.onchange=fill;fill();
  details.append(button('加入改装配置草稿',async()=>{
    const chosen={};for(const item of inputs)if(item.pick.checked){if(item.input.value==='')throw new Error('请输入属性数值');chosen[item.key]=item.toNative(item.input.value);}
    for(const [key,c] of drafts)if(c.kind==='mod_value'&&String(c.id)===String(mod.id))drafts.delete(key);
    const spec=choices.find(s=>s.ware===picker.value);
    queueDraft({kind:'mod_config',id:mod.id,ware:picker.value,fields:chosen,value:picker.value,original:mod.ware,
      label:`${ship?shipLabel(ship):mod.ship} / ${mod.location} / 改装配置`,displayOriginal:mod.name,displayValue:`${spec.name} · ${Object.keys(chosen).length} 项属性`});await renderFeature();
  }),xmlButton({kind:'mod_config',id:mod.id,label:`${mod.name} 原始配置`}));parent.append(details);
}

async function renderHeadquarters(parent){
  const data=await job('gameplay',{kind:'hq',gamePath:gamePathValue});
  for(const hq of data.headquarters)parent.append(el('h3',`${hq.name} · ${hq.sector.name}`));
  if(!data.available)parent.append(el('p','未找到唯一玩家总部或科研容器，科研记录目前只读。','hint'));
  parent.append(el('p','完成一项科研时会同时补齐前置科研；取消完成会撤销依赖它的后续科研。这里只管理完成记录，关联剧情任务和奖励仍由游戏处理。正在执行的科研及内部项目只读。','muted'));
  const targets=dependencyPreview(data.rows,'research');
  const filter=el('input');filter.placeholder='搜索科研名称 / ID';filter.setAttribute('aria-label','筛选总部科研');parent.append(filter);
  const t=table(['科研 / ID','存档状态','目标状态','前置科研','科研资源']);
  const names=new Map(data.rows.map(row=>[row.id,row.name]));
  for(const row of data.rows){const tr=el('tr');cell(tr,`${row.name}\n${row.id}${row.mission?' · 任务前置':''}`).className='named-cell';cell(tr,row.active?'正在执行':row.completed?'已完成':'未完成');
    const make=value=>({kind:'research',id:row.id,value,original:Number(row.completed),label:`总部科研：${row.name}`});
    const select=targetToggle(Number(targets.has(row.id)),`${row.id} 科研状态`,!row.editable,async value=>{queueDraft(make(value));await renderFeature();});
    select.xmlCommand=()=>make(select.value);select.options[0].textContent='未完成';select.options[1].textContent='已完成';cell(tr,'').append(select);
    cell(tr,row.prerequisites.map(id=>names.get(id)||id).join(' / ')||'无').className='named-cell';
    const resources=cell(tr,Object.entries(row.resources||{}).map(([id,amount])=>`${id} × ${fmt(amount)}`).join('\n')||'无物资需求');
    if(!row.completed&&Object.keys(row.resources||{}).length){const c={kind:'research_stock',id:row.id,value:1,original:0,label:`总部补齐科研资源：${row.name}`,displayValue:'按需求补齐库存'};resources.append(draftAction('补齐所需资源',c),xmlButton(c));}
    if(targets.has(row.id)!==row.completed)tr.classList.add('pending');if(!row.editable)tr.title=row.reason;t.body.append(tr);
  }
  filter.oninput=()=>{const q=filter.value.trim().toLowerCase();for(const tr of t.body.rows)tr.hidden=!tr.cells[0].textContent.toLowerCase().includes(q);};parent.append(t.wrap);
  await renderResearchTimers(parent);
}

async function renderLicences(parent){
  const data=await job('gameplay',{kind:'licences',faction:licenceFaction,gamePath:gamePathValue});licenceFaction=data.faction;
  const section=el('section',undefined,'resource-group');section.append(el('h3','势力许可证'));
  section.append(el('p','授予许可时会补齐必要的前置许可；撤销前置会同时撤销依赖许可。这里显示实际持有记录，声望、剧情和游戏规则仍可能影响权限。','muted'));
  const bar=el('div',undefined,'feature-toolbar');const picker=el('select');picker.dataset.work='';picker.setAttribute('aria-label','选择许可证势力');
  for(const faction of data.factions){const option=el('option',`${faction.name} [${faction.id}]`);option.value=faction.id;picker.append(option);}picker.value=licenceFaction;
  picker.onchange=work(async()=>{licenceFaction=picker.value;await renderFeature();});bar.append(picker);section.append(bar);
  const targets=dependencyPreview(data.rows,'licence',data.faction);const t=table(['许可证 / ID','存档持有','目标持有','前置 / 声望条件']);
  const names=new Map(data.rows.map(row=>[row.id,row.name]));
  for(const row of data.rows){const tr=el('tr');cell(tr,`${row.name}\n${row.id}`).className='named-cell';cell(tr,row.owned?'持有':'未持有');
    const make=value=>({kind:'licence',id:data.faction,storage:row.id,value,original:Number(row.owned),label:`${data.name} / ${row.name}`});
    const select=targetToggle(Number(targets.has(row.id)),`${data.faction} ${row.id} 许可证`,!row.editable,async value=>{queueDraft(make(value));await renderFeature();});select.xmlCommand=()=>make(select.value);select.options[0].textContent='未持有';select.options[1].textContent='持有';cell(tr,'').append(select);
    cell(tr,`${row.precursor?(names.get(row.precursor)||row.precursor):'无前置许可'}${row.minrelation!==undefined?' / 基础关系 '+row.minrelation:''}`).className='named-cell';
    if(targets.has(row.id)!==row.owned)tr.classList.add('pending');if(!row.editable)tr.title=row.reason;t.body.append(tr);
  }
  if(data.rows.length)section.append(t.wrap);else section.append(el('p','本机目录未定义此势力的可管理许可证。','muted'));parent.append(section);
}

function renderWorkforce(parent,data,station){
  const workforce=data.workforce;const section=el('section',undefined,'resource-group');section.append(el('h3',`空间站劳动力 · ${fmt(workforce.amount)} / ${fmt(workforce.capacity)}`));
  section.append(el('p','按已存在的居住模块分别计算各族容量，修改的是当前工人数量。游戏仍会根据补给、招募和生产规则继续调整劳动力。','muted'));
  if(workforce.reason)section.append(el('p',workforce.reason,'hint'));
  const make=(row,value)=>({kind:'workforce',id:data.station,storage:row.id,value,original:row.amount,label:`${station.name} / ${row.name} 劳动力`});
  if(workforce.rows.some(row=>row.editable))section.append(button('按居住容量补满劳动力',async()=>{for(const row of workforce.rows)if(row.editable)queueDraft(make(row,row.capacity));await renderFeature();}));
  const t=table(['种族 / ID','当前人数','目标人数','对应居住容量']);
  for(const row of workforce.rows){const tr=el('tr');cell(tr,`${row.name}\n${row.id}`).className='named-cell';cell(tr,fmt(row.amount));
    const input=bindDraft(numberInput(currentValue(make(row,row.amount)),0,row.capacity),value=>make(row,value));input.disabled=!row.editable;input.setAttribute('aria-label',`${row.id} 劳动力目标人数`);cell(tr,'').append(input);cell(tr,fmt(row.capacity));t.body.append(tr);}
  if(workforce.rows.length)section.append(t.wrap);else section.append(el('p','没有可确认的居住容量或现有劳动力记录。','muted'));parent.append(section);
}
