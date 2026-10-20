"""Cut the lines that list the people of a team out of the saved Hedera winner posts.

It uses the one way in which a saved page may change (RawStore.remove_text): the small file of
the post keeps the reason, the time and the number of lines, never the text. Counts only.

    .venv/Scripts/python.exe backlog/tools/hedera/cut_people_from_saved_posts.py         a dry run
    .venv/Scripts/python.exe backlog/tools/hedera/cut_people_from_saved_posts.py --cut

Why (12 October 2026): the first pattern of the collector knew "Team Members" but not "Team
Member" in the singular, which stood in a saved post. The pattern was fixed in 0c41af9.
"""

from __future__ import annotations

import re
import sys

from bs4 import BeautifulSoup

from hackathon_memory.collect.hedera_posts import POSTS, people_lines, raw_dir
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.settings import Settings

WHY = (
    "a line that names people of a team (a list, or the signature under a quote), missed at the "
    "first save; the rules were widened on 12 October 2026"
)
cut = sys.argv[1:] == ["--cut"]
store = RawStore(raw_dir(Settings()))
for event, url in POSTS.items():
    saved = store.load(url)
    if saved is None:
        print(f"{event}: not saved")
        continue
    html = saved.read().decode("utf-8")
    written = [str(line) for line in people_lines(BeautifulSoup(html, "lxml"))]
    as_written = [line for line in written if line in html]
    print(f"{event}: {len(written)} line(s) about people, {len(as_written)} found as written")
    if cut and as_written:
        pattern = re.compile("|".join(re.escape(line) for line in as_written))
        print(f"   cut: {store.remove_text(url, pattern, '', WHY)}")
    if cut:
        again = people_lines(BeautifulSoup(store.load(url).read().decode("utf-8"), "lxml"))
        print(f"   left after the cut: {len(again)}")
