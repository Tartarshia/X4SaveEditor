"""Validated gameplay operations over the disk index, with bounded UI pages."""
from contextlib import closing
from functools import lru_cache
import math
from pathlib import Path
import sqlite3
import core
from edits import Plan, element
from game_data import GameData, DEFAULT_GAME
import shortcuts

SKILLS = ('piloting', 'management', 'engineering', 'boarding', 'morale')


def integer(value, low, high):
    if isinstance(value, bool) or str(value).strip() != str(int(value)):
        raise ValueError('请输入整数')
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f'数值必须在 {low} 至 {high} 之间')
    return value


class Editor:
    def __init__(self, folder, game_path=None, progress=lambda m: None, catalog=None):
        self.folder = Path(folder)
        self.db = sqlite3.connect((self.folder / 'index.db').resolve().as_uri() + '?mode=ro', uri=True)
        self.xml = (self.folder / 'source.xml').open('rb')
        self.tags = dict(self.db.execute('SELECT name,id FROM tags'))
        self.names = {v:k for k,v in self.tags.items()}
        sidecar = shortcuts.ensure_index(folder, progress)
        with closing(sqlite3.connect(sidecar)) as db:
            self.members = {}
            for category,node in db.execute('SELECT category,node FROM members'):
                self.members.setdefault(category, []).append(node)
        players = self.members.get('player', [])
        if len(players) != 1:
            raise ValueError('无法唯一识别玩家角色，仍可使用高级浏览')
        self.player = players[0]
        self.ships = {n:self.attrs(n) for n in self.members.get('ships', [])}
        self.assets = dict(self.ships)
        self.assets.update({n:self.attrs(n) for n in self.members.get('stations', [])})
        self.current = next((n for n,a in self.ships.items() if a.get('id') == self.attrs(self.player).get('lastcontrolled')), None)
        root = self.children(0, 'savegame')[0]
        info = self.first(root, 'info')
        patches = self.first(info, 'patches')
        extensions = [self.attrs(n).get('extension','') for n in self.children(patches,'patch')]
        progress('读取本机游戏名称、货物和蓝图目录…')
        self.game = catalog or GameData(game_path or DEFAULT_GAME, extensions)
        self.warnings = list(self.game.warnings)
        version = self.attrs(self.first(info,'game')).get('version','')
        if version and self.game.version and version != self.game.version:
            self.warnings.append(f'存档版本 {version}，游戏资源版本 {self.game.version}；新增蓝图/货物请使用当前安装版本加载验证。')
        self.factions = {}
        for universe in self.children(root,'universe'):
            for parent in self.children(universe,'factions'):
                self.factions.update({self.attrs(n).get('id'):n for n in self.children(parent,'faction')})
        self.owned = {self.attrs(n).get('ware') for n in self.children(self.first(self.player,'blueprints'),'blueprint')}
        self.station_accounts = {}
        money_accounts = {self.attrs(n).get('id') for n in self.members.get('money',[]) if self.names[self.node(n)[1]] == 'account'}
        def account_info(component):
            accounts = self.children(component,'account')
            if len(accounts) != 1:
                return {'node':None,'amount':None,'min':None,'max':None,'editable':False,'reason':'账户数量不唯一'}
            account = accounts[0]
            attrs = self.attrs(account)
            ref = attrs.get('id')
            matches = self.db.execute('SELECT l.node FROM labels l JOIN nodes n ON n.id=l.node WHERE l.ref=? AND n.tag=?',(ref,self.tags.get('account',-1))).fetchall() if ref else []
            reason = ('账户缺少 ID' if not ref else '账户 ID 与玩家资金共用' if ref in money_accounts else '账户 ID 被其他记录共用' if len(matches) != 1 else '')
            return {'node':account,'amount':int(attrs.get('amount',0)),
                    'min':int(attrs['min']) if 'min' in attrs else None,
                    'max':int(attrs['max']) if 'max' in attrs else None,
                    'editable':not reason,'reason':reason}
        build_by_zone = {}
        for storage in self.members.get('buildstorage',[]):
            zone = self.zone(storage)
            if zone is not None:
                build_by_zone.setdefault(zone,[]).append(storage)
        stations_by_zone = {}
        for station in self.members.get('stations', []):
            zone = self.zone(station)
            if zone is not None:
                stations_by_zone.setdefault(zone,[]).append(station)
        for station in self.members.get('stations', []):
            account = account_info(station)
            zone = self.zone(station)
            builds = build_by_zone.get(zone,[]) if zone is not None else []
            if len(builds) == 1 and len(stations_by_zone.get(zone,[])) == 1:
                account['construction'] = {'storage':builds[0],**account_info(builds[0])}
            else:
                account['construction'] = {'storage':None,'node':None,'amount':None,'min':None,'max':None,
                                           'editable':False,'reason':'未找到唯一关联的建造仓储'}
            self.station_accounts[station] = account
        self.crew = {}
        progress('整理玩家舰船和船员…')
        # Anonymous crew are direct people/person entries of player assets.
        for asset in self.assets:
            for people in self.children(asset,'people'):
                for person in self.children(people,'person'):
                    self.add_crew(person, asset, anonymous=True)
        # Named NPCs, excluding computers and hostile NPCs aboard player ships.
        for n, in self.db.execute("SELECT n.id FROM nodes n JOIN labels l ON l.node=n.id WHERE n.tag=? AND l.label LIKE '%class=npc%' AND l.label LIKE '%owner=player%'", (self.tags.get('component',-1),)).fetchall():
            if self.attrs(n).get('class') == 'npc' and self.attrs(n).get('owner') == 'player':
                self.add_crew(n, self.asset(n), anonymous=False)

    def close(self):
        self.db.close()
        self.xml.close()
        self.node.cache_clear()
        self.attrs.cache_clear()
        self.asset.cache_clear()
        self.sector.cache_clear()
        self.zone.cache_clear()
        self.station_storages.cache_clear()

    @lru_cache(maxsize=50000)
    def zone(self,n):
        while n:
            parent,tag,_ = self.node(n)
            if tag == self.tags.get('component') and self.attrs(n).get('class') == 'zone':
                return n
            n = parent
        return None

    @lru_cache(maxsize=50000)
    def sector(self, n):
        # Physical ancestry includes docked ships, carriers, stations and zones.
        # Never use commander/homebase/order destinations as current location.
        while n:
            parent, tag, _ = self.node(n)
            if tag == self.tags.get('component'):
                attrs = self.attrs(n)
                if attrs.get('class') == 'sector':
                    macro = attrs.get('macro', '')
                    name = self.game.translate(attrs['name']) if attrs.get('name') else self.game.sectors.get(macro.lower(), macro or attrs.get('id') or f'星区 #{n}')
                    return {'id':str(n), 'name':name}
            n = parent
        return {'id':'unknown', 'name':'未知星区 / 未定位'}

    @lru_cache(maxsize=50000)
    def node(self,n):
        row = self.db.execute('SELECT parent,tag,offset FROM nodes WHERE id=?',(n,)).fetchone()
        if row is None:
            raise ValueError('节点不存在')
        return row

    @lru_cache(maxsize=30000)
    def attrs(self,n):
        return core.attributes(core.read_start_tag(self.xml,self.node(n)[2])) if n else {}

    def children(self,n,tag):
        if not n and n != 0:
            return []
        return [r[0] for r in self.db.execute('SELECT id FROM nodes INDEXED BY parent_nodes WHERE parent=? AND tag=? ORDER BY id',(n,self.tags.get(tag,-1)))]

    def first(self,n,tag):
        return next(iter(self.children(n,tag)),None)

    @lru_cache(maxsize=50000)
    def asset(self,n):
        while n:
            if n in self.assets:
                return n
            p,t,_ = self.node(n)
            if t == self.tags.get('component'):
                a = self.attrs(n)
                if a.get('class','').startswith('ship_') or a.get('class') == 'station':
                    return None
            n = p
        return None

    def asset_name(self,n):
        a = self.assets.get(n,{})
        if not a:
            return '未分配资产'
        return a['name'] if a.get('name','').strip() else self.game.model_name(a.get('macro',''))

    def add_crew(self,n,asset,anonymous):
        a = self.attrs(n)
        parent = n if anonymous else self.first(n,'traits')
        skill = self.first(parent,'skills')
        role = a.get('role','') if anonymous else self.attrs(self.first(n,'entity')).get('post','officer')
        roles = {'service':'勤务船员','marine':'陆战队员','aipilot':'船长 / 驾驶员','manager':'经理','officer':'人员'}
        self.crew[n] = {'id':n,'name':a.get('name') or roles.get(role,role) or '船员','role':roles.get(role,role),
                        'asset':asset,'ship':self.asset_name(asset),'sector':self.sector(n),'skills':{k:int(self.attrs(skill).get(k,0)) for k in SKILLS},
                        'skill_node':skill,'parent':parent,'anonymous':anonymous}

    def relation_rows(self):
        result = []
        for identity,n in self.factions.items():
            if identity == 'player':
                continue
            values = []
            locked = False
            for source,target in [('player',identity),(identity,'player')]:
                parent = self.first(self.factions.get(source),'relations')
                locked |= self.attrs(parent).get('locked') == '1'
                parts = [self.attrs(c) for t in ('relation','booster') for c in self.children(parent,t) if self.attrs(c).get('faction') == target]
                values.append(sum(float(a.get('relation',0)) for a in parts))
            result.append({'id':identity,'name':self.game.name(identity),'outgoing':values[0],'incoming':values[1],'locked':locked})
        return result

    def cargo(self,ship):
        if ship not in self.ships:
            raise ValueError('请选择玩家拥有的飞船')
        storages = []
        # Follow component connections only; stop at separately docked ships.
        stack = [ship]
        while stack:
            n = stack.pop()
            a = self.attrs(n)
            if n != ship and (a.get('class','').startswith('ship_') or a.get('class') in ('station','buildstorage')):
                continue
            if a.get('class') == 'storage':
                capacity = self.game.storage(a.get('macro',''))
                containers = self.children(n,'cargo')
                items = []
                for parent in containers:
                    for ware in self.children(parent,'ware'):
                        item = self.attrs(ware)
                        wid = item.get('ware','')
                        items.append({'node':ware,'id':wid,'name':self.game.name(wid),'amount':int(item.get('amount',0)),
                                      'volume':self.game.wares.get(wid,{}).get('volume')})
                storages.append({'id':n,'macro':a.get('macro'), 'cargo':containers[0] if len(containers)==1 else None,
                                 'ambiguous':len(containers)>1,'items':items,**(capacity or {'capacity':None,'types':[]})})
            for connections in self.children(n,'connections'):
                for connection in self.children(connections,'connection'):
                    stack.extend(self.children(connection,'component'))
        return storages

    def station_components(self, root):
        """Walk one station or build-storage component, excluding docked assets."""
        stack = [root]
        while stack:
            n = stack.pop()
            attrs = self.attrs(n)
            cls = attrs.get('class','')
            if n != root and (cls.startswith('ship_') or cls in ('station','buildstorage','npc')):
                continue
            yield n, attrs
            for connections in self.children(n,'connections'):
                for connection in self.children(connections,'connection'):
                    stack.extend(self.children(connection,'component'))

    @lru_cache(maxsize=100)
    def station_storages(self, root):
        storages = []
        productions = {}
        for n, attrs in self.station_components(root):
            cls = attrs.get('class')
            if cls == 'production':
                macro = attrs.get('macro','')
                productions[macro] = productions.get(macro,0) + 1
            if cls != 'storage':
                continue
            containers = self.children(n,'cargo')
            items = []
            for cargo in containers:
                for ware in self.children(cargo,'ware'):
                    item = self.attrs(ware)
                    wid = item.get('ware','')
                    items.append({'node':ware,'id':wid,'name':self.game.name(wid),'amount':int(item.get('amount',0)),
                                  'volume':self.game.wares.get(wid,{}).get('volume')})
            capacity = self.game.storage(attrs.get('macro',''))
            used = sum((w['volume'] or 0)*w['amount'] for w in items) if all(w['volume'] is not None for w in items) else None
            storages.append({'id':n,'macro':attrs.get('macro',''),'name':self.game.model_name(attrs.get('macro','')),
                             'cargo':containers[0] if len(containers)==1 else None,'ambiguous':len(containers)>1,
                             'items':items,'used':used,**(capacity or {'capacity':None,'types':[]})})
        storages.sort(key=lambda storage:storage['id'])
        return storages, productions

    def station_resources(self, request):
        stations = [{'id':n,'name':self.asset_name(n),'code':self.assets[n].get('code',''),'sector':self.sector(n)}
                    for n in self.station_accounts]
        stations.sort(key=lambda r:(r['sector']['name'],r['name'],r['id']))
        station = int(request.get('station') or (stations[0]['id'] if stations else 0))
        if station not in self.station_accounts:
            raise ValueError('请选择玩家空间站')
        ordinary, production = self.station_storages(station)
        construction = self.station_accounts[station]['construction']
        build_root = construction['storage']
        building, _ = self.station_storages(build_root) if build_root else ([],{})
        def indicators(root):
            result = []
            reserved = {}
            for n in self.children(self.first(self.first(root,'trade'),'reservations'),'reservation'):
                attrs = self.attrs(n)
                wid = attrs.get('ware','')
                if wid:
                    reserved[wid] = reserved.get(wid,0) + int(attrs.get('amount',0))
            for wid,amount in reserved.items():
                result.append({'kind':'交易预留','id':wid,'name':self.game.name(wid),'amount':amount})
            resources = self.first(self.first(root,'build'),'resources')
            for tag,label in (('shortage','记录的短缺'),('insufficient','记录的不足')):
                for section in self.children(resources,tag):
                    for n in self.children(section,'ware'):
                        attrs = self.attrs(n)
                        wid = attrs.get('ware','')
                        if wid:
                            result.append({'kind':label,'id':wid,'name':self.game.name(wid),'amount':int(attrs.get('amount',0))})
            return sorted(result,key=lambda r:(r['kind'],r['name'],r['id']))
        def summarize(storages):
            summary = {}
            for storage in storages:
                for item in storage['items']:
                    row = summary.setdefault(item['id'],{'id':item['id'],'name':item['name'],'amount':0,
                                                         'transport':self.game.wares.get(item['id'],{}).get('transport'),
                                                         'volume':item['volume'],'locations':0})
                    row['amount'] += item['amount']
                    row['locations'] += 1
            return sorted(summary.values(),key=lambda r:(r['name'],r['id']))
        return {'stations':stations,'station':station,'ordinary':ordinary,'building':building,
                'ordinaryWares':summarize(ordinary),'buildingWares':summarize(building),
                'ordinaryIndicators':indicators(station),'buildingIndicators':indicators(build_root) if build_root else [],
                'constructionReason':construction['reason'] if not build_root else '',
                'production':[{'macro':k,'name':self.game.model_name(k),'count':v} for k,v in sorted(production.items())],
                'wares':[{'id':k,'name':v['name'],'volume':v['volume'],'transport':v.get('transport')}
                         for k,v in self.game.wares.items() if v.get('transport') in ('container','solid','liquid') and v['volume']>0]}

    def plan_station_stock(self, plan, station, build, updates):
        if station not in self.station_accounts:
            raise ValueError('请选择玩家空间站')
        account = self.station_accounts[station]['construction']
        root = account['storage'] if build else station
        if not root:
            raise ValueError('未找到唯一关联的建造仓储')
        storages, _ = self.station_storages(root)
        if not storages or any(s['ambiguous'] or s['capacity'] is None or s['capacity']<=0 for s in storages):
            raise ValueError('无法确认空间站货仓结构或容量')
        amounts = []
        originals = []
        for storage in storages:
            original = {}
            for item in storage['items']:
                wid = item['id']
                ware = self.game.wares.get(wid)
                if wid in original or not ware or ware.get('transport') not in storage['types'] or ware['volume']<=0:
                    raise ValueError('货仓含重复或无法识别的物资记录')
                original[wid] = item
            originals.append(original)
            amounts.append({wid:item['amount'] for wid,item in original.items()})
        def used(index):
            return sum(self.game.wares[wid]['volume']*amount for wid,amount in amounts[index].items())
        for wid,target in updates.items():
            ware = self.game.wares.get(wid)
            if not ware or ware.get('transport') not in ('container','solid','liquid') or ware['volume']<=0:
                raise ValueError('不是本机已识别的可存储物资：' + wid)
        # Free space first so several edits are checked against their combined final state.
        for wid,target in updates.items():
            current = sum(values.get(wid,0) for values in amounts)
            to_remove = max(0,current-target)
            for values in amounts:
                removed = min(values.get(wid,0),to_remove)
                if removed:
                    values[wid] -= removed
                    to_remove -= removed
            if to_remove:
                raise ValueError('物资总量与存档记录不一致')
        for wid,target in updates.items():
            remaining = target - sum(values.get(wid,0) for values in amounts)
            ware = self.game.wares[wid]
            candidates = sorted(range(len(storages)),key=lambda i:(wid not in amounts[i],i))
            for i in candidates:
                if ware['transport'] not in storages[i]['types']:
                    continue
                free = max(0,int((storages[i]['capacity']-used(i)+1e-7)/ware['volume']))
                added = min(remaining,free)
                if added:
                    amounts[i][wid] = amounts[i].get(wid,0) + added
                    remaining -= added
                if not remaining:
                    break
            if remaining:
                raise ValueError(f'{self.game.name(wid)} 超出空间站可用货仓容量，仍差 {remaining:,} 单位')
        for i,storage in enumerate(storages):
            if used(i) > storage['capacity'] + 1e-6:
                raise ValueError('空间站货仓容量不足')
            additions = []
            for wid,amount in amounts[i].items():
                old = originals[i].get(wid)
                if old and amount != old['amount']:
                    if amount:plan.set(old['node'],amount=amount)
                    else:plan.remove_leaf(old['node'])
                elif not old and amount:
                    additions.append(element('ware',{'ware':wid,'amount':amount}))
            if additions:
                xml = ''.join(additions)
                plan.add(storage['cargo'] or storage['id'],xml if storage['cargo'] else element('cargo',children=xml))
        label = '建造仓储' if build else '空间站库存'
        for wid,target in updates.items():
            plan.summaries.append(f'{self.asset_name(station)} / {label} / {self.game.name(wid)} → {target:,}')

    def view(self, request):
        page = max(0,int(request.get('page',0)))
        query = str(request.get('search','')).lower()
        kind = request.get('kind','home')
        if kind == 'home':
            money = next((self.attrs(n).get('amount') for n in self.members.get('money',[]) if 'amount' in self.attrs(n)),None)
            if money is None:
                money = next((self.attrs(n).get('money') for n in self.members.get('money',[]) if 'money' in self.attrs(n)),None)
            ships = [{'id':n,'name':self.asset_name(n),'code':a.get('code',''),'sector':self.sector(n)} for n,a in self.ships.items()]
            sectors = {}
            for category, entries in [('ships',ships),('crew',self.crew.values())]:
                for row in entries:
                    region = row['sector']
                    sectors.setdefault(region['id'],{**region,'ships':0,'crew':0})[category] += 1
            return {'money':money,'current':self.current,'ships':ships,'sectors':sorted(sectors.values(),key=lambda s:(s['id']=='unknown',s['name'],s['id'])),
                    'stationCount':len(self.station_accounts),'crewCount':len(self.crew),'warnings':self.warnings,'gamePath':str(self.game.path)}
        if kind == 'station_money':
            rows = [{'id':n,'name':self.asset_name(n),'code':self.assets[n].get('code',''),
                     'sector':self.sector(n),**account} for n,account in self.station_accounts.items()]
            if request.get('sector'):
                rows = [r for r in rows if r['sector']['id'] == str(request['sector'])]
            rows = [r for r in rows if query in ' '.join((r['name'],r['code'],str(r['id']),r['sector']['name'])).lower()]
            rows.sort(key=lambda r:(r['sector']['name'],r['name'],r['id']))
            return {'rows':rows[page*100:(page+1)*100],'total':len(rows),'page':page,
                    'sectors':sorted({r['sector']['id']:r['sector'] for r in ({'sector':self.sector(n)} for n in self.station_accounts)}.values(),key=lambda s:s['name'])}
        if kind == 'station_resources':
            return self.station_resources(request)
        if kind == 'relations':
            rows = self.relation_rows()
            hidden = sum(r['id'].lower().startswith('visitor') for r in rows)
            if request.get('includeInternal') is not True:
                rows = [r for r in rows if not r['id'].lower().startswith('visitor')]
        elif kind == 'blueprints':
            ids = self.owned | {k for k,v in self.game.wares.items() if v.get('blueprint')}
            rows = [{'id':k,'name':self.game.name(k),'group':self.game.wares.get(k,{}).get('group','其他'),'owned':k in self.owned} for k in ids if k]
            if request.get('ownership') == 'missing':
                rows = [r for r in rows if not r['owned']]
            elif request.get('ownership') == 'owned':
                rows = [r for r in rows if r['owned']]
            if request.get('group'):
                rows = [r for r in rows if r['group'] == request['group']]
        elif kind == 'crew':
            rows = list(self.crew.values())
            if request.get('sector'):
                rows = [r for r in rows if r['sector']['id'] == str(request['sector'])]
            if request.get('ship'):
                rows = [r for r in rows if r['asset'] == int(request['ship'])]
        elif kind == 'cargo':
            return {'storages':self.cargo(int(request.get('ship') or self.current or 0)),
                    'wares':[{'id':k,'name':v['name'],'volume':v['volume'],'transport':v.get('transport')} for k,v in self.game.wares.items() if v.get('transport') in ('container','solid','liquid') and v['volume']>0]}
        else:
            raise ValueError('未知功能面板')
        rows = [r for r in rows if query in ' '.join(str(r.get(k,'')) for k in ('name','id','role','ship')).lower()]
        rows.sort(key=lambda r:(r.get('name',''),str(r['id'])))
        result = {'rows':rows[page*100:(page+1)*100],'total':len(rows),'page':page}
        if kind == 'relations':
            result['internalCount'] = hidden
        return result

    def plan(self, commands):
        if not isinstance(commands,list) or len(commands)>20000:
            raise ValueError('操作清单过大或格式不正确')
        plan = Plan(self.folder)
        # Last explicit edit of the same target wins, independently of pages.
        unique = {}
        for c in commands:
            kind = c.get('kind')
            key = (kind,c.get('id'),c.get('storage'),c.get('skill'))
            unique.pop(key, None)
            unique[key] = c
        new_blueprints = []
        cargo_changes = {}
        stock_changes = {}
        missing_relations = {}
        for c in unique.values():
            kind = c.get('kind')
            if kind == 'money':
                amount = integer(c['value'],0,999999999999999)
                nodes = self.members.get('money',[])
                if not nodes:
                    raise ValueError('未识别到玩家账户')
                for n in nodes:
                    key = {'account':'amount','player':'money','stat':'value'}.get(self.names[self.node(n)[1]])
                    if key:
                        plan.set(n,**{key:amount})
                plan.summaries.append(f'玩家金钱 → {amount:,} Cr（同步 {len(nodes)} 处记录）')
            elif kind == 'station_money':
                station = integer(c['id'],1,2**63-1)
                account = self.station_accounts.get(station)
                if not account or not account['editable']:
                    raise ValueError('空间站账户不存在或与其他账户共用，无法单独修改')
                amount = integer(c['value'],0,999999999999999)
                plan.set(account['node'],amount=amount)
                plan.summaries.append(f'{self.asset_name(station)} / 空间站账户 → {amount:,} Cr')
            elif kind == 'construction_money':
                station = integer(c['id'],1,2**63-1)
                account = self.station_accounts.get(station,{}).get('construction')
                if not account or not account['editable']:
                    raise ValueError('未找到可独立修改的空间站建造账户')
                amount = integer(c['value'],0,999999999999999)
                plan.set(account['node'],amount=amount)
                plan.summaries.append(f'{self.asset_name(station)} / 建造资金 → {amount:,} Cr')
            elif kind in ('station_stock','build_stock'):
                station = integer(c['id'],1,2**63-1)
                wid = str(c['storage'])
                stock_changes.setdefault((station,kind=='build_stock'),{})[wid] = integer(c['value'],0,2147483647)
            elif kind == 'relation':
                identity = c['id']
                if identity not in self.factions or identity == 'player' or 'player' not in self.factions:
                    raise ValueError('势力不存在')
                value = float(c['value'])
                if not math.isfinite(value) or not -1<=value<=1:
                    raise ValueError('关系值必须在 -1 到 1 之间')
                for source,target in [('player',identity),(identity,'player')]:
                    faction = self.factions[source]
                    parent = self.first(faction,'relations')
                    if self.attrs(parent).get('locked') == '1':
                        raise ValueError('该势力关系被游戏锁定，暂不支持修改')
                    nodes = [n for n in self.children(parent,'relation') if self.attrs(n).get('faction') == target]
                    if nodes:
                        for n in nodes:
                            plan.set(n,relation=value)
                    else:
                        xml = element('relation',{'faction':target,'relation':value})
                        if parent:
                            plan.add(parent,xml)
                        else:
                            missing_relations.setdefault(faction,[]).append(xml)
                    for n in self.children(parent,'booster'):
                        if self.attrs(n).get('faction') == target:
                            plan.set(n,relation=0)
                plan.summaries.append(f'{self.game.name(identity)} ↔ 玩家关系 → {value}；双方临时加成归零')
            elif kind == 'blueprint':
                wid = c['id']
                if wid in self.owned:
                    continue
                if not self.game.wares.get(wid,{}).get('blueprint'):
                    raise ValueError('不是本机已识别的可用蓝图：' + str(wid))
                new_blueprints.append(element('blueprint',{'ware':wid}))
                plan.summaries.append('解锁蓝图：' + self.game.name(wid) + ' [' + wid + ']')
            elif kind == 'crew':
                n = integer(c['id'],1,2**63-1)
                if n not in self.crew:
                    raise ValueError('不是玩家船员')
                value = integer(c['value'],0,15)
                skill = c.get('skill','all')
                if skill not in (*SKILLS,'all'):
                    raise ValueError('未知技能')
                data = self.crew[n]
                updates = {s:value for s in (SKILLS if skill=='all' else (skill,))}
                # Accumulate missing skill nodes once per person below.
                cargo_changes.setdefault(('crew',n),{}).update(updates)
                plan.summaries.append(f'{data["ship"]} / {data["name"]} · {skill} → {value/3:g} 星')
            elif kind == 'cargo':
                ship = integer(c['ship'],1,2**63-1)
                storage = integer(c['storage'],1,2**63-1)
                amount = integer(c['value'],0,2147483647)
                cargo_changes.setdefault((ship,storage),{})[c['id']] = amount
            else:
                raise ValueError('未知修改操作')
        if new_blueprints:
            parent = self.first(self.player,'blueprints')
            xml = ''.join(new_blueprints)
            plan.add(parent or self.player,xml if parent else element('blueprints',children=xml))
        for faction, relations in missing_relations.items():
            plan.add(faction,element('relations',children=''.join(relations)))
        for (ship,storage), updates in cargo_changes.items():
            if ship == 'crew':
                data = self.crew[storage]
                if data['skill_node']:
                    plan.set(data['skill_node'],**updates)
                else:
                    xml = element('skills',updates)
                    plan.add(data['parent'] or storage,xml if data['parent'] else element('traits',children=xml))
                continue
            data = next((r for r in self.cargo(ship) if r['id']==storage),None)
            if not data or data['ambiguous'] or data['capacity'] is None:
                raise ValueError('无法确认货仓结构或容量，请先设置正确的游戏目录')
            current = {r['id']:r for r in data['items']}
            if len(current) != len(data['items']):
                raise ValueError('货仓含重复物资记录，暂不支持修改')
            amounts = {k:v['amount'] for k,v in current.items()}
            amounts.update(updates)
            volume = 0
            for wid, amount in amounts.items():
                if not amount:
                    continue
                ware = self.game.wares.get(wid)
                if not ware or ware.get('transport') not in data['types'] or ware['volume']<=0:
                    raise ValueError('无法确认货物体积或不兼容此货仓：' + wid)
                volume += ware['volume'] * amount
            if volume > data['capacity']:
                raise ValueError(f'超出货仓容量：需要 {volume:g}，容量 {data["capacity"]:g} m³')
            additions = []
            for wid, amount in updates.items():
                if wid in current:
                    if amount:
                        plan.set(current[wid]['node'],amount=amount)
                    else:
                        plan.remove_leaf(current[wid]['node'])
                elif amount:
                    additions.append(element('ware',{'ware':wid,'amount':amount}))
                plan.summaries.append(f'{self.asset_name(ship)} / {self.game.name(wid)} → {amount:,}')
            if additions:
                xml = ''.join(additions)
                plan.add(data['cargo'] or storage,xml if data['cargo'] else element('cargo',children=xml))
        for (station,build),updates in stock_changes.items():
            self.plan_station_stock(plan,station,build,updates)
        return plan


_editor = None
_key = None


def get_editor(folder, game_path=None, progress=lambda m:None):
    global _editor, _key
    key = (str(folder),str(game_path or DEFAULT_GAME))
    if _key != key:
        if _editor:
            _editor.close()
        _editor = None
        _key = None
        _editor = Editor(folder,game_path,progress)
        _key = key
    return _editor
