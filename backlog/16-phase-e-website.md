# 16. Phase E: the website

Started on 15 October 2026 on `phase-e-website`, from the end of Phase D (`7217592`). The owner asked "When can I test the live version on the localhost browser?" and "I might only be able to tell how good the solution would be from actually testing it as a product."

## Goal

S1, the search, and S2, the project card (blueprint 12.1), then review layer 1 (12.3). Phase E ends when review layer 1 is done (`CLAUDE.md` section 4).

## Built

| Commit | What |
|---|---|
| `c4d64bb` | FastAPI 0.143.1, uvicorn 0.54.0 and Jinja2 3.1.6 in the dependencies; templates and style sheet shipped with the package. Starlette 1.8.0: `TemplateResponse(request, name, context)`, autoescape on for .html (read in the installed source). |
| `dcc4da9` | `src/hackathon_memory/web`: S1 (the idea box, the 10 closest projects, one sentence each with its source, the marks of proof and life, the legend) and S2 (three sources apart: the page word for word, the code and the ledger with HashScan links, the fields of the model with labels and quotes). States: nothing asked, nothing found, Google away (the words alone are searched, and the page says so), database down (said within 5 seconds, not 130). Page text always escaped. 127.0.0.1 only. 8 tests. |
| `651d1d4` | constraints.txt with the web packages. |
| `f6780bc` | The card shows the day the page was saved from its site, not the day of the parser. |
| `d80c860` | The comparison of blueprint 8.3: after the results are shown, `compare.js` asks `/compare` for one sentence on what is the same and one on what differs, for each of the first 10 results, and puts each in its place. The model (the search model, Flash, HIGH) reads the kept fields of the card, or the short line and the first 700 letters of the first text when there is no card, and names the texts it used; names it was not given are dropped. Failure: every place says so, the results stay. 13 tests of the website, 2 of them in Chromium (Playwright routes every request to the test client, no server). |
| `8d746a0` | Test 1, second run (card-form-2), graded by the assistant alone; see below. |
| `809210e` | `evals/compare_levels.py`: the comparison at LOW, MEDIUM and HIGH on the owner's 9 ideas of Test 2, numbers only. |
| `498d289` | The README says what works on 15 October (it still said: no website, no search, no cards, no tests). |
| `04d1429` | Refactor: `listing.signs_of_life(conn, ids)`, so that the filters can ask it for every project. |
| `eda395d` | The filters of S1 (blueprint 8.2): event, year, category, Hedera proof, life. Each offers the values the projects have, with counts. Both lists of the search are limited to the matching projects; BM25 still weighs words over every project. No project left: the page says so and Google is not asked. A value no project has is left out, with a note. The category exists only for the 75 projects with a card, and the page says so. The year comes from the end of the event, else its start (658 of 826 projects). The facts are read at most once a minute (0.49 s for 826 projects). |
| `f4f0850` | Review layer 1 of S1 and S2 (`evals/review/2026-10-15-layer1-s1-s2.md`) and its six sure fixes: the wait announced (up to a minute), a search jumps to `#results`, the mark "no Hedera ID given" in the legend's words, a note when no word of the idea is in any project, one date form ("6 July 2025"), a tab icon. |

## Measured

- **15 October 2026, one real idea on the local website** ("an app that lets a street vendor take payments without a bank account"): the 10 results in 2.7 seconds, the comparison of all 10 in 49.2 seconds. Too slow for a person who waits: the thinking level HIGH of the search model (the owner's setting, `CLAUDE.md` section 7) is the likely cause. To measure LOW against HIGH on a few ideas, with a result file, before the owner is asked (review layer 1).
- The comparisons used the short line and the page text for all 10 results, because only the 75 pages of the two sets have a card of card-form-2.
- **The levels, 15 October 2026** (`evals/results/20261015T013838Z-compare-levels.json`, 27 calls): the middle time LOW 7.5 s, MEDIUM 7.4 s, HIGH 26.0 s (longest 35.2, 24.4, 37.1); cost 4.1, 4.2 and 14.3 cents for 9 comparisons each. At LOW and MEDIUM the model thought 0 tokens, at HIGH about 3,200. Every project got its two sentences at every level. Read by the assistant on 4 ideas: the same content at LOW and HIGH; HIGH names the project, LOW writes "The project". "Nothing clear." 16, 19 and 14 times of 90. The level of the search model is the owner's setting (HIGH): asked in the report of 15 October.

## Test 1, second run (card-form-2)

- The cards of the 60 pages made again with card-form-2 (run 40 of the table of runs, 3.13 dollars, quotes 829 of 829, 413 kept, 7 not found, 0 dropped). New sheet `data/evals/test1-card-form-2` (the same pages in the same order, the same 10 parser checks; planted categories from far groups).
- The owner did not grade it. The answers before the card were carried over from the first sheet (they depend only on the page). The categories were looked at again under the 17 categories for every project whose first or second pick was an agent, tool or data category (25 projects), from the name, the short line and the start of the description, before any new card: 15 moved to "Tools for AI agents". Project 3 (a credit bureau for agents, first pick Lending) was missed by that rule and changed after its card was seen, marked `unlocked: yes`. A scan of the other pages for the word "agent" found no other case.
- Result `evals/results/20261015T011908Z-test1-card-form-2.json`: not wrong 407 of 407, fully right 401 (98.5%, 97.3 to 99.5), labels 412 of 414 (99.5%, 98.8 to 100), kept 100%, quote check 413 of 413, planted 6 of 6 caught (4 categories, 2 fields of other cards), all four pass marks met. Model against the assistant's own category: 41 of 56 (45 of 58 in the first run); 5 graded partly. The list check needs two graders and is not repeated.
- Public text: a section of `evals/test1/report-gemini-3.1-pro.md`. Its first draft quoted three words of a page; removed before the commit.

## Review layer 1 (15 October 2026)

T1 and T2 in Chromium, 1366x900 and 390x844 (phone), one picture per screen height (`scratchpad/review_layer1.py`, local). The findings file is public and neutral: `evals/review/2026-10-15-layer1-s1-s2.md`. 9 findings: 6 sure (fixed in `f4f0850`), 3 unsure for layer 2: the note under the filters is long on a phone; on a phone the ledger facts and HashScan links come after the whole page text; for the street-vendor idea a machine-payment project comes first (search quality, Test 2). The phase's end condition (`CLAUDE.md` section 4: "Review layer 1 is done") is met; the merge waits for the owner.

## Running

`python -m hackathon_memory.web` serves http://127.0.0.1:8000. Port 8000 is not in the ranges that Windows reserves on this laptop (`netsh int ipv4 show excludedportrange protocol=tcp`, 15 October). The owner: Docker "sometimes becomes zombie that I have to kill it via task manager and rerun it", and reserved ports can come from winnat.

## Next

1. The owner's answers: the level of the comparison (LOW or HIGH), Q37 (the cards of all pages), and their word on Phases D and E.
2. Layer 2: the owner tests S1 and S2 on http://127.0.0.1:8000 and accepts or rejects the 9 findings.
3. Phase F: S3 (check a submission) and S4 (register on Hedera), after their screens are agreed in blueprint 12.1.

## 16 October 2026: the owner's test and five points

The owner tested the website and wrote five points: (1) the search: the label "one or two
sentences" is bad, the limit must come from cost; what are the layers and does Gemini depend on
them; should the ways to search be separate modes with speed and accuracy, documented with a
benchmark; typo tolerance, autocomplete, highlighting, operators ("dorks"); Elasticsearch or
not, with heavy research. (2) the design: "totally user unfriendly, bad accessibility, bad UX,
bad UI, bad project overview navigation, user should not be navigated outside 1 page to see the
content of a card"; research to avoid an AI look; is a Python-only website the right stack.
(3) was the rewrite by Gemini made only for messy projects, and where is AI inference used.
(4) "Make ai reasoning for search low". (5) "you are free to merge anything that is not broken
and is appendable in the future".

Done:
- (4) the search model at LOW: code default, .env, .env.example, DESIGN 11.3 and 11.4 (`bc8626a`).
- (5) Phase D merged into main as `ee82e10`, tag `phase-d`, pushed. The merge commit was built
  with git commit-tree (the merged tree is exactly the tree of Phase D, which passed on GitHub),
  so that the website on port 8000 did not have to stop; the commit-message guard was run by
  hand on its message. Phase E not merged: the owner's test rejected its screens.
- (1) research (sources in the report to the owner, 16 October): LLM reordering helps ranking
  more than recall (Anthropic contextual retrieval, 49% to 67% fewer failures with reranking,
  primary page read); PostgreSQL has websearch_to_tsquery, ts_headline (XSS and cost warnings),
  pg_trgm; Meilisearch's own page: PostgreSQL is enough for thousands of documents; NN/g:
  advanced search and scopes are rarely used; Baymard: misspellings in autocomplete.
  Measured six ways (`9d72cac`, `20261016T023934Z-search-modes.json`) and with typing errors
  (`6413447`). Default now the 30 closest by meaning put in order by Flash at LOW, 8 s limit
  (`df6bff1` refactor, `16c9429` feature). No spelling layer, no separate engine, no
  autocomplete, no operators for now (reasons in DESIGN 8.2).
- (2) design research: htmx case studies (Contexte, OpenUnited), the "AI look" (purple
  gradients, Inter, four cards, glass, emoji), list-detail pattern (Microsoft, PatternFly),
  axe-core coverage (about 57% of issues, Deque). Real search products looked at in Chromium:
  hn.algolia.com, Typesense books demo, Meilisearch where2watch. Rebuilt S1 and S2 as one page
  (`fddd26f` assets, `100110d` engine modes, `4f19d2b` compare time limit, `d29388c` redesign,
  `bd2249a` main headings and axe test, `25621cc` docs, `a1fd8bd` sentence of the order).
  Fonts Atkinson Hyperlegible Next and Mono (Braille Institute, OFL). axe-core 4.14.0 finds no
  WCAG A/AA problem on the start page, a search, an open card and the method page, wide and
  phone, light and dark (a test in the suite).
- (3) answered in the report: no "messy" rule exists; the card step runs on every full page of
  a set; only the 75 pages of the two sets have cards. Every use of a model, with its cost from
  the ledger, is in the report.

Measured on the live site: results in 0.7 to 2.8 s; the comparison usually 5 to 9 s, once 75 s
(now given up after 30 s, the page says when it is slow).

## 16 October 2026, morning: the owner's 18 points and the third version

The owner tested the second version: "You made a little UX progress thats it". Their points, short:
(1) ten cards; (2) cards side by side, no "The card of a project opens here"; (3) a card opens
when clicked, no prior notice; (4) filters in one row under the search; (5) "How it works" as a
pop-up, the project as a window over the page (80% or less, a little transparency); (6) numbered
pages; (7) no navbar, a footer with a signature, "how it works" and a FAQ, and a first screen with
a signature; (8) an (i) on each thing instead of documentation, and numbered references to
outside sources, Hedera first ("imagine the backlinks it will build for hedera"); (9) "no UI
aesthetic ... government design built by boomers", change the stack if it does not help; (10)
never refresh a search; (11) real-time search without AI, with the person aware of it, and a
button that says what the AI does; (12) the caches; (13) why AI for everything, and how a card
helps the search; (14) where are the charts, and their view on AI judges, into the vault; (15)
hover on phones; (16) their list of the AI look, AI images are fine (their Matafi site); (17) the
new use of GitHub in "check a submission" is allowed, with a design, a method, and whether AI is
needed; (18) the cards question waits for the 17.

Research of the day (read 16 October): WCAG 1.4.13 (dismissible, hoverable, persistent);
Inclusive Components on toggletips; MDN Popover API and interest invokers (Chromium 142, not
Baseline: not used); Baymard on horizontal filter bars (up to 6 to 8 filter types, options hidden
until opened, 2024: be careful); Material and SAP Fiori on full-screen dialogs on small screens;
debounce and live regions for search as you type (Scott O'Hara); NN/g on skeleton screens (video
page only); Chrome docs on view transitions (not used); LLM-as-a-judge: MT-Bench abstract (arXiv
2306.05685, read), UW CV study (read), codebook annotation (arXiv 2311.11844, search summary).
The owner's matafi site was looked at in a browser on their request: warm off-white, IBM Plex
Sans, an AI-made line-art background, an orange accent, a dark footer with columns.

Decided and built (the stack stays; reasons in the report and decisions.md):
- `b856c96` the answers of the search model kept for one day (migration 0011, idea_orders and
  idea_comparisons, exact keys only).
- `631e1bb` projects linked across events (search/seen.py). A first try counted only the
  projects whose ID the ledger confirmed: an ID named by 87 projects and the tutorial number
  0.0.1234567 linked projects. Found by checking the groups before showing them; fixed.
- `fbf5784` evals/overview.py and two result files (3 groups with the first rule, 2 with the
  fixed one): 826 projects, 26 events.
- `1a71a96` Newsreader 5.3.0 for titles (OFL, sha512 checked).
- `4b30111` the third version of the page: quick results while typing (meaning or words, no
  writing model), the Gemini button (order and comparisons, from the one-day memory when the
  same search comes again), ten cards in a grid with numbered pages, filters in one row, the
  project in a window over the list (back closes it without a request), no navbar, a footer with
  three windows (How it works, Common questions, Sources and references), an (i) on each term with
  numbered sources (17 references, Hedera docs first, each address opened on 16 October), the
  overview with four bar charts, the events table and the linked groups, a first screen of about
  one second once per visit, grey shapes while Gemini works, the last search kept in the browser.
- `d417e97` DESIGN 8.2, 12.1, 12.2 and the README. `3945599` the old method template removed.
- Tests: 1507 passed at the last commit (`3945599`); axe finds nothing on five states, wide and
  phone, light and dark.

Measured: the same Gemini search ran four times in a browser this morning; the cost ledger shows
1 rerank call and 1 compare call since 03:30 UTC. All 658 full pages have exactly the two titles
of ETHGlobal's form ("Project Description", "How it's Made"); none has a Problem or Solution title.

## 16 October 2026, afternoon and evening: the owner's 17 points and the fourth version

The owner tested the third version ("You did almost a perfect work on UX but") and wrote 17
points: (1) the header row is still there; (2) odd spacing in the project window; (3) does "a
Hedera prize" mean a winner entry; (4) "I honestly couldn't digest the UI, it's so demoded. Is
there any chance htmx can become like react or bootstrap [...] if you are going to keep retrying
and then keep preaching me about how it will take a day to pivot, that day was actually taken in
this htmx war"; (5) the Gemini note on a card much smaller; (6) an (i) for "show the quick order"
and its opposite; (7) the filters do not follow the search; (8) a clear search button; (9) use
the width, "probably the github implementation part?"; (10, 11) charts for any list, not static;
(12) bullets in the (i) texts; (13) event names linked; (14) a timed job for signs of life; (15)
events with no year; (16) "Implement your github suggestion."; (17) "Run the whole gemini
cards." Then: "stop the gemini background task and checkpoint it" (done at 116 cards), and "you
can continue now".

Built (all on `phase-e-website`, pushed):

| Commit | What |
|---|---|
| `7b71282` | (15) the typed year of the 12 events that no page dates: migration 0012 `events.year`, `data/by-hand/event-years.txt` (each year from the organiser's post), the parse step writes them; the filters and charts use end, start, then the typed year. |
| `b81bce1` | refactor: `search/counts.py` (`tally`) counts a list of facts; `filters.Facts` also carries the prize, the kind of entry and the confirmed kinds of IDs. The overview job uses it. Checked on the real tables against `20261016T050441Z-overview.json`: 0 differences of prize, proof, life and services over 26 events. |
| `4066725` | (4) Tabler 1.6.1, Chart.js 4.5.1, IBM Plex Sans 5.3.0, each checked against npm's sha512 (`scratchpad/fetch_ui_kit.py`). The commit guard refused Tabler's CSS: its class `bg-pattern-blueprint` matched the rule for the private design notes. The guard (`.git/hooks/check_public.py` and its copy in `tools/hooks/`) now removes exactly that class name before the rule is applied, in the commit check and in the push check (which now reads each matching line). A canary commit object with "the blueprint" in a file is still refused; one with only the class passes. |
| `1daa5b7` | (1 to 13) the page on Tabler: no header row, the idea box wide with the check box beside it, cards and charts for every list (Chart.js, numbers also in a hidden list for screen readers), filter counts over the 50 closest of a search with a chosen value kept at 0, a Clear button, the switches Quick order / Gemini's order and Cards / Charts each with an (i), the Gemini note at 11 px, "Won a Hedera prize" and "Only in the winners' list" as two tags, one bullet per status in the (i) texts, event names linked (ETHGlobal `/events/<slug>`; the others: the organiser's post). Contrast: axe on the three sample projects found only one problem, but on the real collection it found Tabler's teal (2.98:1 with white text), the green and grey pills (2.39 and 4.06:1), marks inside grey text (3.58:1) and a link in grey text without underline. Fixed: light teal oklch(50% 0.105 165) (5.7:1), dark teal oklch(74% 0.13 165) with dark text (8:1), pill and badge text mixed 55% towards black or white, a step of the pager that leads nowhere hidden. Then 0 problems in 7 views x 2 themes x 2 widths (`scratchpad/axe_live.py`). |
| `3501612` | refactor: `check/asking.py` (the facts of an ID from the table or the node, and the one more question of the proof rule), used by the step and the check. |
| `13e27ac` | refactor: the two queries of the linking rule as named constants (still 2 groups of 7 projects on the real tables). |
| `2b7b191` | (16) S3, the check of a submission (`check/submission.py`, `/check`): GitHub facts and README through the polite client (saved, never asked twice), at most 5 IDs of the README judged by the proof rule on the named network or both, the life rule with the submission's own IDs, "seen before" by repository or confirmed ID (shared services excluded, the submission counted as one more user), the 5 closest past projects by the meaning of the README (an embedding only). In the window, with its steps while it runs; a page of its own without JavaScript. |
| `291378c` | S4, the register (`hedera/registry.py`, `/register`): record version 1 `{"v":1,"event","code","account"?}` with SHA-256 fingerprints only, refused above 256 bytes or in another form; written by the tool's account, read back from the mirror node, receipt with number, time and HashScan link; never twice for one code and event; `python -m hackathon_memory.hedera.registry open` creates the topic and checks its keys. The topic is NOT created: it waits for the owner (Q38). |
| `7202584`, `73648d3` | DESIGN 7.3, 9.3, 12.1 and the README. The blueprint got the same changes (version 0.23; the table of versions had stopped at 0.20 while the header said 0.22, so a row says that 0.21 and 0.22 were not written there). |

Measured:
- The check on the real site: a repository of the collection (`uok825/ethprague-contragent`, ETHGlobal Prague) in 0.5 to 2.8 s with no request to GitHub and the ledger answers from the table (asked 11 October); proof found for a contract and an account, "seen before" by its repository, life stopped. A new public repository (`hiero-ledger/hiero-sdk-python`, typed days 1 to 20 October 2026) in 4.8 s with exactly 2 requests to GitHub (the count went from 1,349 to 1,351); no ID, life too early to tell.
- The mirror node, 16 October 2026, on the proof topic `0.0.10961154` of Gate A: `sequencenumber=gt:0` and `gt:1` gave no message, `sequencenumber=1` and `gte:1` gave message 1. The register pages with `gte`.
- Tests: 1,551 at `291378c`.

The cards run of point 17 went on at 17:45 with the same command (it skips made cards): 302 of
658 card-form-2 cards at 18:36 UTC.

Not done, and why:
- (14) a timed refresh of every repository and ID: not built. The check step already asks the
  ledger again after 7 days; but reading GitHub's facts again for 653 repositories breaks "nothing
  asked twice", a promise of the tool for GitHub, so it is a new way of using the site and the
  owner decides (Q40).
- The register's topic and a first real registration (launch gate 3): writing to the ledger, so
  the owner decides (Q38).
- Live counts on the charts against hard constraint 6 (Q39).

### Review layer 1 of the fourth version, and the launch gates (16 October 2026, evening)

- Review layer 1 of S1 to S5 on the real collection (`evals/review/2026-10-16-layer1-fourth-version.md`, `ccea91d`): 6 sure findings, all fixed (`052703c` a filter narrows the 50 closest, so "2025 (16)" gives 16; the others in `2b7b191` and `ccea91d`), 3 unsure for layer 2 (common words marked, the sideways filter row on a phone, winner entries first for the street-vendor idea).
- Gate 5 struck in `CLAUDE.md`: `evals/results/20261014T235346Z-test2.json` (34 of 57, under 80%).
- Gate 8, checked: `python -m hackathon_memory.secret_scan`, 7 secret values in 228 commits of every branch and tag: clean. Not struck: it must hold on the day of submission.
- Gate 12, checked: the guard over the tree of every branch and tag: exit 0; every message and author of the 228 commits: no rule broken; no path of `CLAUDE.md`, `backlog/`, `docs/`, `data/` or `.env` in the whole history. Not struck, for the same reason.
- CI: green on every push of the branch on 16 October.
- Open: gate 1 (CI shows a clean install and the tests; the start of the whole project with data is not tried), gate 2 (rebuild; the cards cannot be made again without paying, so the plan must say what "counts matched" means for them), gate 3 (Q38), gate 4 (the owner's grades of Test 1 for card-form-2), gate 6 (Test 3 does not exist yet), gate 7 (layer 2).

## 18 October 2026: the owner's queue, built

The owner's words of 18 October: "1. For A Yes 2. For C leave it ofcourse, we are not
guaranteeing success, its the most logical result and it already gives them some insights that a
close project existed. 3. check if the dates exist and write them by hand. 4. Execute all queue
work". The queue was written on 17 and 18 October (decisions.md).

| Item | What it does now | Commits |
|---|---|---|
| (1) The hackathon of the check is optional | The list of the check offers "No hackathon: show the facts only", the past hackathons whose days are known (each with its days), and "Another hackathon" with typed days. Without a hackathon, every fact keeps its own date, no proof is judged ("Proof: found, dates not judged"), and the register box says that a registration names its hackathon. An (i) says why: the tool is a memory of past hackathons, not a live view. | `21f6c0b` |
| (7) Projects open in the window | A project of "Seen before" or of "The closest past projects" opens in the project window of the page, with a button "Back to the check". | `21f6c0b` |
| A: common words | 43 common words ("app", "platform", "user", "without" ...) are no longer marked in the results. A cut by frequency would not work: "payment" stands in 35% of the projects, "app" in 14%. | `e02c329` (refactor), `dd40f82` |
| (2) Compare with Gemini in the check | A button under the closest projects. Gemini 3.8 Flash at LOW compares the README with the cards of the five closest projects; the answers are kept one day, as for the search. | `a91100b` |
| (3) The register keeps the commit | Record version 2: `{"v":2,"event","code","commit","account"?}`, at most 384 bytes. The check asks GitHub for the newest commit (a third request); only its ID and its date are kept, the names and the addresses of people are dropped before saving. A registration without a known version is refused. | `e4ce80d` |
| (5) Single transactions | A transaction ID (`0.0.N-seconds-nanos`; the "@" form is changed to it, because the mirror node refuses it, measured on 18 October) is its own kind of Hedera ID. The mirror node says what the action was, whether it succeeded and when; the proof rule judges it by that moment; a failed one counts as empty. Migration 0013. A batch is named in plain words. | `f72de14`, `23cd3ac` |
| Point 3: typed days | The years file may carry the first and the last day. The saved posts give them for four events: the building stage of Beyond Blockchain 2023 (26 May to 25 June 2023), Hello Future 2024 (22 July to 20 August 2024), Hello Future 2.0 (11 November to 18 December 2024), Hello Future Origins (21 July to 8 August 2025). The eight others give only a length or nothing. The days change no mark: no winner entry has an ID or a repository. | `774aad3` (refactor), `072ebbe`, `066b2c1` |
| (6) Measure B | `evals/compare_inputs.py`, on the owner's 9 ideas of Test 2: cards against full texts, a middle time of 7.1 s against 7.8 s, 4.3 against 7.7 cents for the 9 ideas; one call on a full text failed after 342 s (`evals/results/20261018T044605Z-compare-inputs.json`). The sentences side by side for the owner: `data/evals/compare-inputs/20261018T044605Z.html` (local, not in git). The owner reads it after going through Test 2. | `ea1586b` |
| (4) README, design, overview | The overview file now counts the cards: 658 cards, 8,909 of the 8,931 quotes found word for word, 4 fields dropped (`evals/results/20261018T050534Z-overview.json`). README, DESIGN and the blueprint (0.24) follow the queue. | `90d27a6`, `fd89f4c`, `b72097b`, `2013e91`, `758a761` |
| Seen on the real site | The version line had only the day of the other facts of GitHub (12 October), so the version seemed as old. It now carries its own day. | `5cb6546` |

Measured on the real collection (18 October):
- The check step with `--max-age-days 30`: 259 new answers of the mirror node; 223 transactions in
  93 projects; 90 of these projects show a transaction as proof, and none depended on it: the
  proof counts of the projects did not change (272 found, 6 dates do not fit, 4 another kind,
  3 not found, 541 no ID given).
- A real check through the website, after the restart: `uok825/ethprague-contragent` with no
  hackathon, 1.9 s with one request to GitHub (the newest commit, `3c881c87c943`, made 1 June
  2025), then 0.7 s with none. "Proof: found, dates not judged", six project links that open in
  the window, and the register box asks for a hackathon.
- Tests: 1,577 at `5cb6546`. Pushed: `phase-e-website` at `758a761`, then `5cb6546`.
- Cost on 18 October: `test` 12.38 of 15 dollars (83%, the website runs in it; about 0.6 cent a
  search with the Gemini button); `prod` 30.02 of 30 dollars, at STOP after the cards run.

What went wrong:
- The README said 7,315 of 7,333 quotes found. The count of the whole table is 8,909 of 8,931.
  The first number came from no dated file. Found before the commit, by looking for the file of
  every number (lessons.md).
- An example in the code (`072ebbe`) and a paragraph of DESIGN quoted a few words of a saved
  post of Hedera. DESIGN was fixed before its commit, the code in `066b2c1`; the four words stay
  in the history of `072ebbe`, which is pushed (lessons.md).

Not done, and why:
- The register's topic and a real registration: the owner said no write of their own
  repository for now (Q38).
- The choice between cards and full texts for the comparison: the owner reads the side-by-side
  page first.

## 18 October 2026, day: the second queue

The owner's word: "Alright, proceed the execution", after their questions on transactions, the
linked projects, the budget, the register and the branches were answered (decisions.md, 18
October).

What changed:
- **The check page (their point 4).** The button "Compare these 5 with Gemini" stands at the head
  of the closest projects; an empty place of a comparison takes no room; "Back to the check" is
  grey at rest and readable in both themes; one line names what was read from GitHub on which
  day; the version names its branch (GitHub's default branch, from the saved facts).
- **Linked projects (their point 3).** An ID that two teams with other code name at one event is a
  shared service. Before the fix, three teams of ETHOnline 2026 named one account of the main
  network and the old rule joined them, with a fourth project, into one group. The groups went
  from 2 with 7 projects to 2 with 5: YourTurn (one repository at Cannes, New York and ETHOnline
  2026) and Froggy with Hands Unchained (one test account, one GitHub owner). The card of a
  project names its linked projects (5 projects have one), also when opened by its address; the
  charts show them first, with their number.
- **The README of a check stays out of the address of its comparison:** the button names the
  repository, and the server reads the README that the check saved.
- **One sentence under the results of an idea:** "Building this? Before you submit, check your
  GitHub link here." The link puts the cursor in the box of the check.
- **The register.** A registration names a hackathon of the list (the events of the collection,
  and `hedera/listed.py`: "FSS Campus Edition 2026", no days yet); typed days serve the check
  only. A registration needs the team's line in its README (`hackathon-memory: XXXXXXXX`, made
  from the event and the fingerprint of the link); at the press the README and the newest version
  are read again from GitHub into a new folder (`data/raw/api.github.com/register/<time>`), so
  nothing saved is replaced.
- **Measure B graded** (their point 2, `evals/results/20261018T085521Z-compare-inputs-grades.json`;
  the sheet with the reasons is `data/evals/compare-inputs/grades-20261018.json`): of 80 pairs
  with both answers, the full text was more specific in 30, alike in 50, the card never; where
  the answers disagreed on a fact (8 projects read on their page), the card's answer was wrong 3
  times and missed the main likeness 3 times, the full text's never. The comparison keeps the
  cards (the owner: too expensive); the insight is in the design (§8.3).
- **The visual review** (their new mission, `evals/review/2026-10-18-visual-review.md`, pictures
  in `data/review/2026-10-18/`): 12 findings, 9 sure and fixed (a wrong link stuck on the steps
  of the check and a refused registration that showed nothing, because htmx 2 names the target in
  `htmx:beforeSwap`; the contrast of "Back to the check" in the dark theme and of the line's box;
  the linked box on a shared address; a chart label cut at the left; an empty cell of the charts;
  the narrow table of "How it works"; "not typed in" for days that nobody announced; the long
  name of the FSS hackathon in the list), 3 unsure for the owner.
- **The cards are saved** (their point 3 of the morning: "Yes please save the cards and be
  careful"): `data/backups/20261018/db.dump` (the whole database, 15 MB, restored into a scratch
  database: the 18 tables had the same counts), `cards.jsonl` and `cards-export.jsonl` (every
  card, 763 rows, of which 658 card-form-2 with 8,909 of 8,931 quotes found). The card step can
  write the cards to a file and put them back without a model (`cards --export`, `cards --restore`).
- **The rebuild (launch gate 2):** built again into a new, empty database (`evals/results/20261018T102138Z-rebuild.json`): 33 of 36 counts the same, among them every count that the site uses; the 3 others are one outdated card of card-form-1, refused because its page text changed after it was made. The ledger statuses came out the same after the mirror node was asked again (4,857 requests); the 826 embeddings were made again (12 cents, copied into the cost ledger in use); 762 of 763 cards came back from the file. Launch gate 2 is struck in CLAUDE.md. Test 3 is begun: guideline, 50 pages, sheet and scripts (`8d746ff`, `063927f`); the hand check is next.

Commits:
- `a0859e4` feat(web): name the branch and the day of each GitHub read
- `5d7f061` fix(web): put the compare button at the head of the closest projects
- `ffee71a` fix(web): show "Back to the check" in grey before it is pointed at
- `edf5beb` refactor(search): decide the shared services in one function
- `8e79564` fix(search): treat an ID two teams name at one event as shared
- `d3259c2` refactor(search): read the projects and their IDs in one helper
- `7fbaf73` refactor(web): write the reason of a link in one macro
- `36c8e80` feat(web): name the linked projects on the card of a project
- `2740d52` fix(web): show the projects linked across events first in the charts
- `1cd58b7` fix(web): keep the README out of the address of a check's compare
- `558ee3b` feat(web): invite a builder back to check the code before submitting
- `81956b4` docs(check): stop naming the old rule of a shared service
- `f0426d1` feat(register): let a registration name only a hackathon of the list
- `2b931bf` feat(register): ask for the team's line in its README first
- `fd8a6f6` fix(web): show the error answer of a check or a register in its place
- `92190e2` fix(web): name the linked projects of a card opened by its address
- `b68b3b2` feat(read): save the cards to a file and put them back
- `128a816` fix(web): keep every chart label whole and fill the last row
- `fd5eaf1` fix(web): keep the short values of the ways to search on one line
- `451c0a2` fix(web): say that the end of an event is not known yet
- `217d361` fix(register): give the FSS Campus Edition a name that fits the list
- `b85c2ef` chore(evals): add the grades of the comparison on cards and full texts
- `a4edfb0` chore(evals): add the overview counts with the new rule of shared IDs
- `9404cd1` feat(evals): count a rebuilt database against the one in use
- `165c335` docs(design): describe the register's actors and the linked projects
- `8d746ff` test(evals): add the draw and the sheet of Test 3, with its guideline
- `063927f` chore(evals): draw the 50 pages of Test 3
- `63c56cc` chore(evals): add the counts of the database built again
- `c167e2a` docs(design): note the database built again and the start of Test 3
- `e176f20` docs(evals): file the visual review of 18 October
- `c7b1357` docs(readme): describe the register's line and the linked projects

Tests: 1,600 at the last commit of the queue.

What went wrong:
- A patch of a local script sent through a heredoc lost its backslashes, twice in one day.
- Four browser tests failed in a staged run: I had run only tests picked by name.
- The error answers of the check and the register were never shown in a browser; only the
  server's answers had tests.
- Staging hunks with `-U0` placed an inserted block after the lines that both versions share.
- The first grades file named "10 failed calls" for one failed call with 10 pairs; it was written
  again before its commit.
(lessons.md, 18 October.)

## 18 October 2026, evening: the third queue, and Test 3

The owner's ten points (decisions.md, 18 October): "Execute all of the above, execute your clean
ups and whats next, except for the register opening until I get my head around it with final
questions later".

What changed:
- **A button to the live demo** at the head of a card, next to the project's page and its code
  (510 projects link a live demo).
- **The register box at the head of the check,** in the empty space beside the title; with no
  hackathon given, when the collection keeps a project with the same code, the box names that
  project's hackathon and asks "Is that the hackathon you register it for?", with a button that
  checks the code again for it.
- **The list of hackathons in groups** (the browser's own list): running now, coming, then one
  group per year; the days leave out the year of their group. The FSS Campus Edition starts on 10
  August 2026 (its registration), its end not announced: "Running now", "from 10 August 2026".
- **"How it works" wider** (1040 pixels), its table on the whole width with lines; its steps have
  their numbers again (the class `steps` was Tabler's component); a time stays on one line.
- **A switch of the theme** (light, dark, auto) in a header row at the top right of every page,
  kept in the browser, applied before the page is drawn, charts drawn again.
- **Errors in plain words:** a 404 or 503 of a card is shown, a request with no answer ends the
  waiting state with a message (and keeps the way back to the check), the list keeps what it
  showed with a line above it, 90 seconds at most, and a page for an error no route expects.
- **The comparison is told that a card is a summary** (compare-2). Checked once on the three ideas
  whose answers were wrong in measure B (`data/evals/compare-inputs/wording-*.json`): the answers
  that say "does not" now speak of the texts.
- Screens seen by eye on the running site (`data/review/2026-10-18-third-queue/`, 11 pictures);
  axe finds no problem in four runs; 21 browser tests pass.

**Test 3 (launch gate 6, struck).** 50 pages and their READMEs read by hand
(`data/evals/test3/hand-notes.md`, answers in `answers.json`), facts from the mirror node with
plain HTTP, statuses by design 7.2. Result `evals/results/20261018T185311Z-test3.json`, report
`evals/test3/report-2026-10.md`: found 156 of 156 (met), status 148 of 156, 94.9% (met), added by
the tool 22 of 178, 12.4% (not met: 10 of hanvil's local network, 5 example values, 7 schedules).
What went wrong, in order:
1. My reading aid (t3_reader.py) cut 42 of 47 READMEs at their first code block, because the
   sheet wraps each README in three backticks. I read the cut READMEs and ran the test: found
   100%, added 70%, status 92%. That run is not valid; its file is kept apart
   (`data/evals/test3/invalid-20261018T183921Z-test3.json`). Its output showed part of the tool's
   list (about 60 rows, ten projects), so the second, full reading of those READMEs is not blind.
   The owner decides whether the public report says so (not written there yet).
2. The facts script read the time of a contract's call from the wrong field: every contract
   showed no activity. Fixed with a test before any status was written.
3. Test 3 compared transaction IDs as text; the tool writes the nanoseconds without leading
   zeros. Fixed with a test, before the valid run.
4. The sheet now uses a fence longer than any fence in its text (for a future sheet).

**The start from a clean copy (launch gate 1, struck):** a clone of `f38aa70` with the README's
commands, in `.cleancopy` (excluded from git): install, `.env` with a password, the database healthy,
the migrations, 1,614 tests passed, `setup_check` named only the stranger's secrets, the website
answered; the copy's database had its own Docker project (`-p hm-clean`) and port (55433) because
the real one runs here. The first attempt, from the session's temporary folder, stopped in `pip`
on Windows' path limit (lessons.md). Log: `data/review/2026-10-18-clean-copy.txt`.

The secret scan is clean (7 values, 286 commits). The video script is `docs/video-script.md`. The
README for judges is the README as it stands, with the new features and Test 3.

Commits (19):
- `f9a3c1d` feat(web): add a button to the live demo at the head of a card
- `921ce04` feat(web): move the register box up and offer its hackathon
- `932e8cd` feat(web): group the hackathons of the check by year
- `5a13096` fix(register): give the FSS Campus Edition its first day
- `9ba6ec8` fix(web): give the table of "How it works" the whole window
- `8c2bc12` feat(web): add a switch of the theme at the top of every page
- `87f7948` fix(search): tell the comparison that a card is a summary
- `a7c8402` fix(web): say what happened when a request fails
- `69d254f` fix(web): give the steps of "How it works" their numbers
- `0260b35` fix(web): give the numbers of "How it works" more room
- `1401a24` docs(design): describe the fifth version of the page
- `f38aa70` docs(readme): describe the switch of the theme and the offer
- `924e199` fix(evals): read the time of a contract's call in Test 3's facts
- `35ab98e` fix(evals): give a transaction one spelling in Test 3
- `4ced4d4` fix(evals): keep a README's code blocks inside Test 3's sheet
- `2ad598d` chore(evals): add the result of Test 3
- `540b012` docs(evals): add the report of Test 3
- `01b8f77` docs(design): note the result of Test 3
- `e503303` docs(readme): add the result of Test 3
