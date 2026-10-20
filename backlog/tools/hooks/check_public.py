"""Local guard (constraints 19 and 20). The working copy lives in .git/hooks; the source is
backlog/tools/hooks/check_public.py.

    check_public.py message <file>   a commit message
    check_public.py staged           the staged change
    check_public.py push             stdin: lines "<local ref> <local sha> <remote ref> <remote sha>"

It stops a commit or a push that would put a co-author line, a "generated with" line or a
mention of the assistant into a commit message, the code, the README or the other public
files, or that would push a secret or the data folder. It prints which rule was broken and
where, never a secret.

Since 20 October 2026 the working notes (the rules file, backlog/ and docs/) are committed and
pushed, by the owner's decision ("from now on they become public and pushed"). They name the
assistant and the notes by nature, so the word rules do not read them.
"""

from __future__ import annotations

import re
import subprocess
import sys

RULES = {
    "a co-author line": r"co-authored-by",
    "the name of an AI assistant or of its maker": r"\bclaude\b|anthropic",
    "a 'generated with' line": r"generated with",
    "a mention of an AI assistant": r"\bai (coding )?assistant|\bvibe[- ]?cod",
    "the word 'assistant'": r"\bassistant\b",
    "the owner's personal notes": r"context[- ]vault|\bmy vault\b|the owner's vault",
}
COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in RULES.items()}
# Words of other projects that only look like a rule word: none since the private-note rules
# were dropped on 20 October 2026. The hook keeps the place for them.
NOT_A_MENTION = re.compile(r"(?!x)x")

# The working notes: pushed since 20 October 2026, and not read by the word rules.
NOTES = re.compile(r"^(CLAUDE\.md$|backlog/|docs/)")

FORBIDDEN_PATHS = re.compile(
    r"^(data/|\.env$|\.env\.[^e]|\.env\.e[^x]|.*application_default_credentials"
    r"\.json$|.*\.pem$|.*\.p12$|.*\.pfx$)"
)


def git(*args: str, stdin: bytes | None = None) -> str:
    done = subprocess.run(
        ["git", *args], capture_output=True, input=stdin, check=False  # noqa: S603, S607
    )
    if done.returncode not in (0, 1):
        sys.exit(f"guard: git {args[0]} failed with exit code {done.returncode}")
    return done.stdout.decode("utf-8", errors="replace")


def broken_rules(text: str) -> list[str]:
    text = NOT_A_MENTION.sub(" ", text)
    return [name for name, pattern in COMPILED.items() if pattern.search(text)]


def check_message(path: str) -> int:
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = [line for line in handle.read().splitlines() if not line.startswith("#")]
    found = broken_rules("\n".join(lines))
    if found:
        print("GUARD: this commit message is refused. It shows: " + "; ".join(found) + ".")
        print("Write it again without them (constraints 19 and 20).")
        return 1
    return 0


def check_staged() -> int:
    problems: list[str] = []
    for name in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines():
        if FORBIDDEN_PATHS.match(name):
            problems.append(f"{name}: a file that must stay on this laptop")
    current = ""
    for line in git("diff", "--cached", "-U0", "--no-color").splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and not NOTES.match(current):
            for rule in broken_rules(line[1:]):
                problems.append(f"{current}: {rule}: {line[1:].strip()[:90]}")
    if problems:
        print("GUARD: this change is refused:")
        for item in problems[:25]:
            print("  " + item)
        if len(problems) > 25:
            print(f"  ... and {len(problems) - 25} more")
        return 1
    return 0


def check_push() -> int:
    zero = "0" * 40
    problems: list[str] = []
    for raw in sys.stdin.read().splitlines():
        parts = raw.split()
        if len(parts) != 4 or parts[1] == zero:
            continue  # a deletion
        local_sha = parts[1]
        messages = git("log", "--format=%H%x01%B%x02", local_sha, "--not", "--remotes")
        for block in messages.split("\x02"):
            if "\x01" not in block:
                continue
            sha, body = block.split("\x01", 1)
            for rule in broken_rules(body):
                problems.append(f"commit {sha.strip()[:8]}: message shows {rule}")
        for name in git("ls-tree", "-r", "--name-only", local_sha).splitlines():
            if FORBIDDEN_PATHS.match(name):
                problems.append(f"tree of {parts[0]}: {name} must stay on this laptop")
        for rule, pattern in RULES.items():
            # Each line that git finds ("<commit>:<path>:<text>") is read again with the same
            # rule as a commit, so that a word of another project (NOT_A_MENTION) is not a hit.
            hits = git("grep", "-I", "-i", "-E", pattern, local_sha, "--")
            found_in: set[str] = set()
            for line in hits.splitlines():
                _, path, text = (line.split(":", 2) + ["", ""])[:3]
                if path in found_in or NOTES.match(path):
                    continue
                if not COMPILED[rule].search(NOT_A_MENTION.sub(" ", text)):
                    continue
                found_in.add(path)
                problems.append(f"tree of {parts[0]}: {rule} in {path}")
    if problems:
        print("GUARD: this push is refused.")
        for item in problems[:40]:
            print("  " + item)
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        print("Nothing leaves this laptop until it is clean (constraints 19 and 20).")
        return 1
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["message"] and len(argv) == 2:
        return check_message(argv[1])
    if argv[:1] == ["staged"]:
        return check_staged()
    if argv[:1] == ["push"]:
        return check_push()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
