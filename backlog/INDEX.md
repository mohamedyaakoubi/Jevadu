# Backlog: index

A running record of every step on this project: what was done, how, the results, and what went wrong. It exists so that any later session can see where the work stopped and how each result was produced.

**Read order for a new session:** `CLAUDE.md` (the rules), then this file, then the newest entries below, then the parts of `docs/blueprint.md` that the task needs.

## Note for the next session

Written on 20 October 2026. Replace it when it is no longer true.

**20 October 2026: the owner's ten points** (entry 17). `phase-e-website` is pushed; its last
commit of code is `d20c714`.
Done: the notes are in git (the repository itself is still private); Test 3 says that a language
model made its reading, and that ten READMEs were not read blind; the FSS Campus Edition runs from 10
August to 7 November 2026; a calmer dark theme that is not green; the usual words of the field on
every screen (hard constraint 13 changed); insights in sentences above the charts. The register
stays closed.

**Waiting for the owner:**
- "redo the demo and its above points when I say so": the demo script with research, an idea that
  they understand with a linked chain, the line about consent, then the logo and the PDF pitch
  deck (points 4, 5, 6, 9). Do not start them before their word.
- Their answer on hosting (point 8): the recommendation is in the report of 20 October and in
  `decisions.md`. Nothing goes online before they write to ETHGlobal again (blueprint 5.7).
- The final questions before the register opens.
- **No Google call without their yes:** about $15 of credit in all (hard constraint 7). A local
  website for pictures or tests runs with `LLM_BUDGET_TEST_USD=0` and `LLM_BUDGET_PROD_USD=0`,
  so no call can be made.

**Next:** the owner's review layer 2 of the screens (launch gate 7); the README for judges, read
once more as a judge; the secret scan before the submission (launch gate 8). FSS submission closes
on 7 November 2026. After a restart: Docker Desktop, `docker compose up -d --wait db`, then
`python -m hackathon_memory.web`.

**Read this first**

- **Gate A passed, and Phase A is on `main`** (11 October 2026): merge commit `115d170`, tag `gate-a`, CI green. The lists proof passed for all 658 projects (`proofs/results/20261011T031418Z-lists.json`).
- **The collection on ETHGlobal is done.** 658 of 658 pages saved, 732 of the 800 requests used. No run is going on, and none is needed: a run sends nothing when nothing is missing.
- **Work goes on on `phase-e-website`** [16](16-phase-e-website.md). Phase F starts from it, on its own branch.
- **What waits for the owner:** their test of the screens (review layer 2), their word to merge Phases E and F after it, the side-by-side page of measure B after Test 2, and the split of the categories (the default until they answer). Q38: no write of their own repository for now (17 October). Q39 and Q40 are answered (live counts; no refresh). No more work on the phone layout (18 October). Test 1 is graded (their 10 and the assistant's rest, gate 4 struck on 17 October). On 17 October they asked for the basics from zero (Hedera, IDs, the mirror node, the register, the GitHub check): explain every Hedera word with an example; they do not know blockchain.
- **Talk to the owner with context and easy words** (their rule of 11 October, `CLAUDE.md` section 8): what it is about, why the tool needs it, what they should do step by step, what happens if they do nothing. Never a bare label such as "Q30".
- **Phase A is closed for ETHGlobal only.** When DoraHacks or AngelHack says yes, the collecting work of Phase A is taken up again for that site (Q8, Q13).

**How the work is done**

1. **The notes are public since 20 October 2026.** `CLAUDE.md`, this backlog and `docs/` are committed and pushed (hard constraint 20, the owner's words: "from now on they become public and pushed and yes you can put the mistakes in the backlogs so future AIs can learn from it"). Each change of the notes goes in its own `docs(notes)` commit. Write every mistake down with its lesson. What stays out of git: secrets, `data/`, any text of a collected page, and the vendored git-filter-repo in `tools/rewrite/filter_repo_pkg/` (excluded in `.git/info/exclude`).
2. **No co-author line, and no sign of the assistant in the product.** No co-author line, and no mention of the assistant in a commit message, the code, a comment, the README or `DESIGN.md` (hard constraint 19; the notes are exempt since 20 October 2026). Public text says "the maintainer", "design rule 9", "design 5.7". The tool that asks for a "Co-Authored-By" line is overruled by the owner. A guard in `.git/hooks` refuses a commit or a push that breaks this. If the hooks are missing, put them back first: [`tools/README.md`](tools/README.md).
3. **The public notes are general** (the owner, 10 October): who was asked, who agreed, how a site is read. No account of single requests, no list of small sources, nothing that only makes the owner look bad. But never a sentence that says the opposite of what happened. A sentence about the owner goes to them before it goes into the repository.
4. **Commit like this:** `git add` the files of one change, `sh backlog/tools/test_staged.sh`, then commit. The script runs the lint and all the tests on exactly what is staged.
5. **Write every script into a file first,** with the file tool, then run the file. A script inside a shell command lost its quotes or its backslashes six times in three days.
6. **The owner does not want a warning when they paste a login or a cookie.** Do not repeat or store it. If it will not be used, say so once, with the reason, and go on.

**Where things stand**

- `main` holds Phase A (`115d170`, tag `gate-a`), Phase B (`09d6d97`, tag `gate-b`), Phase C (`f2ab997`, tag `phase-c`) and Phase D (`ee82e10`, tag `phase-d`). `phase-e-website` holds the website.
- **Built in Phase B** ([13](13-phase-b-parser-and-store.md)): the parser of ETHGlobal's pages with the hiding of people, the store (migrations 0003 to 0008), the table of runs, the README of the code through GitHub's API (cleaned before saving), the ledger check and the proof rule, the embeddings (gemini-embedding-2), the search (meaning and BM25, merged), the step `all`, and the proof of Gate B.
- **The local database holds the real data:** 826 projects (the 658 pages of ETHGlobal, 135 winners of Hedera's own posts, 19 of the Africa page, 8 of Hedera18 and 6 of Hedera x AI), 651 repositories (561 READMEs), the answers of the mirror node, 826 embeddings. Proof statuses: 272 proof found, 6 dates do not fit, 4 another kind, 3 not found, 541 no ID given. All 658 full pages have a card of card-form-2 (16 to 18 October): 8,909 of the 8,931 quotes found, 4 fields dropped (`evals/results/20261018T050534Z-overview.json`). 223 single transactions in 93 projects (18 October) [15](15-phase-d-llm-fields.md), [16](16-phase-e-website.md).
- **The ends of all 14 events** are in `data/by-hand/ethglobal.com/event-ends.txt`: ten from the days of the judging, four read by the owner on the pages of the events (Q30).
- **The scope of the ETHGlobal collection** was every project that its showcase ties to Hedera: 658 pages ([11](11-all-hedera-projects-and-the-429.md)). 92 took a Hedera prize, 81 a prize of another sponsor only, 485 none. A card says which.
- **A 429 is a speed limit, not a stop order** (the owner, 11 October). The tool waits one hour and goes on five times slower, by itself. A real no still needs the owner.
- **A public design document exists:** `DESIGN.md`. If the blueprint changes something that it says, change both. Blueprint version 0.27.
- **The cost of the models is counted** ([08](08-rules-clean-history-finops.md)). On 18 October: 12.38 of the 15 dollars of `test` spent (83%); `prod` 30.02 of 30, at STOP after the cards run. One search on the website costs about 0.6 cent: 0.2 for the order by the model, 0.4 for the comparison. The website runs in `test`.
- **The caches, CAG, Redis and code against model are decided** ([12](12-caches-cag-redis-and-code-against-model.md)). The table of ledger answers is the first exact cache, and it works: a second check asked 5 new questions.
- **The analytics are decided** ([09](09-analytics-for-all-users.md)): six blocks on the event overview screen. Nothing is built.
- `.env` is filled. `HEDERA_TOPIC_ID` and `DATABASE_URL` stay empty: the register's topic waits for the owner's yes (Q38), then `python -m hackathon_memory.hedera.registry open` makes it. **`COLLECT_ETHGLOBAL` is `off` in the file and stays off.** `COLLECT_GITHUB=on` was added on 11 October for the README run (the owner's stop switch for GitHub).
- The owner is free for the whole of Saturday 17 October, for the tests. The registration closes on 20 October 2026, 19:00, and the submission opens then (the owner, 18 October).

**What the owner must do**

| For | What |
|---|---|
| The screens | Review layer 2: use S1 to S5 at http://127.0.0.1:8000, then the word to merge Phases E and F. |
| The backups | Copy `data/backups/20261018/` (the whole database and the cards) to a safe place: it is the only copy of the cards outside the database. |
| The FSS dates | When the submission opens on 20 October: the day it closes, and the day the registration opened. |
| Q44 | Two small findings of the visual review, left as they are unless the owner says otherwise. |
| The register | Q38: a yes to create its topic on the test network and to write one real record (launch gate 3), with the line in the README of this project's repository and the FSS Campus Edition of the list. |
| The categories | The split of "Tools for AI agents" out of "AI agents and automation" (the default until they answer). |
| The first line | Q15, and the hint for a returning name, Q16. |
| The bill | Read Google's bill once and run `python -m hackathon_memory.finops reconcile --billed <amount>`. |

**What the assistant does next, in this order**

1. Review layer 1 of the queue's changes on the real collection (S3 with and without a hackathon, the button "Compare with Gemini", a transaction in a card), with a findings file in `evals/review/`.
2. Test 3, the check of Hedera IDs on hand-checked pages (launch gate 6).
3. After the owner's yes to Q38: open the register, register this project's own repository for the FSS Campus Edition (typed days), keep the receipt in entry 16, strike launch gate 3.
4. **Phase G:** the tests and their reports (launch gates 4 to 6), and S6 (the method window; a first version exists).
4. **Phase I:** the README for judges, the rebuild from a clean copy (launch gates 1 and 2), the script of the video.
5. Later: a stored text-search column, so the word search does not build the documents at each question. Split `collect/ethglobal.py` (about 800 lines, three jobs) when it is touched again.

**The sources, on 11 October 2026**

| Source | State |
|---|---|
| ETHGlobal's showcase | **Collected** on 10 and 11 October 2026: every project of the list with the filter `partners=hedera`, 658 pages, one time each, signed, slowly. 732 of 800 requests used. The owner's decision of 10 October: the email named the winners only, and no second email is sent. The limit is 800 requests. After the 429: ten seconds between two requests. |
| GitHub's API | **The owner said yes** on 10 October 2026 (Q17). The token is in `.env` and works. |
| `hedera-hackathon.hashgraph.swiss` | **Read** on 12 October 2026 with the owner's yes (option 1 of Q35): the page and the one script file of its own that holds the winners, saved; 6 of 10 requests used in all. 19 winner entries. The switch is off again. It is not named in the public notes. |
| DoraHacks | Asked. No answer yet. No program touches it, also not through a link of another site. |
| Dar Blockchain | **Dropped** by the owner on 10 October 2026: it holds no historical submissions. |
| The Hello Future site of AngelHack | Asked for its winners pages. No answer yet. No program touches it. |
| Devpost | **Refused.** No program, ever. A person may browse it and note links. |
| `hol.org`, the winners of Hedera x AI | **Done by hand.** Six winner entries are in `data/by-hand/hol.org/`, outside git. No program. |
| The old copy of the Hedera18 site in the Wayback Machine | **Done by hand.** Eight winner entries are in `data/by-hand/web.archive.org/`, outside git. No program is sent to the archive. |
| Hedera's own winner posts on `hedera.com` | **Read** in the night of 12 to 13 October 2026 with the owner's yes of 9 October: the nine posts, each once (each with a step to its address with "/"), 22 of 25 requests. The people cut before and after the save. 135 winner entries. The switch is off again. |
| 4hacks and StackUp | Excluded. Their submissions are private. |

**Do not**

- Do not add a "Co-Authored-By" line, and do not name the assistant in a commit message, the code, a comment, the README or `DESIGN.md`. This is hard constraint 19. The notes (`CLAUDE.md`, the backlog, `docs/`) are committed since 20 October 2026, in their own `docs(notes)` commits (hard constraint 20).
- Do not spend the Google Cloud credit without the owner's yes: about $15 are left (20 October 2026). Say how much and for what first (hard constraint 7).
- Do not rewrite the history again, and do not force a push. The owner answered Q28 on 11 October: "Leave the commits dont delete them."
- Do not add Redis, a cache that answers similar questions, or CAG (entry 12). Do not run the first model layer on all pages before the sample and the comparison of entry 12.
- **Do not send a request to ethglobal.com with anything but the collector,** and never faster than the count file allows. Not a throw-away script, and never your own web reader.
- Do not write anywhere that the consent of ETHGlobal covers the projects with no Hedera prize. The email named the winners. The public sentence is in `README.md`, at the top.
- Do not ask the owner again to write to ETHGlobal about the scope. They decided.
- Do not show a handle or an address of a person anywhere. The parser hides them in the texts, and keeps a link to a profile without its address (the owner, 11 October: "if its people then hide them"). A new collector hides addresses before it saves a page. A saved page changes only through `RawStore.remove_text`, with a reason.
- Do not ask the owner again about the password of the local database (Q32: it stays).
- Do not read out or show the scores that ETHGlobal computes: `autoOriginality`, `autoPracticality`, `autoTechnicality`, `autoSummary`.
- Do not present the numbers of [`tools/ethglobal/results-20261010.txt`](tools/ethglobal/results-20261010.txt) as a result, in the product, the README, the pitch or the video. They come from scripts, not from a test (hard constraint 6). The file itself is a working note, public since 20 October 2026. The numbers of a result file in `proofs/results/` may be shown.
- Do not put text of a saved page into git, a test, a result file or a commit message. The test pages are invented.
- Do not put an account of single requests, a list of small sources or an admission into the public notes without the owner's word.
- Do not run a collector on a site whose yes is not in the table above. This is hard constraint 17.
- Do not send any program to Devpost, DoraHacks, the Hello Future site or `hol.org`.
- Do not build anything for 4hacks, for StackUp or for Dar Blockchain.
- Do not sign in to any site, and do not use a login that the owner pasted. This is hard constraint 10.
- Do not print a value of `.env`, and do not print a key object of the Hedera library: its `repr()` shows the whole key (entry 05).
- Do not write to the main network of Hedera. The code refuses it, and `CLAUDE.md` section 6 says to ask.
- Do not open anything outside this folder (hard constraint 16). One exception that the owner gave: the code reads their Google sign-in file at the path that is in `.env`. Nothing else in that folder.
- Do not call a model without the meter. Do not guess a price that is not in the price book.
- Do not add a big data tool. Build with the habits of blueprint §11.6 from the first table.

**Ask the owner when you reach it**

- Whether DoraHacks or the Hello Future team has answered: open questions Q8 and Q13. Write each answer into backlog entry 04 with its date.
- The first line of the project, and the hint for a returning name: open questions Q15 and Q16. Both are sentences the judges will read, so the owner decides.

**Practical things about this laptop**

- The tool shells do not see the owner's programs. Use the full paths in [01-research.md](01-research.md). In the Bash tool `git` works and `python3` does not exist: use `.venv/Scripts/python.exe`. In the PowerShell tool `git` does not work: use `C:\Program Files\Git\cmd`. `docker` needs its own folder on `PATH` too: `C:\Program Files\Docker\Docker\resources\bin`. `gh` is at `C:\Program Files\GitHub CLI\gh.exe`.
- Connect to the database on `127.0.0.1`, never on `localhost`: Docker Desktop answers on the IPv6 address and never replies.
- A long test run piped into `Select-Object -Last` shows nothing until it ends. Write the output to a file and read the file.
- A job of several minutes is started in the background, with its output in a file. A foreground command is cut after ten minutes, and a cut run leaves no record.
- A script that prints text of a site must set its output to UTF-8 before the first request.
- Test with the library's own objects, built from the same bytes as the real service sends. Give invented test data the odd habits of the real data as soon as they are known.
- Run a tool that shows numbers on real numbers before calling it done.

## How this backlog works

- **One file per step,** named `NN-topic.md`, numbered in the order the work happened. A later step on the same topic adds a dated heading to that topic's file.
- **Every entry has the same parts:** Goal, Approach, Method (commands to repeat it), Results, What went wrong, What this does not prove, Next.
- **Same session:** the backlog is updated in the same working session as the work it describes. It is committed in its own `docs(notes)` commit (`CLAUDE.md`, hard constraint 20).
- **Commits named:** from Phase A on, every entry ends with the short numbers of the commits of its step (`CLAUDE.md`, section 9.8).
- **Folders:** the numbered entries stay at the top of this folder, so that no link breaks. [`sessions/`](sessions/) holds one file per working session, in time order: what the owner asked, what they decided in their own words, and what was done. The documents for the owner are in `docs/` (`blueprint.md`, `setup-guide.md`, `video-script.md`). [`tools/`](tools/) holds the scripts of the work: the guard hooks, the commit scripts, the history rewrite of 10 October.
- **Three shared files:**
  - [`decisions.md`](decisions.md): every decision, with its date and who made it.
  - [`lessons.md`](lessons.md): mistakes, dead ends and their fixes.
  - [`open-questions.md`](open-questions.md): things that wait for the owner.
- **What goes where:** the blueprint says what we build and why. The backlog says what happened. If they disagree about what we build, the blueprint is fixed in the same change.

## Status board

Update this at the end of every block of work.

| State | Item |
|---|---|
| Done | Research and decisions ([01](01-research.md)). Documents: `CLAUDE.md`, `docs/blueprint.md`, this backlog ([02](02-documents.md)). The owner's answers, the terms of DoraHacks, the licence ([03](03-answers-and-terms.md)). The other platforms and their rules ([04](04-other-platforms.md)). The repository exists. |
| Done | **Phase A and Gate A** (11 October 2026), merged into `main` and tagged `gate-a`. |
| In progress | **Phase B** on `phase-b-thin-path` ([13](13-phase-b-parser-and-store.md)): the parser, the store, the parse and check steps, the proof rule. Next: the README IDs, the code facts, the search, Gate B. |
| Was in progress | **Phase A**, on the branch `phase-a-proofs` ([05](05-phase-a.md) to [11](11-all-hedera-projects-and-the-429.md)). The owner said on 11 October that it is done. The merge waits for the lists proof. Built and tested: the project, the settings, the local database, the polite collector layer with its count of requests, its cooldown and its memory of a refusal, the ETHGlobal walk and run, the Hedera write, the two Gemini layers, the cost ledger, the setup check, the secret scan, CI, the design document. Three proofs of Gate A stand. **The lists proof is open again:** the collection now covers all 658 Hedera projects of ETHGlobal, and it was not finished when this was written. |
| Next | The IDs in the README of the code, the facts of the code, the embeddings and the search, Gate B. |
| Waiting on the owner | Q11, Q15, Q16, Q29 and Q30 in [`open-questions.md`](open-questions.md). |
| Waiting on others | The written answers of DoraHacks and of the Hello Future team, to the emails of 9 October 2026. When one says yes, the collecting work of Phase A is taken up again for that site. |

## Entries

| # | File | Topic | Status |
|---|---|---|---|
| 01 | [01-research.md](01-research.md) | From the idea to the tech stack: what was checked, what was measured, what was wrong | done |
| 02 | [02-documents.md](02-documents.md) | The first documents | done |
| 03 | [03-answers-and-terms.md](03-answers-and-terms.md) | The owner's answers to the nine questions, the terms of DoraHacks, the permission email, the licence | done, the answer of DoraHacks is waiting |
| 04 | [04-other-platforms.md](04-other-platforms.md) | Which site holds which Hedera event, and what each site allows. Later the same day: 4hacks excluded, three more permission emails, the sites that are gone, the owner's own check of every old site, and the first answers: ETHGlobal yes, Devpost no. | done, two answers are waiting |
| 05 | [05-phase-a.md](05-phase-a.md) | Phase A: the project setup and the four small proofs of Gate A | done. The fourth proof is told in entry 10 |
| 06 | [06-live-proofs.md](06-live-proofs.md) | The live proofs on the real services, the two Gemini layers, the owner's answers, a look at ETHGlobal, and the scan for secrets | done |
| 07 | [07-ethglobal-as-it-is.md](07-ethglobal-as-it-is.md) | What ETHGlobal's pages really show (19 signed requests), the video question, and the collector on a list of project pages | done. Overtaken in part by entry 10 |
| 08 | [08-rules-clean-history-finops.md](08-rules-clean-history-finops.md) | The rules of 10 October (no sign of the assistant, notes local, consider a refactor), the one-time rewrite of the history, and the cost of the models | done |
| 09 | [09-analytics-for-all-users.md](09-analytics-for-all-users.md) | Research and proposal: analytics for all users. The owner left the choice to the assistant: six blocks on the event overview screen | decided, nothing built |
| 10 | [10-ethglobal-walk-and-first-run.md](10-ethglobal-walk-and-first-run.md) | The Hedera list of the showcase, the walk, the first run on ETHGlobal (92 pages, 140 requests), the proof of the lists, what the saved pages are like, and the draft of the second email to ETHGlobal (the owner decided not to send it) | done. Its scope was widened in entry 11 |
| 11 | [11-all-hedera-projects-and-the-429.md](11-all-hedera-projects-and-the-429.md) | The owner's seven points: every Hedera project of ETHGlobal and not only the winners, general public notes, Dar Blockchain dropped, a new source. The 429, what caused it, and the cooldown that is now a rule of the code | done. The run ended on 11 October 2026: 658 pages |
| 12 | [12-caches-cag-redis-and-code-against-model.md](12-caches-cag-redis-and-code-against-model.md) | The owner's four points: where the automatic steps run, the caching strategy, CAG, Redis, code against model on the same pages, the commits stay, Phase A is done | decided, nothing built |
| 13 | [13-phase-b-parser-and-store.md](13-phase-b-parser-and-store.md) | Gate A passed and Phase A merged. Phase B: the parser, the store, the parse and check steps, the proof rule, the ends of events, the hiding of people, the README and the facts of the code through GitHub, the life rule, the embeddings and the search, the step all and the proof of Gate B | built; Gate B waits for the owner's three questions |
| 14 | [14-phase-c-all-projects.md](14-phase-c-all-projects.md) | Phase C: every allowed project, 826 in all (658 full cards, 168 winner entries); the Africa page and Hedera's own posts; the people cuts. | done, open for the sites that have not answered |
| 15 | [15-phase-d-llm-fields.md](15-phase-d-llm-fields.md) | Phase D: the quote check, the cards, Test 1 graded, Test 2 run, the categories split, Argon measured. | done, waits for the merge |
| 16 | [16-phase-e-website.md](16-phase-e-website.md) | Phase E: the search and the project card, made on the server. | going on |
| 17 | [17-notes-public-dark-mode-words-insights.md](17-notes-public-dark-mode-words-insights.md) | The owner's ten points of 20 October: the notes public, a calmer dark theme, the words of the website, insights, hosting, the Google credit. | going on |

## Sessions

| Date | Where | Summary |
|---|---|---|
| 7 Oct 2026 | The owner's laptop, with Claude Code | The idea, the count of Hedera's hackathons, what exists elsewhere, the five steps. |
| 9 Oct 2026 | The owner's laptop, with Claude Code | The tech stack by need, the measuring method, the card design, then these documents. |
| 9 Oct 2026, later | The owner's laptop, with Claude Code | The owner's answers to the nine questions. The terms of DoraHacks were read: collection needs its written permission. Blueprint version 0.2. |
| 9 Oct 2026, last | The owner's laptop, with Claude Code | The repository was created and the email was sent. The rules of the other platforms were read. The owner's standing rule: build everything, run no collector before their yes. Blueprint version 0.3. First commit. |
| 9 Oct 2026, evening | The owner's laptop, with Claude Code | 4hacks and StackUp excluded. The owner checked every old site by hand. Winner entries. Production level without big data tools. ETHGlobal said yes and Devpost said no. Blueprint version 0.6. The build starts in the next session. |
| 9 to 10 Oct 2026, night | The owner's laptop, with Claude Code | Phase A built and run: the database, the Hedera write and the Google models passed on the real services. The owner decided on two Gemini layers. Trace: [sessions/2026-10-09-phase-a.md](sessions/2026-10-09-phase-a.md). |
| 10 Oct 2026 | The owner's laptop, with Claude Code | The owner's eleven points. ETHGlobal investigated and the collector rebuilt. The history rewritten once and the notes made local. The cost of the models counted. Analytics researched. Trace: [sessions/2026-10-10-eleven-points.md](sessions/2026-10-10-eleven-points.md). |
| 10 Oct 2026, evening | The owner's laptop, with Claude Code | The owner's six points. They found the Hedera filter of the showcase. The walk and the first run on ETHGlobal: 92 pages. Gate A's fourth proof passed. `DESIGN.md`. Trace: [sessions/2026-10-10-evening-six-points.md](sessions/2026-10-10-evening-six-points.md). |
| 10 to 11 Oct 2026, night | The owner's laptop, with Claude Code | The owner's seven points. The scope widened to all 658 Hedera projects of ETHGlobal. The site answered 429 after 62 more pages. A cooldown rule in the code. Then the owner's four points: caches, CAG, Redis, code against model, and Phase A is done. Then Gate A passed, Phase A merged and tagged, and the first part of Phase B. Trace: [sessions/2026-10-11-night-all-projects.md](sessions/2026-10-11-night-all-projects.md). |
| 11 to 12 Oct 2026 | The owner's laptop, with Claude Code | The owner's nine points: hide people (Q31), the password stays (Q32), context and easy words for every ask. Then the README of every project's code through GitHub (cleaned before saving), the ledger check of its IDs (285 projects with an ID, 76 with proof), the facts of the code and the life rule, the embeddings with gemini-embedding-2, the search (meaning and BM25), the step all and the proof of Gate B. Trace: entry 13. |
| 12 Oct 2026, afternoon and evening | The owner's laptop, with Claude Code | The owner's answers: blind ideas, the scale of three marks, the judgement left to the assistant, the life rule (30 days, "too early to tell"), the ends of four events, and "never take my words granted". Gate B passed. A change of Wi-Fi crashed a run: the clients of Google and of the mirror node now wait and ask again. |
| 13 to 18 Oct 2026 | The owner's laptop, with Claude Code | Phases B to E, told in entries 13 to 16. |
| 20 to 21 Oct 2026 | The owner's laptop, with Claude Code | The owner's ten points of 20 October: the notes public, the FSS dates, the $15 credit, a calmer dark theme, the words of the website, insights; hosting answered; the demo waits for their word. Entry [17](17-notes-public-dark-mode-words-insights.md). |
