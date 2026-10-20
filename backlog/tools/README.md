# Tools that stay on this laptop

These files are not in git. They exist for the assistant and the owner only.

## Before every commit

```text
git add <the files of one change>
sh backlog/tools/test_staged.sh        lint and all tests on exactly what is staged
git commit                             no co-author line, no Refs line
```

`test_staged.sh` builds a temporary copy of the repository at the last commit, puts the staged change on it, and runs the checks there. The working folder is not touched. A commit is made only if it passes.

To stage only a part of a file:

```text
.venv\Scripts\python backlog/tools/stage_hunks.py <file> "<a text that is in the part to stage>"
```

## The guard (hard constraints 19 and 20)

Three hooks refuse a commit message, a staged change or a push that shows a sign of the assistant or a private note. They live in `.git/hooks`, which git never copies. In a fresh copy of the repository they are missing. Put them back before the first commit:

```text
copy backlog\tools\hooks\* .git\hooks\
```

Then add these lines to `.git/info/exclude`, so that git does not see the notes:

```text
/CLAUDE.md
/backlog/
/docs/
/.local-backup/
```

Test the guard once: `echo Co-Authored-By: x > m.txt` then `.venv\Scripts\python .git\hooks\check_public.py message m.txt` must answer "refused".

## Looking at the ETHGlobal data (`ethglobal/`)

None of these sends a request. They read `data/` and print counts, key names and names of events. They print no text of a page and nothing that could be a person. Run them from the project folder, with `PYTHONPATH=src`.

| File | What it is |
|---|---|
| `ethglobal/found_stats.py` | The file of the walk in numbers: events, sponsor ids, and which id the pages seen by hand share |
| `ethglobal/found_blocks.py` | The exact number of projects for each event, after the first walk counted the shared row twice. `--write` was used once, on 10 October 2026. |
| `ethglobal/inspect_saved.py`, `inspect_all.py` | The saved pages: sizes, the team cut, emails, links, data keys, section titles, prize lines |
| `ethglobal/inspect_at_words.py` | The words that start with @: package names or not. A word that could be a person is never printed. |
| `ethglobal/inspect_hedera_proof.py` | What the pages offer as proof of Hedera use: IDs, addresses, service names |
| `ethglobal/results-20261010.txt` | What they printed on 10 October 2026 |
| `ethglobal/seed_count.py` | How the 24 requests that were sent before the count existed were entered, once |
| `ethglobal/probe_list_page.py` | One of the throw-away scripts that read a page of the list. Kept as the record of how the shape was learned. **Do not run it: it sends a request.** |

These numbers are for planning. They are not from a test in `evals/`, so they are not shown to anybody (`CLAUDE.md`, hard constraint 6).

## The rewrite of 10 October 2026 (`rewrite/`)

The history of the remote was rewritten once, to remove the co-author lines and the notes. It must never be done again (`CLAUDE.md`, section 9.5). The tools are kept as the record of how it was done:

| File | What it is |
|---|---|
| `rewrite/sanitize.py` | The wording rules, and the six messages that were written again by hand |
| `rewrite/rewrite.py` | The rewrite of a copy, with git-filter-repo 2.47.0 (in `filter_repo_pkg/`) |
| `rewrite/verify.py` | The check of every commit of the result with the rules of the guard |
| `rewrite/rehearse.sh` | All of it on a throw-away copy, with lint and tests at the end |
| `rewrite/commit-map-20261010.txt` | The old number and the new number of every commit |
| `rewrite/update_notes.py` | Puts the new numbers into the notes |

The old history, whole, is in `.local-backup/old-history-20261010.bundle`. To look into it: `git clone .local-backup/old-history-20261010.bundle some-folder`.
