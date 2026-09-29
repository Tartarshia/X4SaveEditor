"""Small, composable XML edits. All offsets refer to the immutable snapshot."""
import re
from xml.sax.saxutils import quoteattr
import core


def element(tag, attrs=None, children=''):
    text = '<' + tag + ''.join(' ' + k + '=' + quoteattr(str(v)) for k, v in (attrs or {}).items())
    return (text + '>' + children + '</' + tag + '>' if children else text + '/>')


class Plan:
    def __init__(self, folder):
        self.folder = folder
        self.attrs = {}
        self.children = {}
        self.removed = set()
        self.summaries = []

    def set(self, node, **values):
        self.attrs.setdefault(node, {}).update({k: str(v) for k, v in values.items()})

    def add(self, parent, xml):
        self.children.setdefault(parent, []).append(xml)

    def remove_leaf(self, node):
        self.removed.add(node)

    def compile(self, advanced=None):
        attrs = {n: dict(v) for n, v in self.attrs.items()}
        for n, values in (advanced or {}).items():
            n = int(n)
            if n in attrs or n in self.children or n in self.removed:
                raise ValueError('高级属性修改与功能面板冲突，请先撤销其中一项')
            # Advanced editing still only permits existing attributes.
            core.replaced_tag(core.start_tag(self.folder, n)[1], values)
            attrs[n] = values
        patches, delta = [], 0
        for node in sorted(set(attrs) | set(self.children) | self.removed):
            offset, raw = core.start_tag(self.folder, node)
            if node in self.removed:
                if node in attrs or node in self.children or not raw.rstrip().endswith(b'/>'):
                    raise ValueError('仅支持删除无子节点的货物记录')
                patches.append((offset, raw, b''))
                delta -= 1
                continue
            existing = core.attributes(raw)
            updates = attrs.get(node, {})
            replacement = core.replaced_tag(raw, {k:v for k,v in updates.items() if k in existing})
            missing = {k:v for k,v in updates.items() if k not in existing}
            if missing:
                if any(not re.fullmatch(r'[a-zA-Z_][\w.-]*', k) for k in missing):
                    raise ValueError('非法属性名')
                ending = 2 if replacement.endswith(b'/>') else 1
                addition = ''.join(' ' + k + '=' + quoteattr(v) for k,v in missing.items()).encode('utf-8')
                replacement = replacement[:-ending] + addition + replacement[-ending:]
                core.attributes(replacement)
            if node in self.children:
                fragment = ''.join(self.children[node]).encode('utf-8')
                count = [0]
                p = core.parser()
                p.StartElementHandler = lambda t,a: count.__setitem__(0, count[0] + 1)
                p.Parse(b'<wrapper>' + fragment + b'</wrapper>', True)
                delta += count[0] - 1
                if replacement.endswith(b'/>'):
                    tag = re.match(rb'<([^\s/>]+)', replacement)[1]
                    replacement = replacement[:-2] + b'>' + fragment + b'</' + tag + b'>'
                else:
                    replacement += fragment
            patches.append((offset, raw, replacement))
        return patches, delta

    def export(self, changes, destination, progress):
        patches, delta = self.compile(changes)
        return core.export_save(self.folder, {}, destination, progress, structural=patches, node_delta=delta)
