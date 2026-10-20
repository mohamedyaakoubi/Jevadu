# 08. New rules, a clean history, and the cost of the models

- **Date:** 10 October 2026
- **Who:** the owner (Mohamed Yaakoubi), with Claude Code
- **Branch:** `phase-a-proofs`
- **Status:** done. The history of the remote was rewritten once, the notes are local, the cost of the models is counted. CI is green on `4982fa9`.

This file stays on the laptop (`CLAUDE.md`, hard constraint 20). It is never committed.

## Goal

The owner sent eleven points and said: "my points aren't really sorted in priority, you decide priority". This entry covers five of them: no sign of the assistant in the remote (3), always consider a refactor (2), the cost of the models (1), the Google sign-in file (5), and what `HEDERA_TOPIC_ID` and `DATABASE_URL` are (10). ETHGlobal (7, 8, 11) is entry 07. The analytics (4) are entry 09. Dar Blockchain (9) and the GitHub token (6) are in the open questions.

## The order that was chosen, and why

1. The standing rules first, because they change how every later commit is made.
2. ETHGlobal second, because nothing real can go through the tool without a source.
3. The clean history third, prepared on a copy before the remote was touched.
4. The cost of the models.
5. The analytics research.

## New rules (in `CLAUDE.md`)

| Rule | The owner's words |
|---|---|
| Hard constraint 19: nothing that leaves the laptop shows that an AI assistant helped | "no claude co authoried signature is allowed for future commits/pushes and remove any 'with an AI coding assistant.' usage, it's not because its prohibited, but it unfourtentaly will always give the current stereotype we are living in the vibecode era" |
| Hard constraint 20: the working notes stay on the laptop | "we keep whats about me and how we reached it [...] locally only for claude only" |
| Hard constraint 21: requests to Dar Blockchain carry no signature | "my teacher told me you dont have to be formal so keep it anonymous, we only be strict with global companies that we sent emails to" |
| Working style: consider a refactor every time code is touched | "please consider refactoring always if you are not instructed for it already through claude.md" |
| Launch gate 12: the remote shows no sign of the assistant and no note | follows from 19 and 20 |

The tool that asks for a "Co-Authored-By" line in every commit is overruled by the owner's rule. The line is not added.

## The clean history

**What was wrong.** All 35 commits carried a "Co-Authored-By: Claude" line, so GitHub listed Claude as a contributor. The repository held `CLAUDE.md`, the backlog and `docs/`, which show how the owner works with the assistant. 191 lines in 54 other files pointed at those notes ("hard constraint 9", "backlog entry 05", "the owner"). The README said "with an AI coding assistant".

**What was done.**

| Step | Result |
|---|---|
| A guard on this laptop only (`.git/hooks`: commit-msg, pre-commit, pre-push) | It refuses a message, a staged change or a push that shows a sign of the assistant or a note. Tested with five planted cases. It refused the old history with 236 findings |
| The notes excluded in `.git/info/exclude` (not in `.gitignore`) | The remote does not even name them |
| The wording of the public files cleaned in a normal commit | "design rule N", "design N.M", "the maintainer". 48 files. The README now lists the design rules and the promises to the sites, so the numbers in the comments can be looked up |
| A rehearsal on a copy (`backlog/tools/rewrite/rehearse.sh`) | 45 commits became 36. No flagged line in any file of any commit, no flagged message, one identity. The tip was the same, byte for byte, as the public files of the working folder. Lint and 450 tests passed on it |
| Backups, on this laptop only | `.local-backup/old-history-20261010.bundle` (the whole old history, checked with `git bundle verify`) and `.local-backup/notes-20261010.tgz` |
| One forced push, with a lease on the old commits | `main` 1dd2093 to cf93bb1, `phase-a-proofs` db5a37d to c9c368b |
| The local repository moved to the new history | With `git reset --mixed`, so no file of the working folder was touched. The notes are on disk and no longer tracked |
| The 10 old test runs deleted on GitHub | Their titles were the old commit subjects |

**What GitHub shows now.** `main`: 3 commits. `phase-a-proofs`: 37 commits. No co-author line, one author. `CLAUDE.md`, `backlog` and `docs` answer "not found". CI is green on the new tip.

**What was lost, and what was not.** The 9 commits that only touched notes are not in the new history (09e6458, 1dd2093, 214d6de, 621b4c3, 76d7ef5, b46280d, db5a37d, e77b0ad, fa31b85). Their content is in the notes on disk, and their history is in the bundle. Six messages were written again by hand, because they would have said something false once the notes were gone. Every commit number changed. The map from old to new numbers is in `backlog/tools/rewrite/commit-map-20261010.txt`, and the notes were updated with it.

**What is still traceable.** An old commit still answers on GitHub when it is asked for by its exact number. Nothing links to it. GitHub removes such commits in its own time, and only its support can force it. The owner said that this does not matter to them.

**The notes exist once.** They are no longer on GitHub. If the laptop is lost, they are lost. The owner should copy the project folder to a safe place.

## The cost of the models (FinOps)

"FinOps" means: knowing what a service costs, call by call, and keeping it inside a budget.

The owner asked for it "one in testing mode and one in prod (aka hackathon ready)", and left the scope to the assistant. The scope that was chosen:

| Part | What it does |
|---|---|
| Price book (`finops/prices.py`) | One line for each model and each day a price begins. Gemini 3.8 Flash doubles on 1 January 2027. Gemini 3.1 Pro costs more above 200,000 tokens. Cached input costs a tenth, a batch job costs half. A model that is not in the book has no cost: it is never guessed |
| Ledger (`finops/calls.py`, table `llm_calls`) | One line for each call: model, tokens, time, cost. Numbers only. A test checks that the table has no column for text |
| Two environments | `test` is the work before the tool is shown. `prod` is the tool while people use it. `LLM_ENVIRONMENT` in `.env` |
| Budget guard (`finops/budget.py`) | `test` has one cap (15 dollars). `prod` has a cap (30 dollars) and a cap for one day (5 dollars). A call whose worst case could go over is not made |
| Meter (`finops/meter.py`) | A client that stands in for the Google client. No code that asks a model changes. A method that costs money and that the meter does not know is refused |
| Report (`python -m hackathon_memory.finops report`) | By use, by day, the cost of one project page and of one search, second attempts, the share of thinking, the same tokens with the other model, an announced change of price, the days the budget lasts |
| Check against the bill (`reconcile`) | Our own count against the amount on Google's bill |

**Prices, read on 10 October 2026** from Google's page "Gemini Developer API pricing" (last updated 9 October 2026). The price page of the Agent Platform could not be read by the tool. Google's search summary says its global prices are the same.

**The first real numbers**, three calls on an invented text of about 90 words:

| Call | Tokens in | Tokens out | Thinking | Time | Cost |
|---|---|---|---|---|---|
| Rewrite, Gemini 3.1 Pro, HIGH | 1,729 | 465 | 1,641 | 21.3 s | 0.0287 dollars |
| Search, Gemini 3.8 Flash, HIGH | 1,729 | 445 | 1,759 | 13.9 s | 0.0096 dollars |
| Embedding, gemini-embedding-001 | 5 | | | 11.8 s | not known |

Thinking was 79% of the output tokens. On 9 October the same kind of search call thought 5,748 tokens, took 46.1 seconds and cost 0.0246 dollars. So one call of Flash at HIGH can cost between 1 and 2.5 cents and take between 14 and 46 seconds. Two calls are not a measurement. The report will show the spread when there are more.

**What the first real report showed about the report itself.** Two flaws, both fixed with a test: an embedding line said "$0.0000" where the truth is "cost not known", and "one run" mixed a search with a job.

**What it does not do yet.** It is not wired into the proofs, so `python -m proofs.google_models` is not counted. The website does not exist, so `prod` has no call. The price of gemini-embedding-001 is not known: Google's price page no longer lists that model, and it lists Gemini Embedding 2. That is a sign to test the newer model in Phase D.

## Refactors

| Refactor | Why |
|---|---|
| The model code takes its price from the price book (`0866e13`) | Two tables of prices would have drifted apart |
| robots.txt is read in one place (`4982fa9`) | The collector and the look each decided on their own what a 404 means |
| Comments cite the design rules of the README (`c9c368b` in the new history) | A comment must point at something a reader can find |

Left as they are, on purpose: `setup_check.py` does many things in one file, and `finops/report.py` has one long function that builds the text. Neither was in the way of a change today.

## The owner's other points

- **The Google sign-in file (5).** `.env` now names `C:/Users/MSI/Desktop/DATAMUNDI/application_default_credentials.json`. One line of `.env` was changed and the 46 others were checked byte for byte. The setup check says "outside the project folder". One real embedding call worked with it. Only this one file of that folder is read, and only by the code.
- **`HEDERA_TOPIC_ID` (10).** The address of the channel on Hedera where the tool will write its register (Phase F). No code reads it yet. The proof of Gate A creates its own topic at each run. Leave it empty.
- **`DATABASE_URL` (10).** One line that replaces the four `POSTGRES_` lines, for a database that is not the local one. Leave it empty.
- **The GitHub token (6).** It is set. No request was sent to GitHub with it: the owner has not said yes to Q17 yet.

## What went wrong

1. **A shell command lost its backslashes twice more.** The lesson was already written. Scripts with a backslash are now always written with the file tool.
2. **The first report on real calls was wrong in two places.** Fake data had not shown it. A tool that shows numbers must be run on real numbers before it is called done.
3. **A test helper rounded money**, and two assertions failed by a millionth of a dollar. Fixed in the test.

## What this does not prove

- That GitHub's list of contributors no longer shows Claude. GitHub computes that list in its own time. The commits no longer hold the line, so the list must follow.
- That no trace is left in a place that was not looked at: GitHub's activity feed shows that a branch was force-pushed.
- That the budgets are the right size. They are a guess from one estimate (about 3 dollars for 70 pages).
- That our count equals Google's bill. `reconcile` has never been run with a real amount.

## Next

1. The owner copies the project folder to a safe place.
2. The owner reads Google's bill once and runs `reconcile`.
3. The meter is wired into the first job that calls a model many times (Phase D), and into the proofs.

## Commits

In the new history: `bcb3517` the team cut. `402f502` the collector on project pages. `c966cf8` the price book. `0866e13` the price refactor. `92a9cc3` the ledger, the guard and the meter. `ca57723` the report. `d71abdc` and `9f00851` the two fixes of the report. `010ce86` the README. `c9c368b` two long lines (in the old history this was the commit that cleaned the wording of 48 files; after the rewrite every older commit is already clean, so only two lines are left in it). `4982fa9` robots.txt in one place.

## Later on 10 October 2026: the Google proof counts its calls

The third point of "Next" above is done for the proofs.

- `ed87c00`: `proofs/google_models.py` wraps its client in the meter. Each call of the proof leaves a line in `llm_calls`, with the purpose `proof` and one run id. If the ledger cannot be written, the proof stops before the first call ("Blocked").
- `862cb04`: a refactor. The cost commands open the ledger with the same function as the proof.
- `7f0e4a5`: the live result, `proofs/results/20261010T155247Z-google-models.json`. Passed, 5 calls in the ledger. The rewrite call took 21.4 seconds and cost 3.1 cents. The search call took 16.5 seconds and cost 1.2 cents.

The owner said that they need no copy of the project folder: "no need to backup the project folder, no worries." So the first point of "Next" is closed.
