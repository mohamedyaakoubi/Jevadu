"""Stage only some changes of a file: the hunks that contain at least one of the given texts.

    stage_hunks.py <file> <text> [<text> ...]

It uses plain `git diff -U0` and `git apply --cached`, so nothing is rewritten and nothing is lost:
the rest of the changes stay in the working tree. It prints how many hunks it staged.

A hunk with no context is placed by its NEW line number: git apply starts looking at that line,
because it expects the earlier hunks of the patch to be in place, and a hunk with no context
matches anywhere. So when an earlier hunk is left out, the new line numbers of the kept hunks are
computed again from their old ones. On 20 October 2026 a kept insertion of two lines landed 18
lines too low, inside other rules, because a left-out hunk above it added 18 lines.
"""

import re
import subprocess
import sys

HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def renumbered(hunks: list[str]) -> list[str]:
    """The hunks with their new line numbers counted from the kept hunks only."""
    out, shift = [], 0
    for hunk in hunks:
        found = HEADER.match(hunk)
        start, removed = int(found[1]), int(found[2] if found[2] is not None else 1)
        added = int(found[4] if found[4] is not None else 1)
        if removed == 0:  # an insertion: after the old line `start`
            new_start = start + 1 + shift
        elif added == 0:  # a deletion: after the line before it, in the new file
            new_start = start - 1 + shift
        else:
            new_start = start + shift
        out.append(HEADER.sub(f"@@ -{start},{removed} +{new_start},{added} @@", hunk, count=1))
        shift += added - removed
    return out


file, needles = sys.argv[1], sys.argv[2:]
# Bytes in, bytes out: in text mode Windows would turn the line endings into CRLF and the patch
# would no longer match the file.
diff = subprocess.run(
    ["git", "diff", "-U0", "--", file], capture_output=True, check=True
).stdout.decode("utf-8")
parts = re.split(r"(?m)^(?=@@ )", diff)
header, hunks = parts[0], parts[1:]
chosen = [h for h in hunks if any(n in h for n in needles)]
if not chosen:
    print(f"no hunk of {file} contains any of {needles}")
    raise SystemExit(1)
patch = header + "".join(renumbered(chosen))
subprocess.run(
    ["git", "apply", "--cached", "--unidiff-zero", "-"],
    input=patch.encode("utf-8"),
    check=True,
)
print(f"{file}: staged {len(chosen)} of {len(hunks)} hunk(s)")
