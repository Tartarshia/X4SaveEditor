"""Background operations shared by the desktop and local web interfaces."""
from pathlib import Path
import sys
import core

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
                result = core.query(*args)
            elif action == 'details':
                result = core.details(*args)
            elif action == 'tags':
                with core.connect(args[0]) as db:
                    result = db.execute('SELECT name,count FROM tags ORDER BY count DESC').fetchall()
            elif action == 'export':
                result = core.export_save(*args, progress=progress)
            else:
                raise ValueError('未知任务')
            results.put(('done', result))
        except Exception as exc:
            results.put(('error', str(exc)))
