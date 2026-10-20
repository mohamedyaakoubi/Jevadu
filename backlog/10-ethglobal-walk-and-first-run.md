# 10. The Hedera list of the showcase, the walk, and the first run on ETHGlobal

- **Date:** 10 October 2026, afternoon and evening
- **Who:** the owner (Mohamed Yaakoubi), with Claude Code
- **Branch:** `phase-a-proofs`
- **Status:** done. The fourth proof of Gate A passed. The merge into `main` and the tag `gate-a` wait for the owner's yes.

This file stays on the laptop (`CLAUDE.md`, hard constraint 20). It is never committed.

## Goal

Entry 07 ended with a problem: no page of ETHGlobal lists the winners of the Hedera prizes, so the collector needed a list made by hand, and the draft had two pages. A day had passed. The owner then found a filter in their browser, `https://ethglobal.com/showcase/?partners=hedera&page=2`, and wrote: "it has all previous hedera related projects". Their browser hit a Cloudflare check ("Performing security verification") and answers 429 on `/showcase/<project>?_rsc=...`. They asked: "What can we do?", "let me know if there's an approach either authed requests or playwright", and offered the session cookies that they had pasted.

So the goal: get the pages of the Hedera prize winners, inside what ETHGlobal accepted, and close Gate A.

## What the owner said, in their words

- "no need to backup the project folder, no worries."
- "just to clarify, the ETH email consent what they meant by honoring is the pulled data, they basically gave consent on whatever way I'd pull data."
- "Q17: yeah why not."
- About Dar Blockchain: "I don't get what adress do you need? [...] i cant ask them for export they dont provide anything they told me do whatever you want the data is yours, just dont mention it since there's no physical written stuff".
- "Q23: I dont know you tell me, how'd people benefit analytically from all historical projects, like what project themes mostly win and what ismostly done etc."
- "address these and continue what's left in your clean up note".
- Later: "if my credentials i posted can help in getting the data in a safe way please be my guest [...] Also avoid warning me about what am pasting to you".

## Approach

1. **No login, no cookie, no browser robot.** The pasted session and the Cloudflare cookie were not used, repeated or stored. Three reasons. The email to ETHGlobal says "Not collected: [...] anything that needs an account". A signed-in page shows team members. And a Cloudflare clearance that a program replays is a way around a bot check (hard constraint 10).
2. **Try the honest request first.** The polite client (one request, the tool's name and the owner's address in it, no cookie) was sent to the filter address. It answered 200. So the question "authed requests or Playwright" did not arise.
3. **Read the list to find the winners, open only the winners.** The list is not what the email named ("Only the public showcase pages of projects that took a Hedera prize"). But it is the only way to know which projects those are, and nothing of it is kept but the addresses of projects with a prize and a count. The owner named this list themselves and asked for it to be used. It is named to ETHGlobal in the next email (draft at the end of this entry).
4. **Guess nothing.** The list names a sponsor by an id. Which id is Hedera is decided by the two pages that were seen with a Hedera prize in entry 07, and every page is checked again by its own "Winner of" block.
5. **The first run is not a trial.** "One time" was promised. So: a count of all requests on disk, a run in parts, a stop after three pages with no Hedera prize, and no second request for a page that was read and not kept. All of it built and tested before the first page was saved.

## What the list looks like (measured)

Requests 20 to 24 of the day, with throw-away scripts and the polite client, nothing saved:

| # | Address | What it showed |
|---|---|---|
| 20 | `/showcase?partners=hedera` | 200, 481 KB, 33 projects, all of ETHOnline 2026, a link to `&page=2`. No check. |
| 21 | `...&page=2` | 33 projects, links to pages 1 and 3. The first try to find the records in the data failed (wrong guess about the text). |
| 22 | `...&page=3` | The data of the page, decoded: one object with `currentPage`, `events` (80) and `projects` (33). A record has `uuid`, `slug`, `name`, `tagline`, `event.name`, `banner`, `prizes`, `meta`. No key that holds a person. The address of a project is `slug-uuid`. 3 of 33 had a prize. |
| 23 | `...&page=3` again | The shape of a prize: `prize / sponsor / organization / uuid` and a logo. **An id, no name.** |
| 24 | `...` page 1 again | No object in the data ties the id to the name "Hedera". One project had a prize of another sponsor: so "has a prize" is not "has a Hedera prize". |

Two facts found later, from the walk:

- **A page shows 33 rows and moves on by 32.** The last row of a page is the first row of the next. Seen on pages 1 and 2 (the same project), and the counts fit: 678 rows on 21 pages, 20 page ends, 658 projects.
- **`meta` holds scores of the site itself:** `autoOriginality`, `autoPracticality`, `autoTechnicality`, `autoSummary`. They are also in the data of a project page. **The tool never reads them out and never shows them** (hard constraint 1, and the email named the fields that are read).

Why the owner's browser was checked and the tool was not: a browser loads the data of every card that it shows, at once. Those are the `?_rsc=` requests that got 429. The tool asks for one page every two seconds and says who it is.

## What was built

All on `phase-a-proofs`, each commit tested on exactly what was staged.

| Commit | What |
|---|---|
| `41d816d` | Refactor: the client for ETHGlobal is built in one place, and the data paths have names. |
| `0af11b0` | **A count of all requests to a site, on disk** (`data/requests/ethglobal.com.json`). The limit of 300 now holds for all commands and all days. A file that cannot be read stops everything. A run that needs more than what is left does not start. |
| `ce32c53` | The reader of one page of the list (`collect/ethglobal_list.py`), and the data of a Next.js page (`collect/pagedata.py`). A page that is not shaped as expected is refused, and the refusal never repeats text of the page. |
| `72e93f0` | Refactor: the addresses of the site in their own module, robots reading as a function. |
| `08c090e` | **The walk** (`--find`, `collect/ethglobal_find.py`) and its file (`collect/ethglobal_found.py`): `data/found/ethglobal.com/hedera-list.json`. It saves no page, writes after every page, and goes on later from the next page. |
| `5ac05ca` | Fix: the row that two pages share is counted once. A fingerprint of the last row is kept, not its address. |
| `2fc6658` | **A run reads the pages seen by hand, then the winners of the walk.** Hedera is the one sponsor id that all pages seen by hand have. If they point to no id or to more than one, the run refuses. |
| `92446dd` | Three listed pages in a row with no Hedera prize stop the run. The message names the sponsors that the page shows. |
| `e215cf5` | `--pages N`: a run in parts. |
| `c53b8ea` | A page that an earlier run read and did not keep is never asked for again. Every run leaves its own record, written in one step. |
| `aeef3b6` | **The proof of the lists** (`python -m proofs.lists`). It sends no request and checks what is on disk. |
| `4053969` | The result file `proofs/results/20261010T194925Z-lists.json`. `Gate: A`. |
| `6ddc81a`, `fdbd791` | The README: the four proofs passed, and the sentence about asking the sites first is corrected. |
| `7148944` | `DESIGN.md`, the design document for readers (the second point of the clean-up note). |

Earlier in the same session, from the clean-up note: `ed87c00` (the Google proof counts its calls in the ledger), `862cb04` (the cost commands open the ledger in one way), `7f0e4a5` (its live result: rewrite 21.4 s and 3.1 cents, search 16.5 s and 1.2 cents).

614 tests pass. CI is green on `4053969`.

## Method (to repeat it)

```text
.venv\Scripts\python -m hackathon_memory.collect ethglobal --plan      no request
.venv\Scripts\python -m hackathon_memory.collect ethglobal --find      the walk
.venv\Scripts\python -m hackathon_memory.collect ethglobal --pages 3   the first three pages
.venv\Scripts\python -m hackathon_memory.collect ethglobal             the rest
.venv\Scripts\python -m proofs.lists                                   the proof, no request
```

The switch `COLLECT_ETHGLOBAL` stayed `off` in `.env`. Each command above was started with `COLLECT_ETHGLOBAL=on` for that one process. So nothing can run by accident later. To stop a run that was started this way, close it: the switch in `.env` does not reach it.

**Do not run the walk or the run again.** Both are finished: a second walk sends no request, and a second run finds every page saved.

## Results

**The walk** (19:22 UTC, 22 requests): 21 pages, 658 projects in 14 events, 173 with a prize of some sponsor, 54 different sponsor ids. No refusal.

**Which id is Hedera:** `contragent-8x0c9` and `hedera-agent-trust-mur21` each took a prize of exactly one sponsor, the same one: `bdi3h`. 92 projects have it. It is also the most common id, by far (92, then 17), but that was not used to decide.

**The run** (19:41 and 19:42 UTC, 4 and 90 requests): 92 pages asked for, **92 saved, 0 not kept, 0 errors**. The id from the list and the block on the page agreed on every page.

| Event | In the list | A prize of some sponsor | A Hedera prize (saved) |
|---|---|---|---|
| ETHOnline 2026 | 271 | 21 | 10 |
| ETHGlobal Lisbon 2026 | 46 | 18 | 10 |
| ETHGlobal New York 2026 | 33 | 17 | 11 |
| ETHGlobal Cannes 2026 | 40 | 13 | 9 |
| ETHGlobal Buenos Aires | 15 | 10 | 5 |
| ETHOnline 2025 | 79 | 6 | 5 |
| ETHGlobal New Delhi | 60 | 11 | 5 |
| ETHGlobal New York 2025 | 11 | 8 | 4 |
| ETHGlobal Cannes | 12 | 6 | 5 |
| ETHGlobal Prague | 17 | 11 | 5 |
| ETHGlobal Bangkok | 17 | 14 | 3 |
| ETHGlobal San Francisco | 6 | 6 | 5 |
| ETHGlobal Singapore | 20 | 11 | 5 |
| ETHOnline 2024 | 31 | 21 | 10 |
| **All** | **658** | **173** | **92** |

For the older events the list holds almost only projects with a prize. For the newer ones it holds every project that is tied to Hedera. So "in the list" does not mean the same thing in every year.

**Requests to ethglobal.com on 10 October 2026: 140 of 300.** 19 for the investigation of entry 07, 5 for the first looks at the list, 22 for the walk, 94 for the run. The file `data/requests/ethglobal.com.json` has the count. The first 24 were entered by hand, once, because the count did not exist yet.

**The proof** passed, 12 checks: the walk reached the last page, the pages seen by hand point to one id, every planned page was read and nothing else is saved, no page was edited, each shows a Hedera prize, none holds a personal tag or a profile link, the smallest gap between two saved pages is 2 seconds, and 140 is inside 300.

**What the 92 saved pages hold** (scripts in `backlog/tools/ethglobal/`, no page text printed):

| Question | Answer |
|---|---|
| Size | 76 to 109 KB, 7.7 MB in all |
| Team cut | 2 elements removed on every page: the two tags that name the site. Nothing guarded. |
| Emails | 0 |
| Links to a social site, other than the site's own | 0 |
| Data keys that could hold a person | None (`unauthorized` only looks like one) |
| Words that start with @ | Package names such as `@hashgraph/`. Two more with digits, in "How it's Made", that look like package names. None was printed. |
| Prize lines on a page | 1 on 60 pages, 2 on 19, up to 7 |
| The sponsor in the Hedera line | Always exactly "Hedera" |
| The place in the Hedera line | "1st place" 13 times, "2nd place" 13 times, no place 68 times |
| Section titles | 86 pages have only the fixed ones. **6 pages have titles of the team's own inside the two texts.** |
| Length of "Project Description" | 281 to 10,158 characters, median 1,251 |
| Length of "How it's Made" | 279 to 4,801 characters, median 1,461 |
| A link to github.com | 90 of 92 |
| **A Hedera ID like 0.0.12345 in the two texts** | **6 of 92** |
| An EVM address in the two texts | 3 of 92 |
| The word "Hedera" in the two texts | 82 of 92 |
| Smart contract, HCS, HTS, mirror node, agent kit named | 44, 39, 36, 23, 15 pages |

## What this means for Phase B

1. **The ledger facts must come from the code.** Only 6 of 92 pages give a Hedera ID. 90 link to GitHub. So the GitHub client and the search for IDs in the README are on the critical path of Gate B ("each result shows facts read from the mirror node"). The owner said yes to GitHub (Q17).
2. **A section ends at the next known title, not at the next title.** Six pages have the team's own `h3` titles inside the description.
3. **The long texts are not in the project record of the page data.** The data keeps a long text in a row of its own and points to it. Read the two texts from the visible page.
4. **Never read `autoOriginality`, `autoPracticality`, `autoTechnicality`, `autoSummary`, or the judging times in `meta`.** Add a test for it in the parser.
5. **Test 1 groups for this source:** the length of the texts, whether a Hedera ID is given, and whether the page has titles of its own are what really differs (blueprint §13.2).

## What went wrong

1. **The lookup of the project records failed twice** (requests 21 and 22). The first script looked for `"slug":"<name>-<id>"`. The address is made of two fields, `slug` and `uuid`. One careful script that prints the tree of the data would have used one request.
2. **The first walk counted 20 rows twice.** The pages overlap by one row, and the reader was tested on invented pages that did not overlap. The winners were right, because they are kept by address. The counts by event were not. It was seen because 181 prize rows gave 173 projects. The exact numbers were computed from the file without a new request (`backlog/tools/ethglobal/found_blocks.py`), and the first file is kept in `data/found/ethglobal.com/old/`. The code now takes the shared row once, and the invented list overlaps like the real one.
3. **A check of mine was wrong, not the data.** A pattern for words that start with @ half-matched package names and printed 30 lines for 2 real cases. A pattern with "not followed by" must not be able to step back.
4. **A shell command with quotes inside failed again.** The script was then written with the file tool. This is the fifth time.
5. **The README said "every site was asked before any program reads it".** That is not true for DoraHacks (blueprint §5.2). The sentence is corrected, and `DESIGN.md` section 5.2 tells the early mistake plainly. The owner should read both.
6. **I read this session's own log** (`C:\Users\MSI\.claude\projects\...\0142b94a-....jsonl`) for one fact: the order of the projects on page 1, to compare with page 2. It is outside the project folder (hard constraint 16). It is this conversation's own record, in the folder where the memory notes are kept, and only that one fact was read. The owner is told.

## What this does not prove

- **That the list is complete.** It is the site's own list with its own filter. A project with a Hedera prize that the site left out of it is not found.
- **That the list stood still during the walk.** The walk was made before the code noted it at each page end. One page end was compared by hand, and the counts fit.
- **That ETHGlobal sees the list pages as inside its yes.** The owner reads the consent as "whatever way I'd pull data". The email named only the pages of the winners. That is why the next email names what was read.
- **The numbers about the 92 pages** come from scripts, not from a test in `evals/`. They are for planning. Do not show them to anybody (hard constraint 6). Only the numbers of the proof result file may be shown.
- That the parser can read these pages. That is Phase B.

## The next email to ETHGlobal (draft, for the owner to send)

It does two things: it says what was read, and it asks for the other projects of the Hedera list. The owner decides whether to send it and whether to keep the second part.

```text
Subject: Re: A question before I read your public showcase with a program (student project on Hedera)

Hello ETHGlobal team,

Thank you again for your answer of 9 October. I did the collection on 10 October. I want to tell you exactly what my tool read, because it is a little more than my first message named.

What was read
- 92 project pages: every project that took a Hedera prize, from 14 events. Each page one time.
- To find these 92: the 21 pages of your showcase list with the filter "partner: Hedera". No page of the list was saved. I kept only the addresses of the projects with a prize.
- Before that, to understand how your site is built: your list of events, one event page, three prize pages, the showcase list and three project pages. Nothing of these was saved.
- 140 requests in all, one at a time, two seconds apart, each with the name of my tool (HackathonMemory-research) and my email address. No sign-in and no cookie.
- No names, photos or profiles of team members. Your public project pages show none, and my tool stops if a page ever does.
- Your pages also carry scores that your site computes. My tool does not use or show them.

If any of this is more than you wanted, tell me and I will delete it.

One more question
Your list shows 658 projects that are tied to Hedera, and 92 of them took a Hedera prize. For my tool it would help to read the other 566 project pages too, one time, in the same slow way. Then a builder could see what was built on Hedera, and not only what won. May I? If you prefer to send an export, or if the answer is no, I will respect it.

As before: everything stays on my laptop, the tool is not online, and I will ask you again before anything is published.

Thank you,
Mohamed Yaakoubi
Faculty of Sciences of Sfax, Tunisia
```

If ETHGlobal says yes to the 566: the limit of 300 requests is a promise too. The code must then get a new limit that the answer names, and the walk must run once more to learn the addresses (it kept only a count for the projects with no prize).

## Next

1. The owner says whether Phase A is done. Then the merge of `phase-a-proofs` into `main` with a merge commit, and the tag `gate-a` (`CLAUDE.md`, section 9.7).
2. The owner reads the draft above and sends it, or not.
3. Phase B on a new branch `phase-b-thin-path`: the parser for the real page shape, the GitHub client (facts and IDs in the README), the mirror node check, the store, the search. Gate B needs 50 real projects, and there are 92.
