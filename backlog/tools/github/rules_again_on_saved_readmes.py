"""Run the rules of parse/markdown.py once more over every saved README. Counts only.

If the rules hide nothing more and cut nothing more, then nothing that they look for is left in
the saved READMEs. It also sorts the words that start with "@" outside code into packages (a
slash after the name) and others, without printing any of them.

    .venv/Scripts/python.exe backlog/tools/github/rules_again_on_saved_readmes.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from hackathon_memory.parse.markdown import hide_in_markdown
from hackathon_memory.settings import Settings

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
folder = Path(Settings().data_dir) / "raw" / "api.github.com"
AT = re.compile(r"(?<![\w./@+-])@([A-Za-z0-9_][\w.-]*)(/?)")

again: Counter[str] = Counter()
at_words: Counter[str] = Counter()
for meta_path in sorted(folder.glob("*.meta.json")):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta["status"] != 200:
        continue
    text = meta_path.with_name(meta_path.name.removesuffix(".meta.json") + ".txt").read_text(
        encoding="utf-8"
    )
    done = hide_in_markdown(text)
    again["readmes"] += 1
    again["words hidden on a second pass"] += done.words_hidden
    again["parts about the team cut on a second pass"] += done.team_parts_cut
    again["texts changed by a second pass"] += done.text != text
    for match in AT.finditer(text):
        if match.group(1).startswith("[name"):
            at_words["the hidden mark"] += 1
        elif match.group(2) == "/":
            at_words["a package (a slash after the name)"] += 1
        else:
            at_words["another word with @ (in code, a decorator, a version)"] += 1
for key, value in again.items():
    print(f"{value:5}  {key}")
print("words with @ in the saved READMEs:", dict(at_words))
