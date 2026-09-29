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
        self.texts = {}
        self.wares = {}
        self.factions = {}
        self.sectors = {}
        self.macros = {}
        self.macro_paths = {}
        self.component_names = {}
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
            for prefix in ('libraries', 't', 'assets'):
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
            for layer in self.layers:
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
                        self.component_names[component.get('ref').lower()] = data['name']
                    tags = set(data.get('tags', '').split())
                    data['blueprint'] = (data.get('transport') == 'equipment' and item.find('production') is not None
                                         and not tags.intersection({'noblueprint', 'noplayerblueprint'}))
                    data['volume'] = float(data.get('volume', '1'))
                output[identity] = data

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
