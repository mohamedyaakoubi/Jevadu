"""One time: cut the email address of a person out of the saved page that holds one.

The owner decided on 11 October 2026: "if its people then hide them". One saved page holds an
address at a public mail service in the data of the page. This tool takes it out with the store's
own way (RawStore.remove_text), which writes the reason and the old fingerprint next to the page.

It prints counts only: never an address, never the page. It changes a file only when every
email-like string in it is an address at a public mail service. Anything else is left for a
person to look at.

    .venv/Scripts/python.exe backlog/tools/ethglobal/cut_address_from_saved_pages.py          (look)
    .venv/Scripts/python.exe backlog/tools/ethglobal/cut_address_from_saved_pages.py --cut    (do it)
"""

from __future__ import annotations

import sys
from collections import Counter

from hackathon_memory.collect.ethglobal import data_paths
from hackathon_memory.collect.rawstore import RawStore
from hackathon_memory.parse.ethglobal_page import read_project_page
from hackathon_memory.parse.people import ADDRESS, HIDDEN_ADDRESS
from hackathon_memory.settings import Settings

MAIL_SERVICES = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com",
    "proton.me", "protonmail.com", "icloud.com", "me.com", "aol.com", "gmx.com", "mail.com",
}  # fmt: skip
WHY = (
    "An email address of a person stood in the data of the page. The maintainer decided on "
    "11 October 2026 that people are hidden."
)

do_it = sys.argv[1:] == ["--cut"]
store = RawStore(data_paths(Settings()).raw_dir)
found: Counter[str] = Counter()
changed = 0
for saved in store.saved():
    text = saved.read().decode("utf-8")
    domains = [match.group(0).rsplit("@", 1)[1].lower() for match in ADDRESS.finditer(text)]
    if not domains:
        continue
    kinds = ["a public mail service" if d in MAIL_SERVICES else "another kind of name" for d in domains]
    found.update(kinds)
    if set(kinds) != {"a public mail service"}:
        print("a page holds an email-like string of another kind: left alone, a person must look")
        continue
    if not do_it:
        continue
    # Try it in memory first: the parser must read the changed page exactly as before.
    before = read_project_page(saved.read(), saved.url)
    planned = ADDRESS.sub(HIDDEN_ADDRESS, text).encode("utf-8")
    if read_project_page(planned, saved.url) != before:
        print("a page would be read differently after the cut: left alone, a person must look")
        continue
    removed = store.remove_text(saved.url, ADDRESS, HIDDEN_ADDRESS, WHY)
    after_page = store.load(saved.url)
    assert after_page.read() == planned
    assert after_page.meta["removed"][-1]["matches"] == removed
    changed += 1
    print(f"one page: {removed} address(es) cut out, and the parser reads the page as before")

print("email-like strings in the saved pages:", dict(found) or "none")
print("pages changed:", changed, "" if do_it else "(only a look: start with --cut to do it)")
left = sum(len(ADDRESS.findall(saved.read().decode("utf-8"))) for saved in store.saved())
print("email-like strings left in the saved pages:", left)
print("pages with a record of a removal:", sum(1 for saved in store.saved() if saved.meta.get("removed")))
