"""Additional catalogue-backed editing, without materializing save XML trees."""
from functools import lru_cache
import math
import secrets
from edits import element
from management import whole, MOD_LABELS

EQUIPMENT_CLASSES={'engine','shieldgenerator','weapon','turret'}
AMMO_GROUPS={'missiles':'missile','countermeasures':'countermeasure','deployables':'deployable','drones':'unit'}


class ExpansionFeatures:
    def leaf(self,node):
        return not self.db.execute('SELECT 1 FROM nodes WHERE parent=? LIMIT 1',(node,)).fetchone()

    @lru_cache(maxsize=32)
    def ship_components(self,ship):
        if ship not in self.ships:raise ValueError('请选择玩家飞船')
        result=[];stack=[ship];seen=0
        while stack:
            node=stack.pop();seen+=1
            if seen>15000:raise ValueError('飞船组件过多，无法安全定位')
            tag=self.names[self.node(node)[1]]
            if tag=='component':
                attrs=self.attrs(node)
                if node!=ship and (attrs.get('class','').startswith('ship_') or attrs.get('owner') not in (None,'player')):continue
                result.append(node)
            stack.extend(n for n,t in self.db.execute('SELECT id,tag FROM nodes WHERE parent=?',(node,))
                         if self.names[t] in ('connections','connection','component'))
        return result

    def equipment_definition(self,macro):
        model=self.game.model(macro)
        if model is None:return None
        ref=model.find('component');component=self.game.component(ref.get('ref')) if ref is not None else None
        connections=component.findall('connections/connection') if component is not None else []
        tags=set()
        for connection in connections:
            if 'component' in connection.get('tags','').split():tags.update(connection.get('tags','').split())
        return {'class':model.get('class'),'tags':sorted(tags),'connectionNames':[c.get('name','').lower() for c in connections if 'component' in c.get('tags','').split()]}

    @lru_cache(maxsize=1)
    def equipment_catalogue(self):
        result=[]
        for wid,ware in self.game.wares.items():
            if ware.get('group') not in ('engines','shields','weapons','turrets'):continue
            if set(ware.get('tags','').split())&{'deprecated','missiononly'}:continue
            macro=self.game.macro_for_ware(wid)
            spec=self.equipment_definition(macro) if macro else None
            if spec and spec['class'] in EQUIPMENT_CLASSES:result.append({'macro':macro,'name':ware['name'],**spec})
        return result

    def ship_service_data(self,request):
        ship=int(request.get('ship') or self.current or 0)
        rows=[]
        for node in self.ship_components(ship):
            attrs=self.attrs(node);macro=attrs.get('macro','');spec=self.equipment_definition(macro)
            hull=self.first(node,'hull');maximum=self.game.properties(macro,'hull').get('max')
            maxhull=float(maximum) if maximum is not None else None
            if node==ship:
                for mod in self.installed_mods().values():
                    if mod['ship']==ship and mod['category']=='ship' and 'maxhull' in self.attrs(mod['id']) and maxhull is not None:maxhull*=float(self.attrs(mod['id'])['maxhull'])
            cls=attrs.get('class','')
            if node!=ship and cls not in EQUIPMENT_CLASSES:continue
            rows.append({'id':node,'name':self.ship_description(ship) if node==ship else self.game.model_name(macro),
                'class':cls,'macro':macro,'connection':attrs.get('connection',''),'hullNode':hull,
                'hull':float(self.attrs(hull).get('value',maxhull)) if maxhull is not None else None,
                'maxHull':maxhull,'editableHull':maxhull is not None and math.isfinite(maxhull) and maxhull>0 and len(self.children(node,'hull'))<=1,
                'refittable':cls in EQUIPMENT_CLASSES and spec is not None,
                'definition':spec})
        return {'ship':ship,'rows':rows,'catalogue':self.equipment_catalogue()}

    @lru_cache(maxsize=1)
    def ammo_catalogue(self):
        result=[]
        for wid,ware in self.game.wares.items():
            group=AMMO_GROUPS.get(ware.get('group'))
            if ware.get('transport')=='equipment' and set(ware.get('tags','').split())&{'satellite','resourceprobe','navbeacon','lasertower','mine'}:group='deployable'
            if not group or set(ware.get('tags','').split())&{'deprecated','missiononly','module'}:continue
            macro=self.game.macro_for_ware(wid)
            if macro:result.append({'id':macro,'ware':wid,'name':ware['name'],'group':group})
        return result

    def ammo_data(self,request):
        ship=int(request.get('ship') or self.current or 0)
        components=self.ship_components(ship)
        containers=self.children(ship,'ammunition')
        container=containers[0] if len(containers)==1 else None
        available=self.children(container,'available')
        parent=available[0] if len(available)==1 else None
        capacities={k:0 for k in ('missile','countermeasure','deployable','unit')}
        for component in components:
            attrs=self.attrs(component)
            if component==ship or attrs.get('class') in ('weapon','turret'):
                storage=self.game.properties(attrs.get('macro',''),'storage')
                for group in capacities:capacities[group]+=int(storage.get(group,0))
        for mod in self.installed_mods().values():
            if mod['ship']==ship and mod['category']=='ship':
                for group in capacities:capacities[group]+=int(float(self.attrs(mod['id']).get(group+'capacity',0)))
        catalog={r['id']:r for r in self.ammo_catalogue()};items=[];seen=set();duplicate=False
        for node in self.children(parent,'item'):
            attrs=self.attrs(node);macro=attrs.get('macro','');duplicate|=macro in seen;seen.add(macro)
            definition=catalog.get(macro)
            model=self.game.model(macro)
            cls=model.get('class','') if model is not None else ''
            group=definition['group'] if definition else 'missile' if cls=='missile' else 'countermeasure' if cls=='countermeasure' else None
            items.append({'id':macro,'node':node,'name':self.game.model_name(macro),'amount':int(attrs.get('amount',0)),
                          'group':group,'editable':bool(group and self.leaf(node))})
        launched=self.first(container,'launched');unavailable=self.first(container,'unavailable')
        reserved={k:0 for k in capacities}
        unknownReserved=False
        for records in (launched,unavailable):
            for node in self.children(records,'item'):
                attrs=self.attrs(node);spec=catalog.get(attrs.get('macro'))
                if not spec:unknownReserved=True
                else:reserved[spec['group']]+=int(attrs.get('amount',0))
        known=bool(self.game.model(self.ships[ship].get('macro','')) is not None)
        return {'ship':ship,'container':container,'available':parent,'items':items,'catalogue':list(catalog.values()),
                'capacity':capacities,'reserved':reserved,'editable':known and len(containers)<=1 and len(available)<=1 and not duplicate and not unknownReserved and all(r['editable'] for r in items),
                'reason':'缺少游戏型号、重复弹药记录或存在无法识别的弹药 / 已部署物' if not known or duplicate or unknownReserved or not all(r['editable'] for r in items) or len(containers)>1 or len(available)>1 else ''}

    def crew_roster(self,request):
        ship=int(request.get('ship') or self.current or 0)
        if ship not in self.ships:raise ValueError('请选择玩家飞船')
        cap=self.game.properties(self.ships[ship].get('macro',''),'people').get('capacity')
        parents=self.children(ship,'people');parent=parents[0] if len(parents)==1 else None
        rows=[{'id':n,'role':self.attrs(n).get('role',''),'name':self.crew.get(n,{}).get('name','船员'),
               'macro':self.attrs(n).get('macro',''),'skills':self.crew.get(n,{}).get('skills',{}),
               'editable':not set(self.attrs(n).get('flags','').split('|'))&{'intransit','temporary'}}
              for n in self.children(parent,'person')]
        officers=[r for r in self.crew.values() if r['asset']==ship and not r['anonymous']]
        return {'ship':ship,'parent':parent,'capacity':int(cap) if cap is not None else None,'officers':len(officers),
                'rows':rows,'editable':cap is not None and len(parents)<=1,
                'roles':[{'id':'service','name':'勤务船员'},{'id':'marine','name':'陆战队员'}]}

    @lru_cache(maxsize=1)
    def galaxy_sectors(self):
        result=[]
        for (node,) in self.db.execute('SELECT n.id FROM nodes n JOIN labels l ON l.node=n.id WHERE n.tag=? AND l.label LIKE ?',
                                     (self.tags.get('component',-1),'%class=sector%')):
            attrs=self.attrs(node)
            if attrs.get('class')!='sector':continue
            x=z=0.;hasPosition=False;n=node
            while n:
                if self.names[self.node(n)[1]]=='component':
                    offset=self.first(n,'offset');position=self.first(offset,'position')
                    if position:
                        pos=self.attrs(position);x+=float(pos.get('x',0));z+=float(pos.get('z',0));hasPosition=True
                    elif self.attrs(offset).get('default')=='1':
                        parent=self.node(n)[0]
                        while parent and self.names[self.node(parent)[1]]!='component':parent=self.node(parent)[0]
                        parentMacro=self.attrs(parent).get('macro','').lower() if parent else ''
                        pos=self.game.map_positions().get((parentMacro,self.attrs(n).get('macro','').lower()))
                        if pos:x+=pos['x'];z+=pos['z'];hasPosition=True
                n=self.node(n)[0]
            result.append({'id':node,'ref':attrs.get('id',''),'macro':attrs.get('macro',''),
                           'name':self.game.sectors.get(attrs.get('macro','').lower(),attrs.get('macro','')),
                           'known':attrs.get('known')=='1','owner':attrs.get('owner',''),
                           'source':self.game.sector_source(attrs.get('macro','')),
                           'x':x,'z':z,'positionKnown':hasPosition})
        return result

    def map_data(self,request):
        sectors=self.galaxy_sectors();selected=int(request.get('sector') or (sectors[0]['id'] if sectors else 0))
        sector=next((s for s in sectors if s['id']==selected),None)
        discovered=self.first(self.player,'discovered')
        entries=[n for n in self.children(discovered,'sector') if sector and self.attrs(n).get('id')==sector['ref']]
        tree=self.first(entries[0],'quadtree') if len(entries)==1 else None
        return {'sectors':sectors,'selected':selected,'tree':tree,'revealAvailable':bool(tree),
                'objects':self.sector_objects(selected,int(request.get('page',0))) if sector else {'rows':[],'total':0}}

    @lru_cache(maxsize=128)
    def sector_objects(self,sector,page=0):
        # Index cursor walks only this sector; materialize at most one UI page.
        sql='WITH RECURSIVE branch(id) AS (SELECT ? UNION ALL SELECT n.id FROM nodes n JOIN branch b ON n.parent=b.id) SELECT n.id FROM branch b JOIN nodes n ON n.id=b.id WHERE n.tag=?'
        rows=[];total=0
        for (node,) in self.db.execute(sql,(sector,self.tags.get('component',-1))):
            attrs=self.attrs(node)
            if attrs.get('class') not in ('station','gate','highwaygate'):continue
            if page*100<=total<(page+1)*100:
                rows.append({'id':node,'name':attrs.get('name') or self.game.model_name(attrs.get('macro','')),
                             'class':attrs.get('class'),'known':attrs.get('known')=='1'})
            total+=1
        return {'rows':rows,'total':total,'page':page}

    @lru_cache(maxsize=1)
    def encyclopedia_records(self):
        parent=self.first(self.player,'known');groups=[];rows=[]
        for container in self.children(parent,'entries'):
            group=self.attrs(container).get('type','other');groups.append(group)
            for node in self.children(container,'entry'):
                attrs=self.attrs(node);identity=attrs.get('id','')
                rows.append({'id':node,'identity':identity,'group':group,'name':self.game.model_name(identity) if identity in self.game.macro_paths else self.game.name(identity),'known':True})
        # Candidate keys come from local defaults identification categories.
        saved={(r['group'],r['identity']) for r in rows}
        for wid,ware in self.game.wares.items():
            if set(ware.get('tags','').split())&{'deprecated','hidden','missiononly'}:continue
            macro=self.game.macro_for_ware(wid)
            group=identity=None
            if macro:
                group=self.game.properties(macro,'identification').get('type');identity=macro
            if not group:
                group='researchables' if ware.get('transport')=='research' else 'paintmods' if 'paintmod' in ware.get('tags','').split() else 'equipmentmods' if 'equipmentmod' in ware.get('tags','').split() else 'inventory_wares' if ware.get('transport')=='inventory' else 'wares' if self.game.cargo_ware(ware) else None
                identity=wid
            if group and (group,identity) not in saved:
                rows.append({'id':identity,'identity':identity,'group':group,'name':ware['name'],'known':False});saved.add((group,identity));groups.append(group)
        return parent,groups,rows

    def encyclopedia_data(self,request):
        parent,groups,rows=self.encyclopedia_records()
        query=str(request.get('search','')).lower();group=request.get('group')
        status=request.get('status','all')
        if status not in ('all','unknown','known'):raise ValueError('无效的百科状态筛选')
        rows=[r for r in rows if (not group or r['group']==group) and query in (r['name']+' '+r['identity']).lower()
              and (status=='all' or r['known']==(status=='known'))]
        rows.sort(key=lambda r:(r['group'],r['name'],str(r['id'])));page=max(0,int(request.get('page',0)))
        return {'rows':rows[page*100:(page+1)*100],'total':len(rows),'page':page,'groups':sorted(set(groups)),'parent':parent}

    def station_settings(self,request):
        station=int(request.get('station') or 0)
        if station not in self.station_accounts:raise ValueError('请选择玩家空间站')
        trade=self.first(station,'trade');rules=self.first(station,'traderules');prices=self.first(trade,'prices')
        reference=self.first(prices,'reference')
        rows=[];referenceRows=[]
        for node in self.children(prices,'ware'):
            attrs=self.attrs(node);wid=attrs.get('ware','');ware=self.game.wares.get(wid,{})
            rows.append({'id':node,'ware':wid,'name':self.game.name(wid),'buy':attrs.get('buy'),'sell':attrs.get('sell'),'priceRange':ware.get('price',{})})
        for node in self.children(reference,'ware'):
            attrs=self.attrs(node);referenceRows.append({'id':node,'ware':attrs.get('ware'),'name':self.game.name(attrs.get('ware')),'buy':attrs.get('buy'),'sell':attrs.get('sell')})
        ruleRows=[]
        for node in self.children(self.first(rules,'wares'),'ware'):
            attrs=self.attrs(node);ruleRows.append({'id':node,'ware':attrs.get('ware'),'name':self.game.name(attrs.get('ware')),'settings':{k:v for k,v in attrs.items() if k in ('buy','sell','supplies')}})
        gameRoot=self.children(0,'savegame')[0];ruleCatalog=[]
        for node in self.children(self.first(gameRoot,'traderules'),'traderule'):
            attrs=self.attrs(node)
            if attrs.get('owner')=='player':ruleCatalog.append({'id':attrs.get('id'),'name':attrs.get('name',''),'allow':attrs.get('allow'),'factions':attrs.get('factions','')})
        return {'station':station,'trade':trade,'rows':rows,'referenceRows':referenceRows,'ruleRows':ruleRows,'rules':ruleCatalog,'ruleContainer':rules,
                'restrictions':self.attrs(self.first(trade,'restrictions')).get('factions',''),
                'allocations':self.allocation_records(station)}

    def allocation_records(self,station):
        rows=[]
        # Only an explicitly persisted allocation can be edited; never infer it
        # from live cargo or historical economylog amounts.
        for storage in self.station_storages(station)[0]:
            for item in storage['items']:
                attrs=self.attrs(item['node'])
                for key in ('max','capacity'):
                    if key in attrs:rows.append({'id':item['node'],'ware':item['id'],'name':item['name'],'key':key,'amount':int(attrs[key]),'storage':storage['id'],'capacity':storage['capacity'],'volume':item['volume']})
        return rows

    def plan_expansion(self,plan,commands):
        ammo={};encyclopedia={};rosters={}
        for c in commands:
            kind=c['kind']
            if kind=='ammunition':ammo.setdefault(int(c['ship']),{})[str(c['id'])]=whole(c['value'])
            elif kind=='crew_role':
                node=whole(c['id'],1,2**63-1);person=self.crew.get(node);role=str(c['value'])
                if not person or not person['anonymous'] or role not in ('service','marine') or set(self.attrs(node).get('flags','').split('|'))&{'temporary','intransit'}:raise ValueError('只能调整现有非临时匿名船员的勤务 / 陆战队岗位')
                plan.set(node,role=role);plan.summaries.append(f'{person["name"]} 岗位 → {role}')
            elif kind=='crew_count':rosters.setdefault(int(c['id']),{})[str(c['storage'])]=whole(c['value'],0,10000)
            elif kind=='repair':
                ship=int(c['ship']);row=next((r for r in self.ship_service_data({'ship':ship})['rows'] if r['id']==int(c['id'])),None)
                if not row or not row['editableHull']:raise ValueError('无法确认船体容量')
                percent=float(c['value'])
                if not math.isfinite(percent) or not 0<percent<=100:raise ValueError('船体比例必须大于 0 且不超过 100%')
                maximum=row['maxHull']
                if row['id']==ship:
                    maximum=float(self.game.properties(self.ships[ship].get('macro',''),'hull')['max'])
                    for mod in self.installed_mods().values():
                        if mod['ship']==ship and mod['category']=='ship':
                            attrs={**self.attrs(mod['id']),**plan.attrs.get(mod['id'],{})}
                            for key in plan.unset_attrs.get(mod['id'],()):attrs.pop(key,None)
                            maximum*=float(attrs.get('maxhull',1))
                amount=format(maximum*percent/100,'.12g')
                if row['hullNode']:plan.set(row['hullNode'],value=amount)
                else:plan.add(row['id'],element('hull',{'value':amount}))
                plan.summaries.append(f'{row["name"]} 船体 → {percent:g}%')
            elif kind=='refit':
                ship=int(c['ship']);node=int(c['id']);target=str(c['value'])
                row=next((r for r in self.ship_service_data({'ship':ship})['rows'] if r['id']==node),None)
                spec=self.equipment_definition(target)
                if not row or not row['refittable'] or not spec or spec['class']!=row['class']:raise ValueError('只能替换同类别的已安装装备')
                if c.get('experimental') is not True:
                    old=set(row['definition']['tags']);new=set(spec['tags'])
                    if not old or old!=new or row['connection'].lower() not in spec['connectionNames']:raise ValueError('装备连接标签或连接名称不兼容；如需研究特殊组合，请明确启用实验模式')
                plan.set(node,macro=target)
                plan.summaries.append(f'{row["name"]} → {self.game.model_name(target)}'+('（实验换装）' if c.get('experimental') is True else ''))
            elif kind=='map_known':
                node=int(c['id']);sectors=self.galaxy_sectors();sector=next((s for s in sectors if s['id']==node),None)
                allowed=bool(sector)
                if not allowed:
                    attrs=self.attrs(node)
                    if self.names[self.node(node)[1]]=='component' and attrs.get('class') in ('station','gate','highwaygate'):
                        ancestor=self.node(node)[0];sectorIds={s['id'] for s in sectors}
                        while ancestor:
                            if ancestor in sectorIds:allowed=True;break
                            ancestor=self.node(ancestor)[0]
                if not allowed:raise ValueError('不是地图中的星区、空间站或星门')
                attrs=self.attrs(node);known=attrs.get('knownto','').split()
                if 'player' not in known:known.append('player')
                plan.set(node,known=1,knownto=' '.join(known));plan.summaries.append('发现地图对象：'+str(node))
            elif kind=='map_reveal':
                data=self.map_data({'sector':c['id']});tree=data['tree']
                if not tree:raise ValueError('此星区尚无可确认的探索树，请在游戏中进入一次再编辑迷雾')
                stack=self.children(tree,'node');seen=0
                while stack:
                    node=stack.pop();seen+=1
                    if seen>100000:raise ValueError('探索树过大')
                    children=self.children(node,'node')
                    if children:stack.extend(children)
                    else:
                        attrs=self.attrs(node)
                        if set(attrs)-{'state'} or attrs.get('state') not in (None,'0','1'):raise ValueError('未知探索树格式')
                        plan.set(node,state=1)
                plan.summaries.append('揭示已保存的星区探索区域：'+str(c['id']))
            elif kind=='encyclopedia':encyclopedia.setdefault(str(c['storage']),set()).add(str(c['id']))
            elif kind=='station_price':
                data=self.station_settings({'station':c['station']});row=next((r for r in data['rows'] if r['id']==int(c['id'])),None);key=str(c['storage'])
                if not row or key not in ('buy','sell') or row[key] is None:raise ValueError('未找到对应已保存价格')
                value=whole(c['value'],0,2147483647);limits=row['priceRange']
                if value and ('min' not in limits or 'max' not in limits or not limits['min']<=value<=limits['max']):raise ValueError('价格超出本机游戏物资范围；0 保留原有自动标记')
                plan.set(row['id'],**{key:value});plan.summaries.append(f'{row["name"]} / {key} 参考价格 → {value}')
            elif kind=='station_rule':
                data=self.station_settings({'station':c['station']});key=str(c['storage']);value=whole(c['value'],-1,2147483647)
                if value not in (-1,0) and str(value) not in {r['id'] for r in data['rules']}:raise ValueError('交易规则不存在')
                row=next((r for r in data['ruleRows'] if r['id']==int(c['id'])),None)
                if not row or key not in row['settings']:raise ValueError('未找到物资的已保存交易规则')
                plan.set(row['id'],**{key:value});plan.summaries.append(f'{row["name"]} / {key} 交易规则 → {value}')
            elif kind=='station_restriction':
                station=int(c['id']);data=self.station_settings({'station':station});value=str(c['value']).split()
                if any(f not in self.factions for f in value):raise ValueError('未知交易限制势力')
                node=self.first(data['trade'],'restrictions')
                if node:plan.set(node,factions=' '.join(dict.fromkeys(value)))
                elif data['trade']:plan.add(data['trade'],element('restrictions',{'factions':' '.join(dict.fromkeys(value))}))
                else:plan.add(station,element('trade',children=element('restrictions',{'factions':' '.join(dict.fromkeys(value))})))
                plan.summaries.append('空间站交易限制势力 → '+' '.join(value))
            elif kind=='station_allocation':
                data=self.station_settings({'station':c['station']});row=next((r for r in data['allocations'] if r['id']==int(c['id']) and r['key']==c['storage']),None)
                if not row or row['capacity'] is None or row['volume'] is None:raise ValueError('无可确认的仓储配额记录')
                value=whole(c['value']);total=sum((value if r['id']==row['id'] and r['key']==row['key'] else int(plan.attrs.get(r['id'],{}).get(r['key'],r['amount'])))*r['volume'] for r in data['allocations'] if r['storage']==row['storage'])
                if total>row['capacity']:raise ValueError('手动分配超出实体货仓容量')
                plan.set(row['id'],**{row['key']:value});plan.summaries.append(f'{row["name"]} 已保存仓储配额 → {value}')
            elif kind=='research_stock':
                spec=self.game.research.get(str(c['id']));hqs=self.headquarters()
                if not spec or spec['hidden'] or len(hqs)!=1:raise ValueError('未找到科研或唯一总部')
                data=self.station_resources({'station':hqs[0]});current={r['id']:r['amount'] for r in data['ordinaryWares']}
                updates={wid:max(amount,current.get(wid,0)) for wid,amount in spec['resources'].items()}
                self.plan_station_stock(plan,hqs[0],False,updates)
            elif kind=='research_time':
                node=int(c['id']);record=next((r for r in self.research_tasks() if r['id']==node),None)
                if not record or not record['editable']:raise ValueError('不是可编辑的总部科研计时')
                remaining=float(c['value'])
                if not math.isfinite(remaining) or not 0<=remaining<=record['duration']:raise ValueError('剩余时间超出科研周期')
                plan.set(node,**{record['key']:format(record['now']+remaining,'.12g')});plan.summaries.append(f'{record["name"]} 剩余时间 → {remaining:g} 秒')
            else:raise ValueError('未知扩展操作')
        for ship,updates in ammo.items():self.plan_ammo(plan,ship,updates)
        for ship,updates in rosters.items():self.plan_roster(plan,ship,updates)
        if encyclopedia:self.plan_encyclopedia(plan,encyclopedia)

    def plan_ammo(self,plan,ship,updates):
        data=self.ammo_data({'ship':ship})
        for mod in self.installed_mods().values():
            if mod['ship']==ship and mod['category']=='ship':
                for group in data['capacity']:
                    key=group+'capacity';old=int(float(self.attrs(mod['id']).get(key,0)))
                    value=0 if key in plan.unset_attrs.get(mod['id'],set()) else int(float(plan.attrs.get(mod['id'],{}).get(key,self.attrs(mod['id']).get(key,0))))
                    data['capacity'][group]+=value-old
        if not data['editable']:raise ValueError(data['reason'] or '弹药结构不唯一')
        current={r['id']:r for r in data['items']};catalog={r['id']:r for r in data['catalogue']}
        total=dict(data['reserved']);baseline=dict(total)
        for row in current.values():
            if row['group']:baseline[row['group']]+=row['amount']
        for macro in set(current)|set(updates):
            row=current.get(macro) or catalog.get(macro)
            if not row or not row.get('group'):raise ValueError('未知弹药 / 部署物')
            amount=updates.get(macro,current.get(macro,{}).get('amount',0));total[row['group']]+=amount
        for group,amount in total.items():
            if amount>data['capacity'][group] and amount>baseline[group]:raise ValueError('超过弹药 / 部署物容量：'+group)
        additions=[]
        for macro,amount in updates.items():
            row=current.get(macro)
            if row:
                if not row['editable']:raise ValueError('未知或非叶弹药记录')
                if amount:plan.set(row['node'],amount=amount)
                else:plan.remove_leaf(row['node'])
            elif amount:
                if macro not in catalog:raise ValueError('此项目不能作为弹药或部署物加入')
                additions.append(element('item',{'macro':macro,'amount':amount}))
            plan.summaries.append(self.ship_description(ship)+' / '+self.game.model_name(macro)+' → '+str(amount))
        if additions:
            xml=''.join(additions)
            if data['available']:plan.add(data['available'],xml)
            elif data['container']:plan.add(data['container'],element('available',children=xml))
            else:plan.add(ship,element('ammunition',children=element('available',children=xml)))

    def plan_roster(self,plan,ship,updates):
        data=self.crew_roster({'ship':ship})
        if not data['editable'] or any(role not in ('service','marine') for role in updates):raise ValueError('船员容量或岗位无法确认')
        rows=[{**r,'role':plan.attrs.get(r['id'],{}).get('role',r['role'])} for r in data['rows']];current={role:[r for r in rows if r['role']==role] for role in ('service','marine')}
        desired={role:updates.get(role,len(current[role])) for role in current}
        other=len(rows)-sum(len(r) for r in current.values())
        if sum(desired.values())+other+data['officers']>data['capacity']:raise ValueError('超过飞船船员容量（含具名人员和临时人员）')
        additions=[]
        for role,amount in updates.items():
            existing=current[role];difference=amount-len(existing)
            if difference<0:
                removable=sorted((r for r in existing if r['editable'] and r['id'] not in plan.attrs),key=lambda r:(sum(r['skills'].values()),r['id']))
                if len(removable)<-difference:raise ValueError('剩余人员为临时或同时修改岗位的人员，无法满足目标人数')
                for person in removable[:-difference]:plan.remove_branch(person['id'],{'person','npcseed','skills','quantity','quality'})
            template=next((r for r in existing if r['editable'] and r['macro']),None) or next((r for r in rows if r['editable'] and r['macro']),None)
            if difference>0 and not template:raise ValueError('没有可复用的本船人员型号，不能猜测新船员种族')
            for _ in range(difference):
                additions.append(element('person',{'macro':template['macro'],'role':role},children=element('npcseed',{'seed':secrets.randbits(63)})+element('skills',{k:0 for k in ('piloting','management','engineering','boarding','morale')})))
            plan.summaries.append(self.ship_description(ship)+' / '+role+' 人数 → '+str(amount))
        if additions:
            xml=''.join(additions);plan.add(data['parent'] or ship,xml if data['parent'] else element('people',children=xml))

    def plan_encyclopedia(self,plan,updates):
        data=self.encyclopedia_data({'page':0});catalog=set()
        for group in updates:
            page=0
            while True:
                portion=self.encyclopedia_data({'group':group,'page':page});catalog.update((r['group'],r['identity']) for r in portion['rows'])
                if (page+1)*100>=portion['total']:break
                page+=1
        parent=data['parent'];containers=self.children(self.player,'known')
        if len(containers)>1:raise ValueError('百科容器不唯一')
        addGroups=[]
        for group,ids in updates.items():
            matches=[n for n in self.children(parent,'entries') if self.attrs(n).get('type','other')==group]
            if len(matches)>1:raise ValueError('百科分类重复')
            target=matches[0] if matches else None;saved={self.attrs(n).get('id') for n in self.children(target,'entry')}
            if any((group,identity) not in catalog for identity in ids):raise ValueError('不是本机可确认的百科条目')
            xml=''.join(element('entry',{'id':identity,'read':0}) for identity in sorted(ids-saved))
            if not xml:continue
            if target:plan.add(target,xml)
            else:addGroups.append(element('entries',{} if group=='other' else {'type':group},children=xml))
        if addGroups:
            xml=''.join(addGroups);plan.add(parent or self.player,xml if parent else element('known',children=xml))
        plan.summaries.append('解锁百科条目：'+str(sum(len(ids) for ids in updates.values())))

    def research_tasks(self):
        rows=[];root=self.children(0,'savegame')[0];now=float(self.attrs(self.first(self.first(root,'info'),'game')).get('time',0))
        for hq in self.headquarters():
            stack=[self.first(hq,'production'),self.first(hq,'buildtasks')];visited=0
            while stack:
                node=stack.pop()
                if not node:continue
                visited+=1
                if visited>10000:raise ValueError('总部任务结构过大')
                attrs=self.attrs(node);ware=attrs.get('ware') or attrs.get('macro')
                if ware in self.game.research and 'endtime' in attrs:
                    duration=self.game.research[ware]['time']
                    rows.append({'id':node,'ware':ware,'name':self.game.name(ware),'key':'endtime','now':now,'duration':duration,
                                 'remaining':max(0,float(attrs['endtime'])-now),'editable':now>0 and duration>0})
                stack.extend(n for n, in self.db.execute('SELECT id FROM nodes WHERE parent=?',(node,)))
        return rows

    def expansion_sources(self,c):
        kind=c['kind'];nodes=[]
        if kind=='ammunition':
            data=self.ammo_data({'ship':c['ship']});row=next((r for r in data['items'] if r['id']==c['id']),None)
            nodes=[row['node'] if row else data['available'] or data['container'] or int(c['ship'])]
        elif kind=='repair':nodes=[self.first(int(c['id']),'hull') or int(c['id'])]
        elif kind in ('refit','crew_role','research_time'):nodes=[int(c['id'])]
        elif kind=='crew_count':nodes=[self.first(int(c['id']),'people') or int(c['id'])]
        elif kind=='map_known':nodes=[int(c['id'])]
        elif kind=='map_reveal':nodes=[self.map_data({'sector':c['id']})['tree'] or int(c['id'])]
        elif kind=='encyclopedia':
            known=self.first(self.player,'known')
            groups=[n for n in self.children(known,'entries') if self.attrs(n).get('type')==c.get('storage')]
            records=[n for parent in groups for n in self.children(parent,'entry') if self.attrs(n).get('id')==c['id']]
            nodes=records or groups or [known or self.player]
        elif kind.startswith('station_'):nodes=[int(c['id'])] if kind not in ('station_restriction',) else [self.first(int(c['id']),'trade') or int(c['id'])]
        elif kind=='research_stock':nodes=self.headquarters()
        for node in nodes:
            if not self.db.execute('SELECT 1 FROM nodes WHERE id=?',(node,)).fetchone():raise ValueError('原始节点不存在')
        if not nodes:raise ValueError('无原始节点')
        return {'nodes':[{'id':n,'label':self.names[self.node(n)[1]]+' #'+str(n)} for n in nodes]}
