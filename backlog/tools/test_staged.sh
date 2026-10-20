#!/bin/sh
# Run the lint and the whole test suite on EXACTLY what is staged, without touching the working
# folder. It builds a temporary git worktree at HEAD, applies the staged change there, runs the
# checks, and removes the worktree. A commit is made only if this passes.
#
#   sh backlog/tools/test_staged.sh            exit code 0 = the staged state is good
#
# Why: one test reads only the files that git tracks. A run in the working folder before
# "git add" can pass on a state that fails after the commit (lesson of 10 October 2026).
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$REPO/.venv/bin/python"
OUT="${TMPDIR:-/tmp}"
WT="$OUT/hackathon-memory-staged-worktree"

cd "$REPO" || exit 9
git worktree remove --force "$WT" >/dev/null 2>&1
rm -rf "$WT"
git diff --cached --binary > "$OUT/hackathon-memory-staged.patch"
if [ ! -s "$OUT/hackathon-memory-staged.patch" ]; then echo "nothing is staged"; exit 9; fi
git worktree add --quiet --detach "$WT" HEAD || exit 9
cd "$WT" || exit 9
git apply --index "$OUT/hackathon-memory-staged.patch" || { echo "the staged patch does not apply"; exit 9; }
cp "$REPO/.env" .env
echo "files in the staged change: $(git diff --cached --name-only | wc -l)"
"$PY" -m ruff check . > "$OUT/hackathon-memory-staged-lint.txt" 2>&1; LINT=$?
"$PY" -m ruff format --check . >> "$OUT/hackathon-memory-staged-lint.txt" 2>&1; FMT=$?
PYTHONPATH=src "$PY" -u -m pytest -q -p no:cacheprovider -W error::DeprecationWarning \
    -o faulthandler_timeout=120 > "$OUT/hackathon-memory-staged-tests.txt" 2>&1; TESTS=$?
rm -f .env
cd "$REPO" || exit 9
git worktree remove --force "$WT" >/dev/null 2>&1
rm -rf "$WT"
echo "lint: $LINT  format: $FMT  tests: $TESTS  ->  $(tail -1 "$OUT/hackathon-memory-staged-tests.txt")"
[ "$LINT" = 0 ] && [ "$FMT" = 0 ] && [ "$TESTS" = 0 ]
