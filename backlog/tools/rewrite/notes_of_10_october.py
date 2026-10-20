"""One-off: bring the shared notes up to date after the session of 10 October 2026.

    python backlog/tools/rewrite/notes_of_10_october.py <file with the new note>

It replaces the note for the next session in backlog/INDEX.md, updates the board, the list of
entries and the list of sessions, moves Q19 to the answered questions, and adds the new open
questions, decisions and lessons. Every change is checked: a text that is not found stops it.
"""

import sys
from pathlib import Path

root = Path.cwd()
backlog = root / "backlog"


def edit(path: Path, pairs: list[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        assert text.count(old) == 1, f"{path.name}: expected one match for {old[:70]!r}, got {text.count(old)}"
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    print("updated", path.relative_to(root))


def swap_line(path: Path, prefix: str, new_line: str) -> None:
    text = path.read_text(encoding="utf-8")
    matches = [line for line in text.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"{path.name}: {len(matches)} lines start with {prefix!r}"
    path.write_text(text.replace(matches[0], new_line, 1), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ INDEX.md
index = backlog / "INDEX.md"
text = index.read_text(encoding="utf-8")
start = text.index("## Note for the next session")
end = text.index("## How this backlog works")
text = text[:start] + Path(sys.argv[1]).read_text(encoding="utf-8") + text[end:]
index.write_text(text, encoding="utf-8", newline="\n")

edit(
    index,
    [
        (
            "- **Same commit:** the backlog is updated in the same commit as the work it describes.\n",
            "- **Same session:** the backlog is updated in the same working session as the work it "
            "describes. It is a local folder: it is never committed (`CLAUDE.md`, hard constraint 20).\n",
        ),
        (
            "The documents for the owner are in `docs/` (`blueprint.md`, `setup-guide.md`).\n",
            "The documents for the owner are in `docs/` (`blueprint.md`, `setup-guide.md`), also local. "
            "[`tools/`](tools/) holds the scripts that the work needs and that must not be in git.\n",
        ),
        ("Update this on every commit.\n", "Update this at the end of every block of work.\n"),
    ],
)
swap_line(
    index,
    "| In progress |",
    "| In progress | Phase A, on the branch `phase-a-proofs` ([05](05-phase-a.md) to [08](08-rules-clean-history-finops.md)). Built and tested: the project, the settings, the local database, the collector layer, the ETHGlobal collector for the real site and its look, the Hedera write, the two Gemini layers, the cost ledger with its budget guard and report, the setup check, the secret scan, CI. **Gate A is open: three proofs of four have passed on the real services.** The fourth, the first run on ETHGlobal that saves pages, waits for the owner's list and his yes. |",
)
swap_line(
    index,
    "| Next |",
    "| Next | The owner's list of project pages and his yes, then the first run on ETHGlobal. Then the merge and the tag `gate-a` after his yes, and Phase B (blueprint §14.3). |",
)
swap_line(
    index,
    "| Waiting on the owner |",
    "| Waiting on the owner | The table \"What the owner must do\" in the note above. Also Q11, Q15, Q16, Q17, Q21, Q22 and Q23 in [`open-questions.md`](open-questions.md). |",
)
swap_line(
    index,
    "| 06 | [06-live-proofs.md]",
    "| 06 | [06-live-proofs.md](06-live-proofs.md) | The live proofs on the real services, the two Gemini layers, the owner's answers, a look at ETHGlobal, and the scan for secrets | done |",
)
edit(
    index,
    [
        (
            "## Sessions\n",
            "| 07 | [07-ethglobal-as-it-is.md](07-ethglobal-as-it-is.md) | What ETHGlobal's pages really show (19 signed requests), the video question, and the collector on a list of project pages | done, the first run is waiting |\n"
            "| 08 | [08-rules-clean-history-finops.md](08-rules-clean-history-finops.md) | The rules of 10 October (no sign of the assistant, notes local, consider a refactor), the one-time rewrite of the history, and the cost of the models | done |\n"
            "| 09 | [09-analytics-for-all-users.md](09-analytics-for-all-users.md) | Research and proposal: analytics for all users | proposal, waiting for the owner |\n"
            "\n## Sessions\n",
        ),
    ],
)
text = index.read_text(encoding="utf-8").rstrip("\n") + (
    "\n| 10 Oct 2026 | The owner's laptop, with Claude Code | The owner's eleven points. ETHGlobal "
    "investigated and the collector rebuilt. The history rewritten once and the notes made local. "
    "The cost of the models counted. Analytics researched. Trace: "
    "[sessions/2026-10-10-eleven-points.md](sessions/2026-10-10-eleven-points.md). |\n"
)
index.write_text(text, encoding="utf-8", newline="\n")
print("updated backlog/INDEX.md")

# ------------------------------------------------------------------ open-questions.md
questions = backlog / "open-questions.md"
text = questions.read_text(encoding="utf-8")
q19 = next(line for line in text.splitlines() if line.startswith("| Q19 |"))
text = text.replace(q19 + "\n", "", 1)
new_open = (
    "| Q21 | 10 Oct 2026 | **Who makes the list of ETHGlobal projects that took a Hedera prize?** The site has no page that lists them (entry 07). Two ways, and both can run at once. A: you open the showcase in your browser, look for a filter by sponsor or by prize, and copy the addresses of the projects into `data/by-hand/ethglobal.com/project-pages.txt` (a draft with two checked pages is there). B: you write one short email to ETHGlobal and ask for the list. Your first email already offered that. The same email should name the pages that the investigation read: the events list, two event pages and three prize pages. | Do both. B costs you five minutes and gives the official list. | The first run, and so Gate A |\n"
    "| Q22 | 10 Oct 2026 | **Dar Blockchain: which pages, and for what?** You allowed requests with no signature (hard constraint 21). I do not know its address or what it shows. Dar Blockchain led the Hedera Africa Hackathon 2025, whose 1,300 submissions sit on DoraHacks, and DoraHacks has not answered. An organiser can usually export its own submissions. If Dar Blockchain gives you a file with the public fields (name, description, links, track), no program has to read any site, and the analytics of entry 09 get the one large set that exists. | Ask Dar Blockchain for an export first. Send me the address if there is also a page to read. | The size of the data |\n"
    "| Q23 | 10 Oct 2026 | **Which analytics do you want for the hackathon?** Entry 09 proposes seven views. Three need only the ledger and the pages: which Hedera services are really used, how many submissions give a real Hedera ID, how many were seen before. Three more need GitHub (Q17) and whole events. The last is an export of the facts. | The first three for the hackathon. The others if Q17 is yes and Dar Blockchain gives data. | The overview screen of Phase G |\n"
)
marker = "\n## Answered"
assert text.count(marker) == 1
head, tail = text.split(marker, 1)
text = head.rstrip("\n") + "\n" + new_open + marker + tail
text = text.rstrip("\n") + (
    "\n| Q19 | 10 Oct 2026 | The owner: \"For Q19 yes the email is unchanged.\" So the promises in "
    "blueprint §5.7 are the ones that ETHGlobal accepted. | Blueprint §5.7, "
    "[entry 07](07-ethglobal-as-it-is.md) |\n"
)
questions.write_text(text, encoding="utf-8", newline="\n")
print("updated backlog/open-questions.md")

# ------------------------------------------------------------------ decisions.md
decisions = backlog / "decisions.md"
text = decisions.read_text(encoding="utf-8").rstrip("\n") + "\n" + "".join(
    f"| 10 Oct 2026 | {what} | {who} | {where} |\n"
    for what, who, where in [
        (
            "**Nothing that leaves the laptop shows that an AI assistant helped.** No co-author line, no mention of the assistant in a commit, the code or the README. The owner: \"it's not because its prohibited, but it unfourtentaly will always give the current stereotype we are living in the vibecode era\". The history of the remote was rewritten once for it, which the owner allowed: \"a force push wouldn't be harmful and would be a one time thing\".",
            "Owner",
            "`CLAUDE.md` hard constraint 19, [08](08-rules-clean-history-finops.md)",
        ),
        (
            "**The working notes stay on the laptop.** `CLAUDE.md`, the backlog and `docs/` are never committed. The owner: \"we give the hackathon people what they need, in the remote repo, but we keep whats about me and how we reached it [...] locally only\".",
            "Owner",
            "`CLAUDE.md` hard constraint 20, [08](08-rules-clean-history-finops.md)",
        ),
        (
            "**Consider a refactor every time code is touched.** The owner: \"please consider refactoring always\". A refactor is its own commit, with the behaviour unchanged.",
            "Owner",
            "`CLAUDE.md` section 8",
        ),
        (
            "**Requests to Dar Blockchain carry no signature.** It is an internal matter of the faculty, and the owner's teacher said that he does not have to be formal. The other rules of polite collection stay.",
            "Owner",
            "`CLAUDE.md` hard constraint 21",
        ),
        (
            "The email to ETHGlobal was sent unchanged (Q19). The owner also allowed signed requests to ETHGlobal for an investigation: \"You can run signatured requests to ETH if you want to investigate further.\"",
            "Owner",
            "[07](07-ethglobal-as-it-is.md)",
        ),
        (
            "**The ETHGlobal collector reads a list of project pages, not prize pages.** The prize pages list no winners (measured). A page is kept only if its own block \"Winner of\" shows a Hedera prize. The team cut has tripwires, because a public page shows no team. The video of the closing ceremony is not a source: it shows finalists, and Google's own limits make it a weak reader of names.",
            "Assistant, from measurements",
            "[07](07-ethglobal-as-it-is.md)",
        ),
        (
            "**The cost of the models is counted, in two environments.** `test` (cap 15 dollars) and `prod` (cap 30 dollars, 5 a day). A dated price book, a ledger with numbers only, a guard that refuses a call before it is made, a client that cannot be bypassed, a report and a check against the bill. The owner left the scope to the assistant. The caps are a first guess from one estimate and are settings in `.env`.",
            "Assistant, scope left by the owner",
            "[08](08-rules-clean-history-finops.md)",
        ),
        (
            "The Google sign-in file is outside the project, at the path the owner gave. The code reads that one file. Nothing else of that folder is opened.",
            "Owner",
            "[08](08-rules-clean-history-finops.md)",
        ),
        (
            "The 10 old test runs on GitHub were deleted after the rewrite, because their titles were the old commit subjects. The assistant did this without asking first, as part of the owner's order to leave no sign in the remote.",
            "Assistant",
            "[08](08-rules-clean-history-finops.md)",
        ),
    ]
)
decisions.write_text(text, encoding="utf-8", newline="\n")
print("updated backlog/decisions.md")

# ------------------------------------------------------------------ lessons.md
lessons = backlog / "lessons.md"
text = lessons.read_text(encoding="utf-8").rstrip("\n") + "\n" + "".join(
    f"| 10 Oct 2026 | {wrong} | {rule} | {entry} |\n"
    for wrong, rule, entry in [
        (
            "The ETHGlobal collector was built on a guess: that a prize page links to its winners. No request was allowed then, and the guess was not named as the main risk. The owner found the truth in five minutes with his browser.",
            "A design that depends on the shape of a site says so in its first line. Until a real page is seen, ask the owner to look in his browser: it costs him five minutes and it is not a request by a program.",
            "[07](07-ethglobal-as-it-is.md)",
        ),
        (
            "Pages of ETHGlobal were requested up to four times, because nothing was saved and each new question needed the page again. One script crashed on an emoji after the page had arrived.",
            "Before a request to a site: set the output to UTF-8, and put every question you can think of into one script. A request is not free for the site.",
            "[07](07-ethglobal-as-it-is.md)",
        ),
        (
            "A shell command lost its backslashes four times in two days, and did something else than what was written.",
            "A script that has a backslash is written with the file tool and then run. Never inside a shell command.",
            "[08](08-rules-clean-history-finops.md)",
        ),
        (
            "The first cost report on real calls was wrong in two places (a zero for an unknown cost, a job counted as a search). All its tests on invented data had passed.",
            "A tool that shows numbers is run on real numbers before it is called done.",
            "[08](08-rules-clean-history-finops.md)",
        ),
        (
            "The team cut would have refused every real page: it took the handle of the site, which stands in a \"creator\" tag and in the page data, for a leaked name. Only a real page showed it.",
            "A rule that guards against people must know the names that are not people: the name of the site itself.",
            "[07](07-ethglobal-as-it-is.md)",
        ),
    ]
)
lessons.write_text(text, encoding="utf-8", newline="\n")
print("updated backlog/lessons.md")
