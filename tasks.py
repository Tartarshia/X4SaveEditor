"""Background operations shared by the desktop and local web interfaces."""
from pathlib import Path
import sys
import core
import shortcuts
import gameplay

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def worker(requests, results):
    while True:
        job = requests.get()
        if job is None:
            return
        action, args = job
        try:
            progress = lambda msg: results.put(('progress', msg))
            if action == 'open':
                result = core.build_index(args[0], ROOT / '.cache', progress)
            elif action == 'query':
                result = shortcuts.query(args[0],args[2],args[3],progress) if args[1]=='shortcut' else core.query(*args)
            elif action == 'shortcuts':
                result = shortcuts.catalog(args[0],progress)
            elif action == 'details':
                result = core.details(*args)
            elif action == 'tags':
                with core.connect(args[0]) as db:
                    result = db.execute('SELECT name,count FROM tags ORDER BY count DESC').fetchall()
            elif action == 'export':
                if len(args) > 3 and args[3]:
                    result = gameplay.get_editor(args[0], args[4], progress).plan(args[3]).export(args[1], args[2], progress)
                else:
                    result = core.export_save(*args[:3], progress=progress)
            elif action == 'gameplay':
                result = gameplay.get_editor(args[0], args[1].get('gamePath'), progress).view(args[1])
            elif action == 'plan':
                plan = gameplay.get_editor(args[0], args[1].get('gamePath'), progress).plan(args[1].get('commands', []))
                patches, delta = plan.compile(args[1].get('changes', {}))
                result = {'summaries': plan.summaries, 'patches':len(patches),'nodeDelta':delta}
            else:
                raise ValueError('未知任务')
            results.put(('done', result))
        except Exception as exc:
            results.put(('error', str(exc)))
