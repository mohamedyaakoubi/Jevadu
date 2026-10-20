#!/bin/sh
# A rehearsal of the one-time rewrite of the history, on a throw-away clone.
# The real repository is NOT touched and nothing is pushed.
#
#   sh backlog/tools/rewrite/rehearse.sh            from the project folder
#   sh backlog/tools/rewrite/rehearse.sh --lines    also print every line that is still flagged
#
# It clones the repository into the temp folder, removes the notes (CLAUDE.md, backlog/, docs/)
# from every commit, cleans the wording (sanitize.py), strips the co-author lines, then checks
# EVERY commit of the result with the rules of the local guard, and runs the lint and the tests
# at its tip. Exit code 0 means: ready.
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
HERE="$REPO/backlog/tools/rewrite"
PY="$REPO/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$REPO/.venv/bin/python"
CLONE="${TMPDIR:-/tmp}/hackathon-memory-rewrite-clone"

rm -rf "$CLONE"
git clone --quiet --no-local "$REPO" "$CLONE" || exit 9
cd "$CLONE" || exit 9
git branch --quiet main origin/main 2>/dev/null
git remote remove origin
echo "--- before: $(git rev-list --count --all) commits"
PYTHONIOENCODING=utf-8 "$PY" "$HERE/rewrite.py" "$CLONE" 2>&1 | tail -2
echo "--- after: $(git rev-list --count --all) commits. Branches:"
git branch -v | cut -c1-100
GUARD_PATH="$REPO/backlog/tools/hooks/check_public.py" PYTHONIOENCODING=utf-8 \
    "$PY" "$HERE/verify.py" "$CLONE" "$@"
CHECK=$?
different=0
for f in $(git ls-files); do
    cmp -s "$f" "$REPO/$f" || { echo "  differs from the working folder: $f"; different=$((different + 1)); }
done
echo "--- files at the rewritten tip: $(git ls-files | wc -l); different from the working folder: $different"
cp "$REPO/.env" .env
"$PY" -m ruff check . > /dev/null 2>&1; LINT=$?
"$PY" -m ruff format --check . > /dev/null 2>&1; FMT=$?
PYTHONPATH=src "$PY" -u -m pytest -q -p no:cacheprovider -W error::DeprecationWarning \
    -o faulthandler_timeout=120 > "$CLONE/../hackathon-memory-rewrite-tests.txt" 2>&1; TESTS=$?
rm -f .env
echo "--- at the rewritten tip: lint $LINT, format $FMT, tests $TESTS ($(tail -1 "$CLONE/../hackathon-memory-rewrite-tests.txt"))"
echo "--- the clone is in: $CLONE"
[ "$CHECK" = 0 ] && [ "$different" = 0 ] && [ "$LINT" = 0 ] && [ "$FMT" = 0 ] && [ "$TESTS" = 0 ]
