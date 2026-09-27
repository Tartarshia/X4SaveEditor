"""Chinese desktop UI. Heavy work runs in a separate process."""
import multiprocessing as mp
from pathlib import Path
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import core
from tasks import ROOT, worker


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('X4 存档修改器 · 完整结构浏览')
        self.geometry('1320x840')
        self.minsize(960, 620)
        style = ttk.Style(self)
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        style.configure('Treeview', rowheight=27, font=('Microsoft YaHei UI', 10))
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        self.requests, self.results = mp.Queue(), mp.Queue()
        self.process = mp.Process(target=worker, args=(self.requests, self.results), daemon=True)
        self.process.start()
        self.folder = None
        self.source = None
        self.busy = False
        self.callback = None
        self.changes = {}
        self.originals = {}
        self.rows = {}
        self.selected = None
        self.mode, self.value, self.after_id = 'children', 0, 0
        self.history = []
        self.has_more = False
        self.status = tk.StringVar(value='打开 .xml.gz 或 .xml 存档。首次建立索引，之后直接复用。')
        self.summary = tk.StringVar(value='尚未打开存档')
        self.location = tk.StringVar(value='根目录')
        self.pending = tk.StringVar(value='待修改：0 项')
        self._widgets()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(80, self.poll)

    def _widgets(self):
        bar = ttk.Frame(self, padding=10)
        bar.pack(fill='x')
        for text, command in [('打开存档', self.open_file), ('结构根目录', lambda: self.navigate('children', 0)),
                              ('标签统计', self.show_tags), ('查看待修改', self.review), ('导出新存档', self.export)]:
            ttk.Button(bar, text=text, command=command).pack(side='left', padx=3)
        ttk.Label(bar, textvariable=self.pending).pack(side='right', padx=8)
        ttk.Label(self, textvariable=self.summary, padding=(14, 4)).pack(fill='x')
        search = ttk.Frame(self, padding=(12, 8))
        search.pack(fill='x')
        self.search_mode = ttk.Combobox(search, state='readonly', values=['标签名（精确）', 'ID（精确）', '节点编号', '名称 / macro 包含'], width=18)
        self.search_mode.current(0)
        self.search_mode.pack(side='left')
        self.search_text = ttk.Entry(search, width=45)
        self.search_text.pack(side='left', padx=6)
        self.search_text.bind('<Return>', lambda e: self.search())
        ttk.Button(search, text='查询', command=self.search).pack(side='left')
        ttk.Label(search, text='例如 component / account / player；ID 保留原值').pack(side='left', padx=12)
        nav = ttk.Frame(self, padding=(12, 4))
        nav.pack(fill='x')
        for text, command in [('返回', self.back), ('进入子节点', self.enter), ('转到父节点', self.parent), ('下一页', self.next_page)]:
            ttk.Button(nav, text=text, command=command).pack(side='left', padx=2)
        ttk.Label(nav, textvariable=self.location).pack(side='left', padx=10)
        panes = ttk.Panedwindow(self, orient='horizontal')
        panes.pack(fill='both', expand=True, padx=12, pady=6)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=3)
        panes.add(right, weight=2)
        self.tree = self.table(left, ('node', 'tag', 'id', 'label'), ('节点', '标签', 'ID', '名称 / 类型 / 所属'), (85, 120, 120, 340))
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Double-1>', lambda e: self.enter_when_ready())
        ttk.Label(right, text='属性 · 双击修改，修改先加入清单', padding=4).pack(fill='x')
        attr_frame = ttk.Frame(right, height=230)
        attr_frame.pack(fill='both', expand=True)
        self.attrs = self.table(attr_frame, ('key', 'value'), ('属性名', '值（* 表示待修改）'), (120, 310))
        self.attrs.bind('<Double-1>', lambda e: self.edit())
        ttk.Button(right, text='修改选中属性', command=self.edit).pack(anchor='w', pady=5)
        ttk.Label(right, text='原始 XML 片段（从此处起最多 16 KiB，可能包含后续节点）').pack(fill='x')
        preview_frame = ttk.Frame(right)
        preview_frame.pack(fill='both', expand=True)
        self.preview = tk.Text(preview_frame, height=13, wrap='none', font=('Consolas', 10), state='disabled')
        sy = ttk.Scrollbar(preview_frame, command=self.preview.yview)
        sx = ttk.Scrollbar(preview_frame, orient='horizontal', command=self.preview.xview)
        self.preview.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side='right', fill='y')
        sx.pack(side='bottom', fill='x')
        self.preview.pack(fill='both', expand=True)
        footer = ttk.Frame(self, padding=8)
        footer.pack(fill='x')
        self.progress = ttk.Progressbar(footer, mode='indeterminate', length=100)
        self.progress.pack(side='left', padx=5)
        ttk.Label(footer, textvariable=self.status).pack(side='left', padx=8)

    @staticmethod
    def table(parent, columns, headings, widths):
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True)
        tree = ttk.Treeview(box, columns=columns, show='headings', selectmode='browse')
        for col, heading, width in zip(columns, headings, widths):
            tree.heading(col, text=heading)
            tree.column(col, width=width, minwidth=60, stretch=col == columns[-1])
        sy = ttk.Scrollbar(box, command=tree.yview)
        sx = ttk.Scrollbar(box, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side='right', fill='y')
        sx.pack(side='bottom', fill='x')
        tree.pack(fill='both', expand=True)
        return tree

    def run(self, action, args, callback):
        if self.busy:
            return False
        self.busy = True
        self.callback = callback
        self.progress.start(15)
        self.status.set('正在处理… 窗口可正常移动和滚动')
        self.requests.put((action, args))
        return True

    def poll(self):
        try:
            while True:
                kind, value = self.results.get_nowait()
                if kind == 'progress':
                    self.status.set(value)
                    continue
                self.busy = False
                self.progress.stop()
                self.progress.configure(value=0)
                cb, self.callback = self.callback, None
                if kind == 'error':
                    self.status.set('操作失败；原存档未改动')
                    messagebox.showerror('操作失败', value, parent=self)
                else:
                    self.status.set('就绪')
                    cb(value)
        except queue.Empty:
            pass
        if self.busy and not self.process.is_alive():
            self.busy = False
            self.progress.stop()
            self.progress.configure(value=0)
            self.status.set('后台进程退出，请重新启动程序；原存档未改动')
        self.after(80, self.poll)

    def open_file(self):
        if self.busy:
            return
        if self.changes and not messagebox.askyesno('待修改内容', '打开其他存档会丢弃当前修改清单。继续？', parent=self):
            return
        path = filedialog.askopenfilename(parent=self, initialdir=Path.home() / 'Documents' / 'Egosoft' / 'X4', filetypes=[('X4 存档', '*.xml.gz *.xml'), ('全部文件', '*.*')])
        if path:
            self.run('open', (path,), lambda result: self.opened(path, result))

    def opened(self, path, result):
        self.folder, meta = result
        self.source = Path(path)
        self.changes.clear()
        self.originals.clear()
        self.history.clear()
        self.pending.set('待修改：0 项')
        self.summary.set(f'{self.source.name}  ·  XML {meta["xml_bytes"]/1048576:,.1f} MiB  ·  {meta["nodes"]:,} 节点  ·  {meta["tags"]} 种标签  ·  首次索引 {meta["seconds"]:.1f} 秒')
        self.navigate('children', 0, remember=False)

    def navigate(self, mode, value, after=0, remember=True):
        if self.busy or not self.folder:
            return
        if remember:
            self.history.append((self.mode, self.value, self.after_id))
        self.mode, self.value, self.after_id = mode, value, after
        self.run('query', (self.folder, mode, value, after), self.show_rows)

    def show_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        self.attrs.delete(*self.attrs.get_children())
        self.set_preview('')
        self.selected = None
        self.has_more = len(rows) > core.PAGE
        self.rows = {r[0]: r for r in rows[:core.PAGE]}
        for node, tag, parent, offset, ref, label in rows[:core.PAGE]:
            self.tree.insert('', 'end', iid=str(node), values=(node, tag, ref, label))
        names = {'children': '子节点', 'tag': '标签', 'id': 'ID', 'node': '节点', 'text': '名称 / macro'}
        self.location.set(f'{names[self.mode]}：{self.value} · 本页 {len(self.rows)} 条' + (' · 还有下一页' if self.has_more else ' · 已到末尾'))

    def search(self):
        value = self.search_text.get().strip()
        if not value:
            return
        mode = ['tag', 'id', 'node', 'text'][self.search_mode.current()]
        if mode == 'node' and not value.isdecimal():
            messagebox.showerror('查询', '节点编号应为整数', parent=self)
            return
        self.navigate(mode, value)

    def back(self):
        if not self.busy and self.history:
            self.navigate(*self.history.pop(), remember=False)

    def enter(self):
        sel = self.tree.selection()
        if sel:
            self.navigate('children', int(sel[0]))

    def enter_when_ready(self):
        if self.busy:
            self.after(100, self.enter_when_ready)
        else:
            self.enter()

    def parent(self):
        sel = self.tree.selection()
        if sel:
            self.navigate('node', self.rows[int(sel[0])][2])

    def next_page(self):
        if self.has_more and self.rows:
            self.navigate(self.mode, self.value, max(self.rows))

    def select(self, event=None):
        sel = self.tree.selection()
        if self.busy:
            # Retry latest selection after the active bounded read completes.
            self.after(100, self.select)
            return
        if sel:
            node = int(sel[0])
            self.selected = node
            self.run('details', (self.folder, node), lambda result: self.show_details(node, result))

    def set_preview(self, value):
        self.preview.configure(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.insert('1.0', value)
        self.preview.configure(state='disabled')

    def show_details(self, node, result):
        attrs, preview = result
        self.originals = {node: attrs}
        self.attrs.delete(*self.attrs.get_children())
        edits = self.changes.get(node, {})
        for i, (key, value) in enumerate(attrs.items()):
            self.attrs.insert('', 'end', iid=str(i), values=(key, ('* ' if key in edits else '') + edits.get(key, value)))
        self.set_preview(preview)
        if not attrs:
            self.status.set('此节点没有属性；可进入子节点继续浏览')

    def edit(self):
        if self.busy or self.selected is None or not self.attrs.selection():
            return
        node = self.selected
        key = self.attrs.item(self.attrs.selection()[0], 'values')[0]
        original = self.originals[node][key]
        value = simpledialog.askstring('修改 XML 属性', f'节点 {node} · {key}\n原值：{original[:200]}\n仅校验 XML 格式；字段之间的游戏逻辑需自行确认。', initialvalue=self.changes.get(node, {}).get(key, original), parent=self)
        if value is None:
            return
        try:
            core.replaced_tag(b'<test value=""/>', {'value': value})
        except Exception as exc:
            messagebox.showerror('无效属性值', str(exc), parent=self)
            return
        edits = self.changes.setdefault(node, {})
        if value == original:
            edits.pop(key, None)
        else:
            edits[key] = value
        if not edits:
            self.changes.pop(node, None)
        self.pending.set(f'待修改：{sum(map(len, self.changes.values()))} 项')
        self.select()

    def review(self):
        if not self.changes:
            messagebox.showinfo('待修改', '尚无待修改内容', parent=self)
            return
        win = tk.Toplevel(self)
        win.title('修改清单 · 导出前可撤销')
        win.geometry('760x440')
        table = self.table(win, ('node', 'key', 'value'), ('节点', '属性', '新值'), (100, 180, 420))
        mapping = {}
        for node, attrs in self.changes.items():
            for key, value in attrs.items():
                item = table.insert('', 'end', values=(node, key, value))
                mapping[item] = (node, key)
        def undo():
            if self.busy or not table.selection():
                return
            item = table.selection()[0]
            node, key = mapping[item]
            if node in self.changes:
                self.changes[node].pop(key, None)
                if not self.changes[node]:
                    del self.changes[node]
            table.delete(item)
            self.pending.set(f'待修改：{sum(map(len, self.changes.values()))} 项')
            self.select()
        ttk.Button(win, text='撤销选中的修改', command=undo).pack(pady=8)

    def show_tags(self):
        if self.folder:
            self.run('tags', (self.folder,), self.tags_ready)

    def tags_ready(self, rows):
        win = tk.Toplevel(self)
        win.title('全存档标签统计 · 双击浏览')
        win.geometry('540x600')
        table = self.table(win, ('tag', 'count'), ('标签', '节点总数'), (300, 160))
        for tag, count in rows:
            table.insert('', 'end', values=(tag, count))
        def choose(event):
            if table.selection():
                tag = table.item(table.selection()[0], 'values')[0]
                self.navigate('tag', tag)
                win.destroy()
        table.bind('<Double-1>', choose)

    def export(self):
        if self.busy or not self.folder:
            return
        if not messagebox.askyesno('导出新存档', f'导出 {sum(map(len, self.changes.values()))} 项属性修改。\n保留原文件，完整回读校验后生成新文件。\nXML 校验不代表游戏逻辑校验。继续？', parent=self):
            return
        dest = filedialog.asksaveasfilename(parent=self, initialdir=self.source.parent, initialfile=self.source.name.replace('.xml', '_edited.xml'), defaultextension='.xml.gz', filetypes=[('压缩存档', '*.xml.gz'), ('XML 存档', '*.xml')])
        if dest:
            self.run('export', (self.folder, self.changes, dest), self.exported)

    def exported(self, path):
        self.status.set('已导出并完成全部节点与修改值校验')
        messagebox.showinfo('导出完成', f'{path}\n\n原存档保留。请在退出游戏后管理槽位文件，再进游戏确认效果。', parent=self)

    def close(self):
        if (self.busy or self.changes) and not messagebox.askyesno('关闭', '后台任务或待修改内容将被放弃。关闭？\n原存档不会被改动。', parent=self):
            return
        self.process.terminate()
        self.process.join(timeout=1)
        self.destroy()


if __name__ == '__main__':
    mp.freeze_support()
    App().mainloop()
