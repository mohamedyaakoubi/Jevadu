"""Stage only some changes of a file: the hunks that contain at least one of the given texts.

    stage_hunks.py <file> <text> [<text> ...]

It uses plain `git diff -U0` and `git apply --cached`, so nothing is rewritten and nothing is lost:
the rest of the changes stay in the working tree. It prints how many hunks it staged.
"""

import re
import subprocess
import sys

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
patch = header + "".join(chosen)
subprocess.run(
    ["git", "apply", "--cached", "--unidiff-zero", "-"],
    input=patch.encode("utf-8"),
    check=True,
)
print(f"{file}: staged {len(chosen)} of {len(hunks)} hunk(s)")
