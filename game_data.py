"""Read local game catalogues, never redistribute Egosoft assets."""
from functools import lru_cache
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET

DEFAULT_GAME = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Steam/steamapps/common/X4 Foundations'


class GameData:
    def __init__(self, path, extensions=()):
        self.path = Path(path)
        self.warnings = []
        self.layers = []
        self.layer_origins = []
        self.sector_sources = {}
        self.catalogue_sources = {'ware':{},'faction':{}}
        self.source_names = {'base':'基础游戏','unknown':'来源未确认'}
        self.texts = {}
        self.wares = {}
        self.factions = {}
        self.sectors = {}
        self.macros = {}
        self.macro_paths = {}
        self.component_names = {}
        self.research = {}
        self.modifications = {}
        self.licences = {}
        self.races = {}
        self.version = ''
        if not self.path.is_dir():
            self.warnings.append('未找到游戏目录。设置目录后可读取货物、未拥有蓝图和中文名称。')
            return
        version = self.path / 'version.dat'
        if version.exists():
            self.version = version.read_text('utf-8-sig').strip()
        roots = [self.path]
        for ext in sorted(set(extensions)):
            if not re.fullmatch(r'[\w.-]+', ext):
                continue
            root = self.path / 'extensions' / ext
            if ext.startswith('ego_dlc_') and root.is_dir():
                roots.append(root)
            elif not ext.startswith('ego_dlc_'):
                self.warnings.append('模组资源未合并：' + ext + '；保留存档中的已有项目。')
            else:
                self.warnings.append('缺少存档所需 DLC：' + ext)
        languages = {'044':{}, '086':{}}
        for root in roots:
            origin='base' if root==self.path else root.name
            self.layer_origins.append(origin)
            if origin!='base':
                try:self.source_names[origin]=ET.parse(root/'content.xml').getroot().get('name') or origin
                except (OSError,ET.ParseError):self.source_names[origin]=origin
            layer = {}
            for cat in sorted(root.glob('*.cat')):
                if '_sig' in cat.name:
                    continue
                offset = 0
                for line in cat.read_text('utf-8-sig').splitlines():
                    name, size, _, _ = line.rsplit(' ', 3)
                    size = int(size)
                    key = name.replace('\\', '/').lower()
                    if key.endswith('.xml'):
                        layer[key] = (cat.with_suffix('.dat'), offset, size)
                    offset += size
            # Loose resources take precedence within the same layer.
            for prefix in ('libraries', 't', 'assets', 'maps'):
                for file in (root / prefix).rglob('*.xml'):
                    layer[file.relative_to(root).as_posix().lower()] = (file, 0, file.stat().st_size)
            self.layers.append(layer)
            for name, entry in layer.items():
                if '/macros/' in name:
                    self.macros[Path(name).stem] = entry
                    self.macro_paths[Path(name).stem] = name
            for lang in ('044', '086'):
                for name in sorted(layer):
                    if name.startswith('t/') and name.endswith('-l' + lang + '.xml'):
                        tree = self.read(layer[name])
                        for page in tree.iter('page'):
                            for t in page.findall('t'):
                                languages[lang][(page.get('id'), t.get('id'))] = ''.join(t.itertext())
        self.texts.update(languages['044'])
        self.texts.update(languages['086'])
        for resource, tag, output in [('libraries/wares.xml', 'ware', self.wares), ('libraries/factions.xml', 'faction', self.factions), ('libraries/mapdefaults.xml', 'dataset', self.sectors)]:
            merged = None
            for layer,origin in zip(self.layers,self.layer_origins):
                if resource not in layer:
                    continue
                tree = self.read(layer[resource])
                if tree.tag != 'diff':
                    if tag == 'dataset' and merged is not None:
                        # DLC defaults are additive libraries, not replacements.
                        # Only identification is consumed by the name catalogue.
                        datasets = {d.get('macro','').lower():d for d in merged.findall('dataset')}
                        for item in tree.findall('dataset'):
                            key = item.get('macro','').lower()
                            previous = datasets.get(key)
                            if previous is None:
                                merged.append(item)
                                datasets[key] = item
                            else:
                                identity = item.find('properties/identification')
                                if identity is not None:
                                    props = previous.find('properties')
                                    if props is None:
                                        props = ET.SubElement(previous, 'properties')
                                    existing = props.find('identification')
                                    if existing is None:
                                        props.append(identity)
                                    else:
                                        existing.attrib.update(identity.attrib)
                    else:
                        merged = tree
                elif merged is not None:
                    self.patch(merged, tree, resource)
                if tag=='dataset' and merged is not None:
                    # Record the introducing layer; later naming patches do not
                    # change which expansion originally supplied a sector.
                    for dataset in merged.findall('dataset'):
                        macro=dataset.get('macro','').lower()
                        if macro:self.sector_sources.setdefault(macro,origin)
                elif tag in self.catalogue_sources and merged is not None:
                    for item in merged.findall(tag):
                        identity=item.get('id','').lower()
                        if identity:self.catalogue_sources[tag].setdefault(identity,origin)
            if merged is None:
                continue
            for item in merged.findall(tag):
                if tag == 'dataset':
                    identity = item.get('macro', '').lower()
                    identification = item.find('properties/identification')
                    if identity and identification is not None and identification.get('name'):
                        output[identity] = self.translate(identification.get('name'))
                    continue
                identity = item.get('id')
                if not identity:
                    continue
                data = dict(item.attrib)
                data['name'] = self.translate(data.get('name', identity))
                if tag == 'ware':
                    component = item.find('component')
                    if component is not None and component.get('ref'):
                        data['component'] = component.get('ref').lower()
                        self.component_names[component.get('ref').lower()] = data['name']
                    tags = set(data.get('tags', '').split())
                    data['blueprint'] = ((data.get('transport') in ('equipment','ship') or 'module' in tags) and item.find('production') is not None
                                         and not tags.intersection({'noblueprint', 'noplayerblueprint'}))
                    if data.get('transport') == 'ship':
                        data['group'] = 'ships'
                    elif 'module' in tags:
                        data['group'] = 'modules'
                    data['volume'] = float(data.get('volume', '1'))
                    price=item.find('price')
                    data['price']={k:float(v) for k,v in price.attrib.items() if k in ('min','max','average')} if price is not None else {}
                    research = item.find('research')
                    if data.get('transport') == 'research' and research is not None:
                        self.research[identity] = {'id':identity,'name':data['name'],
                            'description':self.translate(data.get('description','')),
                            'prerequisites':[w.get('ware') for w in research.findall('research/ware') if w.get('ware')],
                            'time':float(research.get('time',0)),'tags':data.get('tags',''),
                            'resources':{w.get('ware'):int(w.get('amount',0)) for w in research.findall('primary/ware') if w.get('ware')},
                            'hidden':'hidden' in tags,'mission':'missiononly' in tags}
                elif tag == 'faction':
                    self.licences[identity] = {n.get('type'):{**n.attrib,'name':self.translate(n.get('name'))}
                        for n in item.findall('licences/licence') if n.get('type') and n.get('name')}
                output[identity] = data
        mods = self.library('libraries/equipmentmods.xml')
        if mods is not None:
            for category in mods:
                for mod in category:
                    wid = mod.get('ware')
                    if not wid:
                        continue
                    fields = {}
                    for field in [mod,*[f for bonus in mod.findall('bonus') for f in bonus]]:
                        if field.get('min') is None or field.get('max') is None:
                            continue
                        low,high = float(field.get('min')),float(field.get('max'))
                        fields[field.tag] = {'min':low,'max':high}
                    self.modifications[(category.tag,wid)] = {'quality':int(mod.get('quality',0)),
                                                             'primary':mod.tag,'fields':fields,
                                                             'bonusMax':sum(int(b.get('max',0)) for b in mod.findall('bonus'))}
        races = self.library('libraries/races.xml')
        if races is not None:
            self.races = {n.get('id'):self.translate(n.get('name',n.get('id','')))
                          for n in races.findall('race') if n.get('id')}

    @lru_cache(maxsize=512)
    def library(self, path):
        merged = None
        for layer in self.layers:
            if path not in layer:
                continue
            tree = self.read(layer[path])
            if tree.tag != 'diff':
                merged = tree
            elif merged is not None:
                self.patch(merged,tree,path)
        return merged

    @lru_cache(maxsize=4096)
    def model(self, macro):
        path=self.macro_paths.get(str(macro).lower())
        root=self.library(path) if path else None
        return next((n for n in root.iter('macro') if n.get('name','').lower()==str(macro).lower()),None) if root is not None else None

    @lru_cache(maxsize=4096)
    def component(self, ref):
        for path in self.component_paths().get(str(ref).lower(),[]):
            root=self.library(path)
            found=next((n for n in root.iter('component') if n.get('name','').lower()==str(ref).lower()),None)
            if found is not None:return found
        return None

    @lru_cache(maxsize=1)
    def component_paths(self):
        result={}
        for layer in reversed(self.layers):
            for path in layer:
                if path.startswith('assets/') and '/macros/' not in path:result.setdefault(Path(path).stem.lower(),[]).append(path)
        return result

    def properties(self, macro, path):
        model=self.model(macro)
        result={}
        if model is None:return result
        defaults=self.library('libraries/defaults.xml')
        if defaults is not None:
            classes=['ship',model.get('class')] if model.get('class','').startswith('ship_') else [model.get('class')]
            for cls in classes:
                for dataset in defaults.findall('dataset'):
                    if dataset.get('class')==cls:
                        prop=dataset.find('properties/'+path)
                        if prop is not None:result.update(prop.attrib)
        prop=model.find('properties/'+path)
        if prop is not None:result.update(prop.attrib)
        return result

    def macro_for_ware(self, ware):
        ref=self.wares.get(ware,{}).get('component','')
        if ref in self.macro_paths:return ref
        candidate=ref+'_macro'
        return candidate if candidate in self.macro_paths else None

    def sector_source(self,macro):
        origin=self.sector_sources.get(str(macro).lower(),'unknown')
        return {'id':origin,'name':self.translate(self.source_names.get(origin,origin))}

    @lru_cache(maxsize=4096)
    def encyclopedia_source(self,identity):
        key=str(identity).lower();origin='unknown'
        path=self.macro_paths.get(key)
        if path:
            # Inspect only this small resource. A later diff changes properties,
            # but does not move the original definition to another expansion.
            for layer,source in zip(self.layers,self.layer_origins):
                if path not in layer:continue
                root=self.read(layer[path])
                if root.tag!='diff' and any(n.get('name','').lower()==key for n in root.iter('macro')):
                    origin=source;break
        else:
            origin=self.catalogue_sources['ware'].get(key,
                self.catalogue_sources['faction'].get(key,self.sector_sources.get(key,'unknown')))
        return {'id':origin,'name':self.translate(self.source_names.get(origin,origin))}

    @lru_cache(maxsize=1)
    def map_connections(self):
        galaxy=self.library('maps/xu_ep2_universe/galaxy.xml')
        clusters=self.library('maps/xu_ep2_universe/clusters.xml')
        if galaxy is None or clusters is None:return []
        sectors={}
        for cluster in clusters.findall('macro'):
            sectors[cluster.get('name','').lower()]={c.get('name','').lower():c.find('macro').get('ref','').lower()
                for c in cluster.findall('connections/connection') if c.find('macro') is not None and c.get('ref')=='sectors'}
        result=[]
        for universe in galaxy.findall('macro'):
            refs={c.get('name','').lower():c.find('macro').get('ref','').lower()
                for c in universe.findall('connections/connection') if c.find('macro') is not None and c.get('ref')=='clusters'}
            def endpoint(path):
                parts=[p.lower() for p in path.split('/') if p not in ('','..','.')]
                if len(parts)<2:return None
                return sectors.get(refs.get(parts[0]),{}).get(parts[1])
            for c in universe.findall('connections/connection'):
                target=c.find('macro')
                if c.get('ref')!='destination' or target is None:continue
                start=endpoint(c.get('path',''));end=endpoint(target.get('path',''))
                if start and end and start!=end:result.append({'from':start,'to':end,'name':c.get('name','')})
        # Accelerators between sectors of the same cluster are declared here.
        for cluster in clusters.findall('macro'):
            refs=sectors.get(cluster.get('name','').lower(),{})
            def local_endpoint(path):
                parts=[p.lower() for p in path.split('/') if p not in ('','..','.')]
                return refs.get(parts[0]) if parts else None
            for c in cluster.findall('connections/connection'):
                target=c.find('macro')
                if c.get('ref')!='destination' or target is None:continue
                start=local_endpoint(c.get('path',''));end=local_endpoint(target.get('path',''))
                if start and end and start!=end:result.append({'from':start,'to':end,'name':c.get('name','')})
        return result

    @lru_cache(maxsize=1)
    def map_positions(self):
        """Relative positions from the installed universe, including DLC diffs."""
        result={}
        for filename in ('galaxy.xml','clusters.xml'):
            root=self.library('maps/xu_ep2_universe/'+filename)
            if root is None:continue
            for macro in root.findall('macro'):
                for connection in macro.findall('connections/connection'):
                    child=connection.find('macro');position=connection.find('offset/position')
                    if child is not None and position is not None:
                        result[(macro.get('name','').lower(),child.get('ref','').lower())]={k:float(position.get(k,0)) for k in ('x','z')}
        return result

    @lru_cache(maxsize=4096)
    def habitation(self, macro):
        path = self.macro_paths.get(macro.lower())
        root = self.library(path) if path else None
        if root is None:
            return None
        model = next((n for n in root.iter('macro') if n.get('name','').lower()==macro.lower()),None)
        workforce = model.find('properties/workforce') if model is not None else None
        if workforce is None or not workforce.get('race') or not workforce.get('capacity'):
            return None
        return {'race':workforce.get('race'),'capacity':int(workforce.get('capacity'))}

    @staticmethod
    def read(entry):
        path, offset, size = entry
        if size > 32 * 1024**2:
            raise ValueError('游戏数据文件超过读取上限')
        with path.open('rb') as f:
            f.seek(offset)
            raw = f.read(size)
        if b'<!DOCTYPE' in raw.upper():
            raise ValueError('不支持带 DTD 的游戏资源')
        return ET.fromstring(raw)

    def patch(self, root, diff, resource):
        for op in diff:
            selector = op.get('sel', '')
            prefix = '/' + root.tag
            if not selector.startswith(prefix):
                continue
            relative = '.' + selector[len(prefix):]
            try:
                if '/@' in relative:
                    parent, attr = relative.rsplit('/@', 1)
                    targets = root.findall(parent)
                    for target in targets:
                        if op.tag == 'remove':
                            target.attrib.pop(attr, None)
                        else:
                            target.set(attr, op.text or '')
                else:
                    targets = [root] if relative == '.' else root.findall(relative)
                    if op.tag == 'add' and not op.get('pos'):
                        for target in targets:
                            target.extend(list(op))
                    elif op.tag in ('replace', 'remove'):
                        parents = {c:p for p in root.iter() for c in p}
                        for target in targets:
                            parent = parents.get(target)
                            if parent is not None:
                                pos = list(parent).index(target)
                                parent.remove(target)
                                if op.tag == 'replace':
                                    for child in reversed(list(op)):
                                        parent.insert(pos, child)
                    else:
                        raise SyntaxError()
            except (SyntaxError, KeyError):
                self.warnings.append('部分资源补丁暂不支持：' + resource + ' ' + selector)

    def translate(self, value, seen=()):
        def without_comments(text):
            result, depth, index = [], 0, 0
            while index < len(text):
                char = text[index]
                if char == '\\' and index + 1 < len(text):
                    if not depth:
                        result.append(text[index:index+2])
                    index += 2
                    continue
                if char == '(':
                    depth += 1
                elif char == ')' and depth:
                    depth -= 1
                elif not depth:
                    result.append(char)
                index += 1
            return ''.join(result)
        def resolve(text, trail):
            def replace(match):
                key = (match[1], match[2])
                if key in trail or len(trail) > 12:
                    return match[0]
                resource = self.texts.get(key)
                return resolve(without_comments(resource), trail + (key,)) if resource is not None else match[0]
            return re.sub(r'\{(\d+),\s*(\d+)\}', replace, text)
        # Strip comments only in language resources, never in a custom save name.
        return re.sub(r'\\([()\\])', r'\1', resolve(value, seen))

    @lru_cache(maxsize=4096)
    def model_name(self, macro):
        """Resolve model identification lazily, including official DLC patches."""
        key = macro.lower()
        path = self.macro_paths.get(key)
        merged = None
        if path:
            for layer in self.layers:
                if path not in layer:
                    continue
                tree = self.read(layer[path])
                if tree.tag != 'diff':
                    merged = tree
                elif merged is not None:
                    self.patch(merged, tree, path)
        if merged is not None:
            for model in merged.iter('macro'):
                if model.get('name', '').lower() != key:
                    continue
                identification = model.find('properties/identification')
                if identification is not None and identification.get('name'):
                    return self.translate(identification.get('name'))
        return self.component_names.get(key) or (f'未知型号（{macro}）' if macro else '未知型号')

    @lru_cache(maxsize=1)
    def ship_roles(self):
        """Map ship macros to roles declared by the installed game's ship groups."""
        resources = {}
        for name in ('libraries/ships.xml', 'libraries/shipgroups.xml'):
            merged = None
            for layer in self.layers:
                if name not in layer:
                    continue
                tree = self.read(layer[name])
                if tree.tag != 'diff':
                    if merged is None:
                        merged = tree
                    else:
                        key = 'id' if name == 'libraries/ships.xml' else 'name'
                        existing = {item.get(key):item for item in merged}
                        for item in tree:
                            previous = existing.get(item.get(key))
                            if previous is None:
                                merged.append(item)
                            elif key == 'name':
                                previous.extend(list(item))
                            else:
                                merged.remove(previous)
                                merged.append(item)
                elif merged is not None:
                    self.patch(merged,tree,name)
            resources[name] = merged
        ships,groups = resources.values()
        if ships is None or groups is None:
            return {}
        labels = {'carrier':'航母','battleship':'战列舰','destroyer':'驱逐舰','frigate':'护卫舰',
                  'gunboat':'炮艇','corvette':'轻型护卫舰','fighter':'战斗机','scout':'侦察机',
                  'resupplier':'补给舰','builder':'建造舰','miner':'采矿船','trader':'运输船',
                  'tug':'拖船','terraformer':'地貌改造船','plunderer':'掠夺船'}
        by_group = {}
        for ship in ships.findall('ship'):
            category = ship.find('category')
            tags = set(category.get('tags','').strip('[]').replace(',',' ').split()) if category is not None else set()
            role = next((label for tag,label in labels.items() if tag in tags),'')
            if role and ship.get('group'):
                by_group.setdefault(ship.get('group'),set()).add(role)
        result = {}
        for group in groups.findall('group'):
            roles = by_group.get(group.get('name'),set())
            if len(roles) != 1:
                continue
            role = next(iter(roles))
            for item in group.findall('select'):
                if item.get('macro'):
                    result.setdefault(item.get('macro').lower(),set()).add(role)
        return {macro:next(iter(roles)) for macro,roles in result.items() if len(roles)==1}

    def ship_type(self, macro, ship_class):
        size = ship_class.removeprefix('ship_').upper() if ship_class.startswith('ship_') else ''
        role = self.ship_roles().get(macro.lower(),'') if macro else ''
        if not role:
            parts = macro.lower().split('_')
            if len(parts)>3 and parts[0]=='ship':
                role = {'battleship':'战列舰','carrier':'航母','destroyer':'驱逐舰','frigate':'护卫舰',
                        'corvette':'轻型护卫舰','heavyfighter':'重型战斗机','fighter':'战斗机',
                        'bomber':'轰炸机','scout':'侦察机','resupplier':'补给舰','builder':'建造舰',
                        'miner':'采矿船','trans':'运输船','tugboat':'拖船'}.get(parts[3],'')
        return ' · '.join(part for part in (size,role) if part) or '未知船型'

    @staticmethod
    def cargo_ware(ware):
        return (ware.get('transport') in ('container','solid','liquid') and ware.get('volume',0)>0
                and 'module' not in ware.get('tags','').split())

    @lru_cache(maxsize=4096)
    def storage(self, macro):
        if macro not in self.macros:
            return None
        root = self.read(self.macros[macro])
        cargo = root.find('.//properties/cargo')
        if cargo is None:
            return None
        return {'capacity': float(cargo.get('max', '0')), 'types': cargo.get('tags', '').split()}

    def name(self, identity):
        return self.wares.get(identity, self.factions.get(identity, {})).get('name', identity)
