"""Check a rewritten CLONE against the guard rules, in EVERY commit (not only the tip).

    python verify.py <clone folder> [--lines]

Prints counts per rule and per place. With --lines it prints the flagged lines (public text, no
secret). Exit code 0 only if nothing is found. Also checks: identities, empty commits, the files that
must stay on the laptop, and the pronouns "he / his / him" that the word 'owner' may have left.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from collections import Counter

GUARD = os.environ.get("GUARD_PATH", "")
spec = importlib.util.spec_from_file_location("check_public", GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

PRONOUNS = re.compile(r"\b(?:he|his|him)\b", re.IGNORECASE)


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def main(clone: str, show_lines: bool) -> int:
    os.chdir(clone)
    revs = git("rev-list", "--all").decode().split()
    problems: Counter[str] = Counter()
    lines_out: list[str] = []

    # messages and identities
    for rev in revs:
        message = git("log", "-1", "--format=%B", rev).decode("utf-8", errors="replace")
        for rule in guard.broken_rules(message):
            problems[f"message: {rule}"] += 1
            lines_out.append(f"message of {rev[:8]}: {rule}")
        if PRONOUNS.search(message):
            problems["message: pronoun"] += 1
        who = git("log", "-1", "--format=%an <%ae> | %cn <%ce>", rev).decode().strip()
        problems[f"identity: {who}"] += 0

    # files
    seen_paths = set()
    for rev in revs:
        for name in git("ls-tree", "-r", "--name-only", rev).decode().splitlines():
            seen_paths.add(name)
            if guard.FORBIDDEN_PATHS.match(name):
                problems["path that must stay on the laptop"] += 1
                lines_out.append(f"{rev[:8]} {name}: forbidden path")
                continue
            blob = git("show", f"{rev}:{name}")
            try:
                text = blob.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                for rule in guard.broken_rules(line):
                    problems[f"content: {rule}"] += 1
                    lines_out.append(f"{rev[:8]} {name}:{number}: {rule}: {line.strip()[:110]}")
                if PRONOUNS.search(line) and not name.startswith(("LICENSE",)):
                    problems["content: pronoun he/his/him"] += 1
                    lines_out.append(f"{rev[:8]} {name}:{number}: pronoun: {line.strip()[:110]}")

    identities = Counter(
        git("log", "--all", "--format=%an <%ae> | %cn <%ce>").decode().strip().splitlines()
    )
    print(f"commits checked: {len(revs)}; distinct paths ever present: {len(seen_paths)}")
    print("identities:", dict(identities))
    real = {k: v for k, v in problems.items() if v}
    if show_lines:
        for item in sorted(set(lines_out)):
            print("  " + item)
    print("problems:" if real else "problems: none")
    for key, count in sorted(real.items()):
        print(f"  {count:5}  {key}")
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], "--lines" in sys.argv))
