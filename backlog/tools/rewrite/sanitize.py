"""The wording rules of the one-time rewrite of the history (constraints 19 and 20).

Used by rewrite.py on every text file of every commit, and on every commit message. The rules turn
references to private notes into neutral wording, and remove the lines that cannot be made neutral.
They are applied in order. Run rewrite.py and verify.py to see what is left.
"""

from __future__ import annotations

import re

RULES: list[tuple[re.Pattern[str], str]] = []


def rule(pattern: str, replacement: str, flags: int = 0) -> None:
    RULES.append((re.compile(pattern, flags), replacement))


M = re.MULTILINE

# ---------------------------------------------------------------- the README of the repository
# Rows of the Documents table that point at private notes: they go.
rule(r"^\| \[`docs/blueprint\.md`\]\(docs/blueprint\.md\) \|[^\n]*\n", "", M)
rule(r"^\| \[`docs/setup-guide\.md`\]\(docs/setup-guide\.md\) \|[^\n]*\n", "", M)
rule(r"^\| \[`CLAUDE\.md`\]\(CLAUDE\.md\) \|[^\n]*\n", "", M)
rule(r"^\| \[`backlog/INDEX\.md`\]\(backlog/INDEX\.md\) \|[^\n]*\n", "", M)
rule(r"^\| \[`backlog/[^`]*`\]\([^)]*\) \|[^\n]*\n", "", M)
rule(r"^\| \[`docs/[^`]*`\]\(docs/[^)]*\) \|[^\n]*\n", "", M)
# A Documents section that has no row left goes too.
rule(r"## Documents\n\n\| File \| What it is \|\n\|---\|---\|\n\n", "", M)
rule(r"## Documents\n\n\| File \| What it is \|\n\|---\|---\|\n$", "", M)
# The sentence that says how the code was written.
rule(r", with an AI coding assistant\.", ".")
rule(r" with an AI coding assistant", "")
# Sentences that point at the private notes.
rule(r"\s*The plan for (?:them|it) is in \[`docs/blueprint\.md`\]\(docs/blueprint\.md\)[^.\n]*\.", "")
rule(
    r"\s*How to get every value, step by step \([^)]*\), is in "
    r"\[`docs/setup-guide\.md`\]\(docs/setup-guide\.md\)\.",
    "",
)
rule(r"\s*\(see \[`docs/[^`]*`\]\(docs/[^)]*\)[^)]*\)", "")
rule(r"\s*See \[`docs/[^`]*`\]\(docs/[^)]*\)[^.\n]*\.", "")
rule(r" in \[`(?:docs|backlog)/[^`]*`\]\((?:docs|backlog)/[^)]*\)", "")
rule(r"\[`(?:docs|backlog)/[^`]*`\]\((?:docs|backlog)/[^)]*\)", "the project notes")

# ---------------------------------------------------------------- citations of the private notes
# "(backlog entry 05)", "(Backlog entry 05, lessons.)", "(backlog 05\nand 06)"
rule(r"\s*\([Bb]acklog (?:entry )?\d+(?:\s+and\s+\d+)?(?:,[^)]*?)?\.?\)", "")
# "(found on the second live run, backlog entry 06)"
rule(r",? [Bb]acklog (?:entry )?\d+(?:\s+and\s+\d+)?(?=\))", "")
rule(r"[Rr]ead backlog entry \d+ and relax the guard", "read its source again and relax the guard")
rule(
    r"The trap of backlog \d+\. If this test fails, the library changed: read the entry again\.",
    "A trap of the library. If this test fails, the library changed: read its source again.",
)
rule(r"\(blueprint 15, and the first item of backlog/INDEX\.md\)", "(design 15)")

# ---------------------------------------------------------------- the private rules file
rule(r"\(`CLAUDE\.md`, ", "(")
rule(r"CLAUDE\.md,? hard constraints", "design rules")
rule(r"CLAUDE\.md,? hard constraint", "design rule")
rule(r"\s*\(CLAUDE\.md,? section \d+\)", "")
rule(r"CLAUDE\.md section 6 says to ask the owner first", "the maintainer decides first")
rule(r"CLAUDE\.md,? section \d+:", "Design rule:")
rule(r"\s*\(CLAUDE\.md\)", "")
rule(r"`CLAUDE\.md`", "the project rules")
rule(r"\bCLAUDE\.md\b", "the project rules")
rule(r"\bHard constraints\b", "Design rules")
rule(r"\bhard constraints\b", "design rules")
rule(r"\bHard constraint\b", "Design rule")
rule(r"\bhard constraint\b", "design rule")

# ---------------------------------------------------------------- the private design notes
rule(r"\bBlueprint\b", "Design")
rule(r"\bblueprint\b", "design")
rule(r"(?<=_)blueprint\b", "design")

# ---------------------------------------------------------------- the person who owns the project
rule(r"\b(The)(\s+)owner\b", r"\1\2maintainer")
rule(r"\b(the)(\s+)owner\b", r"\1\2maintainer")

# The pronouns that the word "owner" leaves behind. The text must not guess who the person is.
rule(r"\bhis list of prize pages and his yes\b", "the list of prize pages and a yes")
rule(r"\bhis list of prize pages\b", "the list of prize pages")
rule(r"\bhis contact address\b", "the contact address")
rule(r"\bhis address and his list\b", "the address and the list")
rule(r"\bhis yes\b", "a yes")
rule(r"\bhis address\b", "the address")
rule(r"\bhis list\b", "the list")
rule(r"\bfrom his\s+browser\b", "from a browser")
rule(r"\bno work from him\b", "no manual work")
rule(r"\bthat he saves by hand\b", "saved by hand")

# ---------------------------------------------------------------- the setup guide
rule(r"step by step: docs/setup-guide\.md", "see README.md")
rule(r"docs/setup-guide\.md", "README.md")

# ---------------------------------------------------------------- names of other tools in a test
rule(r'"claude-sonnet"', '"other-vendor-model"')


def sanitize_text(text: str) -> str:
    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    return text


_TRAILER = re.compile(r"^(?:Co-Authored-By|Refs):.*(?:\n|$)", re.IGNORECASE | re.MULTILINE)
_GENERATED = re.compile(r"^.*Generated with.*(?:\n|$)", re.IGNORECASE | re.MULTILINE)


MESSAGE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\s*\(see\)"), ""),
    (re.compile(r"\s*\(see\s+backlog\s+\d+[^)]*\)"), ""),
    (re.compile(r"\s*and\s+are written in the backlog entry"), ""),
    (re.compile(r";\s*the backlog lists what it does not prove"), ""),
    (
        re.compile(r"the first question of the\s+backlog index"),
        "the question \"what is missing?\"",
    ),
    (
        re.compile(r"the README and the index are the counted number"),
        "the README is the counted number",
    ),
    (re.compile(r"The test counts in"), "The test count in"),
]


def sanitize_message(message: str) -> str:
    text = _TRAILER.sub("", message)
    for pattern, replacement in MESSAGE_RULES:
        text = pattern.sub(replacement, text)
    text = _GENERATED.sub("", text)
    text = sanitize_text(text)
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
    return text


# Messages that would say something false once the private notes are gone: written again by hand.
CURATED: dict[str, str] = {
    "737af76": "Add the licence, the README and the ignore rules\n",
    "051be5b": "Update the README and the settings example\n",
    "b9a8d24": "docs(readme): describe the state after Phase A\n",
    "f977226": "docs(readme): update the state of Phase A\n",
    "66f1193": (
        "test(collect): pin what the team cut keeps and changes\n\n"
        "The saved page is written again by the parser. The test pins that its text, its links and\n"
        "the order of its tags stay the same, and that the spacing of the markup may change.\n"
        "The README follows.\n"
    ),
    "dc75aff": "docs(readme): point the setup messages to the README\n",
    "9a2f107": (
        "chore(infra): wrap two long lines in comments\n\n"
        "A row of the table in polite.py and a sentence at the top of the model tests were\n"
        "longer than 100 characters.\n"
    ),
    "78dda99": (
        "feat(collect): add a look at ETHGlobal: three requests, nothing saved\n\n"
        "python -m hackathon_memory.collect ethglobal --look sends at most three requests, two\n"
        "seconds apart, with the tool's name and the maintainer's address: robots.txt, the first\n"
        "prize page of the list, and the first project page that it links to. It prints the shape\n"
        "of the two pages with the skeleton printer (every text only as its length, no person) and\n"
        "saves nothing to disk. robots.txt is obeyed, a refusal by the site stops it with no second\n"
        "try, and the client itself refuses a fourth request.\n\n"
        "It lets the page shape be learned without breaking design rule 18, and it shows early\n"
        "whether ETHGlobal accepts an honest request at all. It stays inside the promises of design\n"
        "5.7 (fewer pages, nothing kept) and still needs the maintainer's yes for these pages, the\n"
        "switch COLLECT_ETHGLOBAL=on, the contact address and the list. It does not need the\n"
        "checked page shape, because it is how the shape is found. It was never run on the site.\n\n"
        "--plan shows what the look would read.\n\n"
        "Tests: 317 passed (14 are new). ruff is clean. No test touches a site.\n"
    ),
}
