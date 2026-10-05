"""Terraforming records from the immutable save index and local catalogue."""
from functools import lru_cache
from collections import Counter
import math
from management import whole


class TerraformingFeatures:
    @lru_cache(maxsize=1)
    def terraforming_catalogue(self):
        root = self.game.library('libraries/terraforming.xml')
        if root is None:
            return {}, {}
        stats = {}
        for stat in root.findall('stats/stat'):
            ends = [float(r.get('end')) for r in stat.findall('range') if r.get('end') is not None]
            stats[stat.get('id')] = {'name':self.game.translate(stat.get('name',stat.get('id'))),
                                    'min':0 if ends else None,'max':max(ends) if ends else None,
                                    'ranges':[{'end':float(r.get('end')),
                                               'description':self.game.translate(r.get('description','')),
                                               'habitable':r.get('habitable')!='false'}
                                              for r in stat.findall('range') if r.get('end') is not None]}
        groups = {g.get('id'):self.game.translate(g.get('name',g.get('id')))
                  for g in root.findall('projectgroups/projectgroup')}
        return stats, groups

    @lru_cache(maxsize=1)
    def terraforming_planets(self):
        roots = [n for n, in self.db.execute('SELECT id FROM nodes WHERE tag=? ORDER BY id LIMIT 257',
                                            (self.tags.get('terraforming',-1),))]
        if len(roots)>256:
            raise ValueError('行星改造记录过多，无法安全处理')
        rows = []
        for node in roots:
            cluster = self.node(node)[0]
            attrs = self.attrs(cluster)
            if self.names[self.node(cluster)[1]]!='component' or attrs.get('class')!='cluster':
                continue
            macro = attrs.get('macro','')
            sectors = []
            for sector in self.galaxy_sectors():
                parent = sector['id']
                while parent and parent!=cluster:
                    parent = self.node(parent)[0]
                if parent==cluster:
                    sectors.append(sector['name'])
            rows.append({'id':node,'cluster':cluster,'macro':macro,
                         'name':' / '.join(sectors) or self.game.sectors.get(macro,macro),
                         'active':self.attrs(node).get('active',''),
                         'missionCompleted':self.attrs(node).get('missioncomplete')=='1'})
        return rows

    def terraforming_data(self, request):
        planets = self.terraforming_planets()
        if not planets:
            return {'planets':[],'planet':None,'stats':[],'rows':[],'total':0,'page':0}
        identity = whole(request.get('planet') or planets[0]['id'])
        planet = next((p for p in planets if p['id']==identity),None)
        if planet is None:
            raise ValueError('请选择存档中已有的改造行星')
        specs, groups = self.terraforming_catalogue()
        parents = self.children(identity,'stats')
        nodes = [n for p in parents for n in self.children(p,'stat')]
        if len(nodes)>100:
            raise ValueError('行星指标结构过大')
        stats = []
        for node in nodes:
            a = self.attrs(node); key = a.get('id',''); spec = specs.get(key,{})
            try:
                value = float(a['value'])
                valid = math.isfinite(value)
                if not valid:value = None
            except (KeyError,ValueError):
                value = None; valid = False
            unique = sum(self.attrs(n).get('id')==key for n in nodes)==1
            editable = bool(valid and unique and len(parents)==1 and not planet['active']
                            and self.leaf(node) and len(self.children(planet['cluster'],'terraforming'))==1
                            and spec.get('max') is not None and spec['min']<=value<=spec['max'])
            status = next((r['description'] for r in spec.get('ranges',[]) if valid and value<=r['end']),'')
            stats.append({'id':node,'key':key,'name':spec.get('name',key),'value':value,
                          'min':spec.get('min'),'max':spec.get('max'),'status':status,'editable':editable})
        project_parents = self.children(identity,'projects')
        projects = [n for p in project_parents for n in self.children(p,'project')]
        if len(projects)>1000:
            raise ValueError('行星项目结构过大')
        project_counts = Counter(self.attrs(n).get('id') for n in projects)
        rows = []
        hqs = self.headquarters()
        hq_cluster = hqs[0] if len(hqs)==1 else None
        while hq_cluster and self.attrs(hq_cluster).get('class')!='cluster':
            hq_cluster = self.node(hq_cluster)[0]
        for node in projects:
            a = self.attrs(node); key = a.get('id','')
            containers = self.children(node,'scaledresources')
            resources = []
            safe = len(containers)==1 and len(project_parents)==1 and project_counts[key]==1
            for parent in containers:
                for widnode in self.children(parent,'ware'):
                    w = self.attrs(widnode); wid = w.get('ware','')
                    try:amount = whole(w.get('amount'))
                    except (ValueError,TypeError):amount = None; safe = False
                    if any(r['id']==wid for r in resources):safe = False
                    resources.append({'id':wid,'name':self.game.name(wid),'amount':amount})
            try:
                completed = whole(a.get('completed',0))
                repeatable = math.isfinite(float(a.get('repeatcooldown',-1))) and float(a.get('repeatcooldown',-1))>=0
            except (ValueError,TypeError):
                completed = None; repeatable = False; safe = False
            active = planet['active']==key
            rows.append({'id':node,'key':key,'name':self.game.translate(a.get('name') or key),
                         'group':groups.get(a.get('group'),a.get('group','')),
                         'completed':completed,'active':active,'duration':a.get('duration'),
                         'resources':resources,'canSupply':bool(safe and resources and not active
                             and (not completed or repeatable)
                             and hq_cluster==planet['cluster'])})
        query = str(request.get('search','')).lower()
        rows = [r for r in rows if query in (r['key']+' '+r['name']+' '+r['group']).lower()]
        rows.sort(key=lambda r:(not r['active'],r['group'],r['key']))
        page = whole(request.get('page',0),0,100000)
        return {'planets':planets,'planet':planet,'stats':stats,'rows':rows[page*50:(page+1)*50],
                'total':len(rows),'page':page,'hqHere':hq_cluster==planet['cluster']}

    def terraforming_supply(self, command):
        data = self.terraforming_data({'planet':command['planet']})
        # Locate through the same bounded, filtered data path used by the UI.
        for page in range((data['total']+49)//50):
            if page:data = self.terraforming_data({'planet':command['planet'],'page':page})
            row = next((r for r in data['rows'] if r['id']==int(command['id'])),None)
            if row:
                if not row['canSupply']:raise ValueError('项目物资不明确、正在执行或总部不在该行星所在星系')
                return {r['id']:r['amount'] for r in row['resources']}
        raise ValueError('未找到改造项目')

    def plan_terraforming_stat(self, plan, command):
        data = self.terraforming_data({'planet':command['planet']})
        row = next((r for r in data['stats'] if r['id']==int(command['id'])),None)
        if isinstance(command['value'],bool):raise ValueError('改造指标必须为数值')
        value = float(command['value'])
        if not row or not row['editable'] or not math.isfinite(value) or not row['min']<=value<=row['max']:
            raise ValueError('改造指标只支持已有、唯一、闲置且游戏目录范围明确的记录')
        plan.set(row['id'],value=format(value,'.17g'))
        plan.summaries.append(f'{data["planet"]["name"]} / {row["name"]} → {value:g}')

    def terraforming_sources(self, command):
        data = self.terraforming_data({'planet':command['planet']})
        identity = int(command['id'])
        if command['kind']=='terraforming_stat':
            if not any(r['id']==identity for r in data['stats']):raise ValueError('指标不属于该行星')
            nodes = [identity]
        else:
            parent = self.node(identity)[0]
            if (self.names[self.node(identity)[1]]!='project' or self.names[self.node(parent)[1]]!='projects'
                    or self.node(parent)[0]!=data['planet']['id']):raise ValueError('项目不属于该行星')
            nodes = [identity]
            if command['kind']=='terraforming_stock':
                self.terraforming_supply(command)
                nodes.extend(self.headquarters())
        return {'nodes':[{'id':n,'label':self.names[self.node(n)[1]]+' #'+str(n)} for n in nodes]}
