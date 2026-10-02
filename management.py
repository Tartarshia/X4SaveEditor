"""Catalogue-backed research, licences, installed mods and station workforce.

Save XML is accessed only through the disk index; all edits use the immutable
snapshot and preserve unrelated records.
"""
from functools import lru_cache
import math
from edits import element


MOD_LABELS = {
    'damage':'伤害','cooling':'冷却','reload':'射速','speed':'弹速','beamlength':'光束长度',
    'lifetime':'弹体寿命','chargetime':'武器充能时间','mining':'采矿效率','rotationspeed':'转动速度',
    'sticktime':'附着时间','surfaceelement':'表面组件伤害','forwardthrust':'前向推力',
    'rotationthrust':'转向推力','strafethrust':'侧向推力','strafeacc':'侧向加速度',
    'boostthrust':'加速推力','boostacc':'加速模式加速度','boostduration':'加速持续时间',
    'travelthrust':'巡航推力','travelstartthrust':'巡航起步推力','travelattacktime':'巡航加速时间',
    'travelchargetime':'巡航充能时间','mass':'质量','drag':'阻力','maxhull':'船体强度',
    'capacity':'护盾容量','rechargerate':'护盾充能速度','rechargedelay':'护盾充能延迟',
    'radarrange':'雷达范围','radarcloak':'雷达探测距离修正','regiondamage':'环境伤害抗性',
    'hidecargochance':'货物隐匿概率','countermeasurecapacity':'干扰弹容量增加',
    'deployablecapacity':'部署物容量增加','missilecapacity':'导弹容量增加','unitcapacity':'无人机容量增加',
}
LOWER_BETTER = {'mass','drag','chargetime','travelchargetime','travelattacktime','rechargedelay','radarcloak'}
ABSOLUTE_MOD_FIELDS = {'countermeasurecapacity','deployablecapacity','missilecapacity','unitcapacity'}
DIRECT_MOD_FIELDS = {'radarcloak','regiondamage','hidecargochance'}
MOD_CATEGORIES = {'ship':'船体','engine':'引擎','shield':'护盾','weapon':'武器 / 炮塔'}


def whole(value, low=0, high=2147483647):
    if isinstance(value,bool) or str(value).strip()!=str(int(value)):
        raise ValueError('请输入整数')
    value=int(value)
    if not low<=value<=high:
        raise ValueError(f'数值必须在 {low} 至 {high} 之间')
    return value


def dependency_state(initial, specifications, updates):
    """Resolve grants and dependent revocations without command-order effects."""
    grants=set()
    def visit(identity, trail=()):
        if identity in trail:
            raise ValueError('资源目录的前置条件存在循环')
        if identity not in specifications:
            raise ValueError('无法确认前置条件：'+identity)
        if identity in grants:
            return
        for precursor in specifications[identity].get('prerequisites',[]):
            visit(precursor,trail+(identity,))
        grants.add(identity)
    for identity,value in updates.items():
        if value:visit(identity)
    removed={identity for identity,value in updates.items() if not value}
    while True:
        dependents={identity for identity,spec in specifications.items()
                    if removed.intersection(spec.get('prerequisites',[]))}
        if dependents<=removed:break
        removed.update(dependents)
    if grants & removed:
        raise ValueError('同时完成/授予和撤销了相互依赖的项目，请调整草稿')
    return (set(initial)|grants)-removed


class ManagementFeatures:
    def headquarters(self):
        return [n for n,a in self.assets.items() if a.get('class')=='station'
                and a.get('macro')=='station_pla_headquarters_base_01_macro']

    @lru_cache(maxsize=1)
    def installed_mods(self):
        result={}
        for container in self.members.get('modifications',[]):
            ship=self.asset(container)
            if ship not in self.ships:continue
            parent=self.node(container)[0]
            location=[]
            n=parent
            while n and n!=ship and len(location)<12:
                attrs=self.attrs(n)
                tag=self.names[self.node(n)[1]]
                if attrs.get('group'):location.append(attrs['group'])
                elif attrs.get('macro'):location.append(self.game.model_name(attrs['macro']))
                elif tag in ('shields','weapons','turrets','engines'):
                    location.append({'shields':'护盾组','weapons':'武器组','turrets':'炮塔组','engines':'引擎组'}[tag])
                n=self.node(n)[0]
            for category in MOD_CATEGORIES:
                nodes=self.children(container,category)
                for node in nodes:
                    attrs=self.attrs(node)
                    wid=attrs.get('ware','')
                    definition=self.game.modifications.get((category,wid))
                    fields=[]
                    for key,value in attrs.items():
                        if key in ('ware','generated'):continue
                        try:current=float(value)
                        except (ValueError,TypeError):continue
                        spec=definition['fields'].get(key) if definition else None
                        editable=bool(spec and key in MOD_LABELS and len(nodes)==1 and math.isfinite(current))
                        fields.append({'id':key,'name':MOD_LABELS.get(key,key),'value':current,
                            'min':spec['min'] if spec else None,'max':spec['max'] if spec else None,
                            'best':(spec['min'] if key in LOWER_BETTER else spec['max']) if editable else None,
                            'mode':'raw' if key not in MOD_LABELS else 'count' if key in ABSOLUTE_MOD_FIELDS else 'direct' if key in DIRECT_MOD_FIELDS else 'factor',
                            'editable':editable,'lowerBetter':key in LOWER_BETTER})
                    result[node]={'id':node,'ship':ship,'ware':wid,'name':self.game.name(wid),
                        'category':category,'categoryName':MOD_CATEGORIES[category],
                        'location':' / '.join(reversed(location)) or MOD_CATEGORIES[category],
                        'quality':definition['quality'] if definition else None,'fields':fields,
                        'editable':any(f['editable'] for f in fields)}
        return result

    def research_data(self, request):
        hqs=self.headquarters()
        containers=self.children(self.player,'research')
        entries={}
        for parent in containers:
            for node in self.children(parent,'research'):
                entries.setdefault(self.attrs(node).get('ware',''),[]).append(node)
        active=set()
        for hq in hqs:
            for tag in ('production','buildtasks'):
                for parent in self.children(hq,tag):
                    stack=[parent];visited=0
                    while stack:
                        node=stack.pop();visited+=1
                        if visited>10000:
                            raise ValueError('总部任务记录过多，无法安全确认科研活动')
                        ware=self.attrs(node).get('ware','')
                        if ware in self.game.research:active.add(ware)
                        stack.extend(n for n, in self.db.execute('SELECT id FROM nodes INDEXED BY parent_nodes WHERE parent=?',(node,)))
        rows=[]
        for wid in set(self.game.research)|set(entries):
            spec=self.game.research.get(wid)
            nodes=entries.get(wid,[])
            safe=all(set(self.attrs(n))<={'ware','method'} and self.attrs(n).get('method','research')=='research'
                     and not self.db.execute('SELECT 1 FROM nodes WHERE parent=? LIMIT 1',(n,)).fetchone() for n in nodes)
            editable=bool(spec and not spec['hidden'] and len(nodes)<=1 and safe and len(containers)<=1 and len(hqs)==1 and wid not in active)
            rows.append({'id':wid,'name':self.game.name(wid),'completed':bool(nodes),'nodes':nodes,
                         'prerequisites':spec['prerequisites'] if spec else [],'time':spec['time'] if spec else None,
                         'resources':spec.get('resources',{}) if spec else {},
                         'mission':spec['mission'] if spec else False,'hidden':spec['hidden'] if spec else True,
                         'active':wid in active,'editable':editable,
                         'reason':'' if editable else '正在科研、内部项目、记录不唯一或未找到唯一总部'})
        rows.sort(key=lambda row:(row['hidden'],row['id']))
        query=str(request.get('search','')).lower()
        filtered=[r for r in rows if query in (r['name']+' '+r['id']).lower()]
        return {'headquarters':[{'id':n,'name':self.asset_name(n),'sector':self.sector(n)} for n in hqs],
                'rows':filtered,'entries':entries,'container':containers[0] if len(containers)==1 else None,
                'active':sorted(active),'available':len(hqs)==1 and len(containers)<=1}

    def licence_data(self, request):
        permitted={r['id'] for r in self.relation_rows() if not r['id'].lower().startswith('visitor')}
        if not permitted and not request.get('faction'):
            return {'faction':'','name':'','rows':[],'saved':{},'container':None,'factions':[]}
        faction=str(request.get('faction') or next(iter(sorted(permitted)),''))
        if faction not in permitted:raise ValueError('请选择可见的非玩家势力')
        parents=self.children(self.factions.get('player'),'licences')
        saved={}
        for parent in parents:
            for node in self.children(parent,'licence'):
                saved.setdefault(self.attrs(node).get('type',''),[]).append(node)
        specs=self.game.licences.get(faction,{})
        rows=[]
        for kind in set(specs)|{t for t,ns in saved.items() if any(faction in self.attrs(n).get('factions','').split() for n in ns)}:
            spec=specs.get(kind,{})
            nodes=saved.get(kind,[])
            editable=bool(spec and 'hidden' not in spec.get('tags','').split() and len(nodes)<=1 and len(parents)<=1 and self.factions.get('player'))
            rows.append({'id':kind,'name':spec.get('name',kind),'owned':any(faction in self.attrs(n).get('factions','').split() for n in nodes),
                         'precursor':spec.get('precursor'),'minrelation':spec.get('minrelation'),
                         'editable':editable,'reason':'' if editable else '内部许可、未识别的许可或重复记录'})
        return {'faction':faction,'name':self.game.name(faction),'rows':sorted(rows,key=lambda r:(r['name'],r['id'])),
                'saved':saved,'container':parents[0] if len(parents)==1 else None,
                'factions':[{'id':f,'name':self.game.name(f)} for f in sorted(permitted)]}

    @lru_cache(maxsize=100)
    def workforce_data(self, station):
        if station not in self.station_accounts:raise ValueError('请选择玩家空间站')
        capacity={};reason=''
        for node,attrs in self.station_components(station):
            if attrs.get('class')!='habitation':continue
            spec=self.game.habitation(attrs.get('macro',''))
            if spec is None or spec['capacity']<0:
                reason='存在未识别的居住模块，无法确认容量';continue
            capacity[spec['race']]=capacity.get(spec['race'],0)+spec['capacity']
        parents=self.children(station,'workforces')
        if len(parents)>1:reason='劳动力容器不唯一'
        current={}
        for parent in parents:
            for node in self.children(parent,'workforce'):
                race=self.attrs(node).get('race','')
                if race in current:reason='存在重复种族劳动力记录'
                current[race]={'node':node,'amount':int(self.attrs(node).get('amount',0))}
        root=self.first(0,'savegame')
        time=self.attrs(self.first(self.first(root,'info'),'game')).get('time')
        if not parents and capacity and (time is None or not math.isfinite(float(time))):
            reason='存档缺少游戏时间，无法初始化劳动力容器'
        rows=[{'id':race,'name':self.game.races.get(race,race),'amount':current.get(race,{}).get('amount',0),
               'capacity':capacity.get(race,0),'node':current.get(race,{}).get('node'),
               'editable':not reason and race in capacity} for race in set(current)|set(capacity)]
        return {'rows':sorted(rows,key=lambda r:r['name']),'capacity':sum(capacity.values()),
                'amount':sum(r['amount'] for r in rows),'reason':reason,'container':parents[0] if len(parents)==1 else None,'time':time}

    def plan_management(self, plan, commands):
        research={};licences={};workforce={}
        for command in commands:
            kind=command['kind']
            if kind=='mod_config':
                node=whole(command['id'],1,2**63-1)
                mod=self.installed_mods().get(node)
                if not mod or not mod['editable']:raise ValueError('不是可编辑的已安装改装')
                spec=self.game.modifications.get((mod['category'],str(command.get('ware',''))))
                if not spec:raise ValueError('目标改装与装备类别不匹配')
                original=self.attrs(node)
                old_spec=self.game.modifications.get((mod['category'],mod['ware']))
                if not old_spec or set(original)-set(old_spec['fields'])-{'ware','generated'}:raise ValueError('原改装包含未知属性，不支持更换')
                fields=command.get('fields')
                if not isinstance(fields,dict) or spec['primary'] not in fields or not set(fields)<=set(spec['fields']):raise ValueError('必须包含主属性，且只能选择该改装的附加属性')
                if len(fields)-1>spec['bonusMax']:raise ValueError('附加属性数量超过该改装定义的上限')
                updates={'ware':str(command['ware'])}
                for key,value in fields.items():
                    if key not in MOD_LABELS or isinstance(value,bool):raise ValueError('无法确认此改装属性')
                    value=float(value);limit=spec['fields'][key]
                    if not math.isfinite(value) or not limit['min']<=value<=limit['max']:raise ValueError('改装属性超出游戏范围：'+key)
                    if key in ABSOLUTE_MOD_FIELDS and not value.is_integer():raise ValueError('容量属性必须为整数')
                    updates[key]=format(value,'.12g')
                plan.unset(node,*[key for key in original if key not in updates and key!='generated'])
                plan.set(node,**updates)
                plan.summaries.append(f'{self.ship_description(mod["ship"])} / 改装 → {self.game.name(command["ware"])}')
            elif kind=='mod_value':
                node=whole(command['id'],1,2**63-1)
                mod=self.installed_mods().get(node)
                key=str(command.get('storage',''))
                field=next((f for f in mod['fields'] if f['id']==key),None) if mod else None
                if not field or not field['editable']:raise ValueError('不是可编辑的玩家飞船已安装改装属性')
                if isinstance(command['value'],bool):raise ValueError('改装值必须为数值')
                value=float(command['value'])
                if not math.isfinite(value) or not field['min']<=value<=field['max']:
                    raise ValueError(f'{field["name"]} 必须在 {field["min"]} 至 {field["max"]} 之间')
                if field['mode']=='count' and not value.is_integer():raise ValueError('容量增加值必须为整数')
                plan.set(node,**{key:format(value,'.12g')})
                plan.summaries.append(f'{self.ship_description(mod["ship"])} / {mod["name"]} / {field["name"]} → {value:g}')
            elif kind=='research':research[str(command['id'])]=whole(command['value'],0,1)
            elif kind=='licence':
                licences.setdefault(str(command['id']),{})[str(command['storage'])]=whole(command['value'],0,1)
            elif kind=='workforce':
                workforce.setdefault(whole(command['id'],1,2**63-1),{})[str(command['storage'])]=whole(command['value'])
        if research:self.plan_research(plan,research)
        if licences:self.plan_licences(plan,licences)
        for station,updates in workforce.items():
            data=self.workforce_data(station)
            if data['reason']:raise ValueError(data['reason'])
            rows={r['id']:r for r in data['rows']}
            for race,value in updates.items():
                if race not in rows or not rows[race]['editable'] or value>rows[race]['capacity']:
                    raise ValueError('劳动力种族未识别或超过对应居住容量')
            additions=[]
            for race,value in updates.items():
                row=rows[race]
                if row['node']:plan.set(row['node'],amount=value)
                elif value:additions.append(element('workforce',{'race':race,'amount':value}))
                plan.summaries.append(f'{self.asset_name(station)} / {row["name"]} 劳动力 → {value:,}')
            if additions:
                xml=''.join(additions)
                plan.add(data['container'] or station,xml if data['container'] else element('workforces',{'lasttime':data['time']},xml))

    def plan_research(self, plan, updates):
        data=self.research_data({})
        rows={r['id']:r for r in data['rows']}
        if not data['available']:raise ValueError('未找到唯一玩家总部或科研容器')
        for wid in updates:
            if wid not in rows or not rows[wid]['editable']:raise ValueError('科研项目只读或正在运行：'+wid)
        initial={wid for wid,row in rows.items() if row['completed']}
        target=dependency_state(initial,self.game.research,updates)
        changed=initial^target
        for wid in changed:
            if wid not in rows or not rows[wid]['editable']:raise ValueError('依赖的科研项目正在运行或不可编辑：'+wid)
        additions=[]
        for wid in sorted(changed):
            if wid in target:additions.append(element('research',{'ware':wid,'method':'research'}))
            else:plan.remove_leaf(rows[wid]['nodes'][0])
            plan.summaries.append(f'科研 / {self.game.name(wid)} → '+('已完成' if wid in target else '未完成'))
        if additions:
            xml=''.join(additions)
            plan.add(data['container'] or self.player,xml if data['container'] else element('research',children=xml))

    def plan_licences(self, plan, updates_by_faction):
        by_type={};saved=None;container=None
        for faction,updates in updates_by_faction.items():
            data=self.licence_data({'faction':faction})
            rows={r['id']:r for r in data['rows']}
            for kind in updates:
                if kind not in rows or not rows[kind]['editable']:raise ValueError('许可类型不存在或只读：'+kind)
            specs={kind:{'prerequisites':[s['precursor']] if s.get('precursor') else []}
                   for kind,s in self.game.licences.get(faction,{}).items()}
            initial={kind for kind,row in rows.items() if row['owned']}
            target=dependency_state(initial,specs,updates)
            for kind in initial^target:
                if kind not in rows or not rows[kind]['editable']:raise ValueError('依赖的许可证无法安全修改：'+kind)
                by_type.setdefault(kind,{})[faction]=kind in target
            saved=data['saved'];container=data['container']
        additions=[]
        for kind,updates in by_type.items():
            nodes=saved.get(kind,[])
            node=nodes[0] if nodes else None
            factions=self.attrs(node).get('factions','').split()
            for faction,owned in updates.items():
                if owned and faction not in factions:factions.append(faction)
                elif not owned:factions=[f for f in factions if f!=faction]
                plan.summaries.append(f'{self.game.name(faction)} / 许可证 {kind} → '+('持有' if owned else '未持有'))
            if node:
                if factions:plan.set(node,factions=' '.join(factions))
                else:plan.remove_leaf(node)
            elif factions:additions.append(element('licence',{'type':kind,'factions':' '.join(factions)}))
        if additions:
            xml=''.join(additions)
            plan.add(container or self.factions['player'],xml if container else element('licences',children=xml))
