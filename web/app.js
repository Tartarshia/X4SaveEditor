'use strict';
const $ = id => document.getElementById(id);
let token = '', revision = null, snapshot = null, busy = false;
let locationState = {mode:'children', value:0, after:0}, history = [], rows = [], selected = null;
let attributes = {}, changes = new Map(), advancedDrafts = new Map(), hasMore = false;
let shortcutCatalog = [];
const fmt = n => Number(n).toLocaleString('zh-CN');
const cell = (row, value) => { const td=document.createElement('td'); td.textContent=String(value); td.title=String(value); row.append(td); return td; };
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
function showError(error) { $('errorMessage').textContent=error.message || String(error); if (!$('errorDialog').open) $('errorDialog').showModal(); }
function work(fn) { return async (...args) => { try { await fn(...args); } catch(e) { showError(e); } }; }
async function api(path, options={}) {
  const response=await fetch(path,{...options,headers:{'X-X4-Token':token,...options.headers}});
  const data=await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败：${response.status}`);
  return data;
}
function setBusy(value, message='就绪') {
  busy=value; document.body.classList.toggle('working',value);
  $('busyIndicator').hidden=!value;
  document.querySelectorAll('[data-work]').forEach(button=>button.disabled=value || button.dataset.unavailable==='true');
  $('status').textContent=message;
  if (!value) $('elapsed').textContent='';
}
async function job(action, data={}) {
  if (busy) throw new Error('后台任务正在运行，请等待完成');
  const started=performance.now();
  setBusy(true,'正在处理…');
  try {
    const {id}=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,revision,...data})});
    while (true) {
      const result=await api('/api/job?id='+encodeURIComponent(id));
      $('status').textContent=result.message || '正在处理…';
      $('elapsed').textContent=((performance.now()-started)/1000).toFixed(1)+' 秒';
      if (result.status==='error') throw new Error(result.error);
      if (result.status==='done') return result.result;
      await delay(180);
    }
  } finally { setBusy(false); }
}
function updateCount(){ $('changeCount').textContent=changes.size + commands.size; }
function applySnapshot(data) {
  snapshot=data; revision=data.revision;
  if (!data.meta) return;
  const m=data.meta;
  $('filename').textContent=data.source.split(/[\\/]/).pop();
  $('summary').textContent=`XML ${(m.xml_bytes/1048576).toFixed(1)} MiB · ${fmt(m.nodes)} 节点 · ${m.tags} 种标签 · 首次索引 ${m.seconds.toFixed(1)} 秒`;
}
async function openSave(path) {
  if ((changes.size || commands.size || drafts.size || advancedDrafts.size) && !confirm('打开其他存档会丢弃待修改清单和未暂存输入，继续？')) return;
  $('openDialog').close();
  const data=await job('open',{path});
  changes.clear(); commands.clear(); drafts.clear(); advancedDrafts.clear(); sourceContext=null; updateDraftCount(); selectedShip=''; selectedSector=''; shipSearch=''; resourceStation=''; diplomacySource=''; diplomacyTarget=''; includeInternalFactions=false; featurePage=0; stationPage=0; stationSearch=''; stationSector=''; updateCount(); history=[];
  gameHome=null;
  $('featureBody').textContent='正在识别玩家账户、舰船和船员…';
  shortcutCatalog=[];
  $('shortcutButtons').textContent='正在识别常用节点…';
  applySnapshot(data);
  await navigate('children',0,0,false);
  await loadShortcuts();
  await loadGameplay();
}
async function loadShortcuts() {
  try {
    shortcutCatalog=await job('shortcuts');
    const container=$('shortcutButtons');container.replaceChildren();
    for(const item of shortcutCatalog){
      const button=document.createElement('button');button.dataset.work='';button.dataset.shortcut=item.key;
      button.dataset.unavailable=String(item.count===0);button.disabled=item.count===0;
      button.title=`${item.group} · ${item.description}`+(item.count===0?' 本存档未找到匹配节点。':'');
      const title=document.createElement('span');title.textContent=item.title;
      const count=document.createElement('small');count.textContent=fmt(item.count);
      button.append(title,count);button.onclick=work(()=>navigate('shortcut',item.key));container.append(button);
    }
  } catch(e) {
    const container=$('shortcutButtons');container.replaceChildren();
    const note=document.createElement('span');note.className='muted';note.textContent='常用节点暂时无法识别，仍可使用结构浏览。';
    const retry=document.createElement('button');retry.textContent='重试';retry.dataset.work='';retry.onclick=work(loadShortcuts);
    container.append(note,retry);throw e;
  }
}
async function navigate(mode, value, after=0, remember=true) {
  if (!revision) return;
  const next={mode,value,after};
  const data=await job('query',next);
  if (remember) history.push({...locationState});
  locationState=next; hasMore=data.length>200; rows=data.slice(0,200); selected=null; attributes={};
  const body=$('nodes').querySelector('tbody'); body.replaceChildren();
  const knownShips=new Map((gameHome?.ships||[]).map(ship=>[String(ship.id),ship]));
  for (const row of rows) {
    const tr=document.createElement('tr'); tr.dataset.node=row[0]; tr.tabIndex=0;
    const ship=knownShips.get(String(row[0]));
    [row[0],row[1],row[4],ship?shipLabel(ship):row[5]].forEach(value=>cell(tr,value));
    tr.onclick=work(()=>busy?null:selectRow(row));
    tr.ondblclick=work(async()=>{while(busy) await delay(50); await navigate('children',row[0]);});
    tr.onkeydown=work(async e=>{if(e.key==='Enter' && !busy) await selectRow(row);});
    body.append(tr);
  }
  $('empty').hidden=rows.length>0;
  if (!rows.length) { $('empty').querySelector('h3').textContent='这里没有匹配的节点'; $('empty').querySelector('p').textContent='尝试其他查询，或返回上一层。'; }
  const shortcut=mode==='shortcut'?shortcutCatalog.find(item=>item.key===value):null;
  const names={children:'子节点',tag:'标签',id:'ID',node:'节点',text:'摘要包含',shortcut:'快捷入口'};
  $('location').textContent=`${names[mode]}：${shortcut?.title || value} · 本页 ${rows.length} 条${hasMore?' · 还有下一页':' · 已到末尾'}`;
  $('shortcutHint').hidden=!shortcut;
  $('shortcutHint').textContent=shortcut?`${shortcut.description} 共找到 ${fmt(shortcut.count)} 个节点。`:'';
  document.querySelectorAll('[data-shortcut]').forEach(button=>button.classList.toggle('active',button.dataset.shortcut===shortcut?.key));
  $('nodeTitle').textContent='节点详情'; $('attrCount').textContent='尚未选中';
  $('attributes').replaceChildren(); $('preview').textContent='选中左侧节点以查看属性。';
}
async function selectRow(row) {
  const data=await job('details',{node:row[0]});
  selected=row; attributes=data[0];
  document.querySelectorAll('#nodes tbody tr').forEach(tr=>tr.classList.toggle('selected',tr.dataset.node===String(row[0])));
  const ship=gameHome?.ships.find(item=>String(item.id)===String(row[0]));
  $('nodeTitle').textContent=ship?shipLabel(ship):`${row[1]} · #${row[0]}`;
  $('attrCount').textContent=`${Object.keys(attributes).length} 个属性`;
  $('preview').textContent=data[1]; renderAttributes();
}
function renderAttributes() {
  const container=$('attributes'); container.replaceChildren();
  if (!selected) return;
  const node=selected[0];
  for (const [key, original] of Object.entries(attributes)) {
    const id=node+':'+key, edit=changes.get(id), draft=advancedDrafts.get(id);
    const row=document.createElement('div'); row.className='attr'+(edit||draft?' changed':'');
    const label=document.createElement('label'); label.textContent=key;
    const input=document.createElement('input'); input.value=draft?.value??edit?.value??original; input.setAttribute('aria-label',key); input.dataset.work='';
    input.oninput=()=>{
      if(input.value===(edit?.value??original))advancedDrafts.delete(id);
      else advancedDrafts.set(id,{node,key,original,value:input.value});
      row.classList.toggle('changed',advancedDrafts.has(id)||changes.has(id));updateDraftCount();
    };
    row.append(label,input); container.append(row);
  }
  if (!Object.keys(attributes).length) { const p=document.createElement('p'); p.className='muted'; p.textContent='此节点没有属性，可进入子节点继续浏览。'; container.append(p); }
}
function review() {
  const body=$('reviewTable').querySelector('tbody'); body.replaceChildren();
  for (const [id,edit] of changes) {
    const tr=document.createElement('tr'); cell(tr,`#${edit.node} / ${edit.key}`); cell(tr,edit.original); cell(tr,edit.value);
    const button=document.createElement('button'); button.textContent='撤销';
    button.onclick=()=>{changes.delete(id); updateCount(); tr.remove(); renderAttributes();};
    cell(tr,'').append(xmlButtonForNode(edit.node),button); body.append(tr);
  }
  appendCommandReview(body);
  if (!$('reviewDialog').open) $('reviewDialog').showModal();
}
function xmlButtonForNode(node){return button('查看原始 XML',async()=>{if($('reviewDialog').open)$('reviewDialog').close();await openOriginalNode(node);},'xml-link');}
async function listSaves() {
  const paths=await api('/api/saves'); const container=$('saves'); container.replaceChildren();
  if (!paths.length) container.textContent='未发现默认目录中的存档，可输入路径或选择文件。';
  for (const save of paths) {
    const button=document.createElement('button'); button.className='save-item'; button.dataset.work='';
    const title=document.createElement('span'); title.textContent=save.name; button.title=save.path;
    const subtitle=document.createElement('small'); subtitle.textContent=`${(save.bytes/1048576).toFixed(1)} MiB · ${new Date(save.mtime*1000).toLocaleString()}`;
    button.append(title,subtitle); button.onclick=work(()=>openSave(save.path)); container.append(button);
  }
  $('openDialog').showModal();
}
function upload(file) {
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();
    xhr.open('POST','/api/upload?name='+encodeURIComponent(file.name)); xhr.setRequestHeader('X-X4-Token',token);
    xhr.upload.onprogress=e=>{$('status').textContent=e.lengthComputable?`正在导入到本机：${Math.round(e.loaded/e.total*100)}%`:'正在导入到本机…';};
    xhr.onload=()=>{try{const data=JSON.parse(xhr.responseText); if(xhr.status!==200) throw new Error(data.error); resolve(data);}catch(e){reject(e);}};
    xhr.onerror=()=>reject(new Error('本机文件传输失败'));
    xhr.send(file);
  });
}
$('open').onclick=work(listSaves);
$('openPath').onclick=work(()=>openSave($('sourcePath').value.trim().replace(/^"|"$/g,'')));
$('sourcePath').onkeydown=e=>{if(e.key==='Enter') $('openPath').click();};
$('chooseFile').onclick=()=>$('file').click();
$('file').onchange=work(async()=>{
  const file=$('file').files[0]; if(!file) return;
  $('openDialog').close(); setBusy(true,'正在导入到本机…');
  let result;
  try{result=await upload(file);}finally{setBusy(false);$('file').value='';}
  await openSave(result.path);
});
$('search').onclick=work(async()=>{
  const value=$('searchText').value.trim(),mode=$('mode').value; if(!value) return;
  if(mode==='node' && !/^\d+$/.test(value)) throw new Error('节点编号应为整数');
  await navigate(mode,value);
});
$('searchText').onkeydown=e=>{if(e.key==='Enter' && !busy) $('search').click();};
$('root').onclick=work(()=>navigate('children',0));
$('back').onclick=work(async()=>{if(!history.length)return;const prev=history[history.length-1];await navigate(prev.mode,prev.value,prev.after,false);history.pop();});
$('enter').onclick=work(()=>selected?navigate('children',selected[0]):null);
$('parent').onclick=work(()=>selected?navigate('node',selected[2]):null);
$('next').onclick=work(()=>hasMore?navigate(locationState.mode,locationState.value,rows[rows.length-1][0]):null);
$('review').onclick=review;
$('tags').onclick=work(async()=>{
  if(!revision)return;const data=await job('tags');const body=$('tagTable').querySelector('tbody');body.replaceChildren();$('tagFilter').value='';
  for(const [tag,count] of data){const tr=document.createElement('tr');cell(tr,tag);cell(tr,fmt(count));const button=document.createElement('button');button.textContent='浏览';button.onclick=work(async()=>{$('tagsDialog').close();feature='advanced';showMode();await navigate('tag',tag);});cell(tr,'').append(button);body.append(tr);}
  $('tagsDialog').showModal();
});
$('tagFilter').oninput=()=>{const q=$('tagFilter').value.toLowerCase();for(const tr of $('tagTable').querySelector('tbody').rows)tr.hidden=!tr.cells[0].textContent.toLowerCase().includes(q);};
$('export').onclick=work(async()=>{if(!revision)return;if(drafts.size||advancedDrafts.size)await stagePending();$('exportSummary').textContent=`本次将导出 ${changes.size} 项属性修改和 ${commands.size} 项功能修改，保留原存档。`;$('exportName').value=$('filename').textContent.replace(/\.xml/i,'_edited.xml');$('exportDialog').showModal();});
$('confirmExport').onclick=work(async()=>{
  const values=Object.create(null);for(const edit of changes.values()){if(!values[edit.node])values[edit.node]=Object.create(null);values[edit.node][edit.key]=edit.value;}
  const name=$('exportName').value.trim();$('exportDialog').close();
  const result=await job('export',{changes:values,name,commands:[...commands.values()],gamePath:gamePathValue});$('exportPath').textContent=result.path;$('download').href=result.url;$('resultDialog').showModal();
});
document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>button.closest('dialog').close());
window.addEventListener('beforeunload',e=>{if(changes.size||commands.size||drafts.size||advancedDrafts.size||busy){e.preventDefault();e.returnValue='';}});
const splitter=$('splitter');let dragging=false;
function resize(percent){const value=Math.max(25,Math.min(75,percent));document.documentElement.style.setProperty('--left',value+'%');splitter.setAttribute('aria-valuenow',Math.round(value));try{localStorage.setItem('x4-split',value);}catch{}}
splitter.onpointerdown=e=>{dragging=true;splitter.setPointerCapture(e.pointerId);e.preventDefault();};
splitter.onpointermove=e=>{if(!dragging)return;const rect=$('workspace').getBoundingClientRect();resize((e.clientX-rect.left)/rect.width*100);};
splitter.onpointerup=()=>dragging=false;splitter.onlostpointercapture=()=>dragging=false;
splitter.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();resize(Number(splitter.getAttribute('aria-valuenow'))+(e.key==='ArrowLeft'?-2:2));}};
work(async()=>{try{const saved=Number(localStorage.getItem('x4-split'));if(saved)resize(saved);}catch{}const session=await api('/api/session');token=session.token;applySnapshot(session);if(revision){await navigate('children',0,0,false);await loadShortcuts();await loadGameplay();}})()
