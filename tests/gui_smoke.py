"""Run from workspace: python tests/gui_smoke.py [--real]. Opens a temporary window."""
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core
import editor


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        source = temp / 'test.xml'
        source.write_text('<savegame><info><player name="测试" money="42"/></info>' + ''.join(f'<component id="{i}" owner="player"/>' for i in range(500)) + '</savegame>', encoding='utf-8')
        if '--real' in sys.argv:
            paths = list((editor.ROOT / '.cache').glob('*/meta.json'))
            meta = max((json.loads(p.read_text('utf-8')) for p in paths), key=lambda m: m['nodes'])
            source = Path(meta['fingerprint'][0])
        app = editor.App()
        errors = []
        app.report_callback_exception = lambda *args: errors.append(repr(args))
        beats = []
        def heartbeat():
            beats.append(time.perf_counter())
            app.after(20, heartbeat)
        app.after(20, heartbeat)
        def wait():
            until = time.perf_counter()+120
            while app.busy:
                app.update()
                if time.perf_counter()>until:
                    raise TimeoutError(app.status.get())
                time.sleep(.005)
            app.update()
            assert not errors, errors
        try:
            app.run('open', (str(source),), lambda result: app.opened(str(source), result))
            wait()
            assert app.tree.get_children()
            app.navigate('tag', 'component')
            wait()
            assert len(app.tree.get_children()) == 200
            first = list(app.rows)
            app.next_page()
            wait()
            assert len(app.tree.get_children()) == 200
            assert not set(first) & set(app.rows)
            app.back()
            wait()
            assert list(app.rows) == first
            app.navigate('tag', 'player')
            wait()
            node = next(iter(app.rows))
            app.tree.selection_set(str(node))
            app.update()
            wait()
            assert app.originals[node]['money']
            assert app.attrs.get_children()
            if '--real' not in sys.argv:
                money_item = next(i for i in app.attrs.get_children() if app.attrs.item(i, 'values')[0] == 'money')
                app.attrs.selection_set(money_item)
                old_dialog = editor.simpledialog.askstring
                editor.simpledialog.askstring = lambda *a, **k: '123'
                try:
                    app.edit()
                    wait()
                finally:
                    editor.simpledialog.askstring = old_dialog
                assert app.changes[node]['money'] == '123'
                outputs = []
                app.run('export', (app.folder, app.changes, str(temp / 'new.xml.gz')), outputs.append)
                wait()
                assert outputs
                core.validate(outputs[0], {node: {'money': '123'}})
            else:
                try:
                    from PIL import ImageGrab
                    app.update()
                    (editor.ROOT / '.local').mkdir(exist_ok=True)
                    ImageGrab.grab(bbox=(app.winfo_rootx(), app.winfo_rooty(), app.winfo_rootx()+app.winfo_width(), app.winfo_rooty()+app.winfo_height())).save(editor.ROOT / '.local' / 'gui-smoke.png')
                except ImportError:
                    pass
            gaps = [b-a for a,b in zip(beats, beats[1:])]
            print(json.dumps({'ui_smoke': 'PASS', 'real_save': '--real' in sys.argv, 'heartbeats': len(beats), 'max_heartbeat_gap_ms': max(gaps, default=0)*1000}))
        finally:
            app.process.terminate()
            app.process.join(2)
            app.destroy()


if __name__ == '__main__':
    main()
