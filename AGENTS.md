# X4SaveEditor

Independent workspace. Do not change sibling projects or the game installation.
Python standard library only. Run `python -m unittest discover -s tests`.
Large saves must use streaming parsing, bounded memory, disk indexes, paginated UI,
and background processes for long operations. Never build an entire XML DOM.
Preserve original XML bytes outside explicitly edited attributes and vetted gameplay insertions/deletions.
Export to a new file only; validate before publishing it. Never overwrite a source save.
Keep saves, cache, local benchmarks, user names and machine paths out of version control.
Read names and gameplay catalogues only from the local game installation; retain raw IDs.
Never redistribute extracted resources or guess unknown cargo capacities/game semantics.

The default UI is web_server.py with static web/ assets. Bind loopback only;
keep same-origin/Host/token checks and stream uploads/downloads. No CDN assets.
Long jobs run in tasks.py in a separate process; never parse entire saves in the browser.
Keep LICENSE, THIRD_PARTY_NOTICES.md and pinned research references in source releases.
Local data, screenshots, caches and exports must remain ignored. No auto-start service.
