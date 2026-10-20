"""After the rewrite of 10 October 2026: put the NEW commit numbers into the local notes.

    python backlog/tools/rewrite/update_notes.py           from the project folder

It reads commit-map-20261010.txt (written by git-filter-repo: old number, new number). In every
note under backlog/ it replaces the short form of an old number by the short form of the new one.
A commit that only touched notes has no new number: it is not in the new history. Its old number
stays in the notes, and the list of those is printed. The old history is kept in
.local-backup/old-history-20261010.bundle.
"""

import re
from pathlib import Path

root = Path.cwd()
lines = (root / "backlog/tools/rewrite/commit-map-20261010.txt").read_text(encoding="utf-8").splitlines()
mapping: dict[str, str] = {}
gone: list[str] = []
for line in lines[1:]:
    old, new = line.split()
    if set(new) == {"0"}:
        gone.append(old[:7])
    else:
        mapping[old[:7]] = new[:7]

changed = 0
for path in sorted((root / "backlog").rglob("*.md")):
    if "tools" in path.parts:
        continue
    text = path.read_text(encoding="utf-8")
    new_text = text
    for old, new in mapping.items():
        new_text = re.sub(rf"(?<![0-9a-f]){old}(?![0-9a-f])", new, new_text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8", newline="\n")
        changed += 1
        print("updated", path.relative_to(root))
print(f"{changed} note(s) updated; {len(mapping)} commits have a new number.")
print(f"{len(gone)} commits touched only notes and are not in the new history: {', '.join(sorted(gone))}")
