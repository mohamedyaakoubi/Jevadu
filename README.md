# Jevadu

One place that knows every project sent to a Hedera hackathon: what it claimed, what really happened, and whether it is still alive.

Jevadu is not affiliated with, sponsored, or endorsed by Hedera Hashgraph, LLC.

> **State on 21 October 2026:** The proofs of Gate A passed, and so did Gate B, the first full path from a saved page to a search. Every project of the allowed sources is collected, parsed and checked on the ledger. The cards written by the model and the three tests of quality have run. A website runs on one laptop: the search, the card of each project, insights and charts of every list, the check of a submission and the register on Hedera. The register is open: its topic [`0.0.11126502`](https://hashscan.io/testnet/topic/0.0.11126502) on the test network has no admin key, and no registration is written in it yet. See "What works today" below.
>
> **Where the data comes from.** ETHGlobal was asked before any program read its showcase. It agreed in writing to a slow, signed read of its Hedera prize projects, and the other projects that its showcase ties to Hedera are read in exactly the same way. The pages stay on one laptop. Devpost said no, so no program reads Devpost. DoraHacks and AngelHack have not answered yet, so no program reads them.

## Why

Hedera has run at least 12 big hackathons since 2018, with more than 2,100 projects that we could count. They sit on at least five different websites. So:

- builders rebuild old ideas without knowing it;
- a judge cannot tell quickly whether a project is a repeat;
- every team writes "we use Hedera", and nobody can check it quickly;
- nobody knows which past projects are still alive.

## What it will do

| For | It answers |
|---|---|
| A builder | Was my idea already built on Hedera? What happened to it? |
| A judge | Is this submission's Hedera proof real? What is close to it? Was it sent before? |
| An organiser | What did our past events produce? |

## How it works

1. **Collect.** A program reads the public project pages of past hackathons and saves them, without the part that shows the team members. It does this only where the site's terms allow it or the site said yes in writing.
2. **Parse.** Ordinary code pulls out the name, the links, the Hedera IDs and the titled sections. No AI.
3. **Read.** An LLM gives every project the same structure. Each field it writes carries a label and exact quotes from the page, and code checks every quote.
4. **Check.** The Hedera mirror node says what each ID really is and when it was active. GitHub says when the code was written, and the code itself is read for its Hedera packages, imports and calls. No AI.
5. **Link and search.** The tool finds the past projects closest to an idea and shows the facts side by side.

## Where Hedera is used

- **Reading.** The public ledger is the ground truth for every claim a project makes about Hedera.
- **Writing.** A public register on a Hedera topic. A team registers a fingerprint of its own submission, after it adds a line that the tool gives to its README, and gets a timestamp that nobody can change. If the same fingerprint appears again at another event, the tool says "seen before". The register's topic is [`0.0.11126502`](https://hashscan.io/testnet/topic/0.0.11126502) on the test network, created on 22 October 2026 with the memo "Jevadu register".

## What the AI may and may not do

It may read pages, give them structure and find similar ideas. It may not give a score, pick a winner, say that a project is a copy, or state a fact. Facts come from the parser, the code host and the ledger.

## What already exists

Solana's hackathon organiser built this idea for Solana: [Colosseum Copilot](https://github.com/colosseumorg/colosseum-copilot). It runs inside a builder's coding agent, on the submissions of Colosseum's own hackathons, and its own page says its records show "what teams submitted, not what they run today".

Two hackathon projects search past projects too. [ETHSearch](https://github.com/pauldev20/ethglobalsearch) searches the projects of ETHGlobal's showcase by text and by meaning. [HackathAttest Agent](https://github.com/TheSoftwareDevGuild/the-guild-attestation-intelligent-agent), from ETHOnline 2025, answers questions about past hackathon projects from attestations on Arbitrum.

We found nothing like this for Hedera. Jevadu keeps the projects tied to Hedera, and adds what the ledger and the code say about each one.

Many tools score hackathon submissions with AI. DoraHacks' Hackathon AI, for example, gives each submission a score and feedback against the organiser's criteria, can approve every submission that reaches a score the organiser sets, and ranks the approved projects of each track, with its reasons, as a guide for the human judges ([its own article](https://dorahacks.io/blog/guides/hackathon-ai/)). Jevadu does not score: it puts the facts side by side, and people judge.

## What works today

First the four small proofs that the ground holds (Gate A), then what runs on the real data today, the three tests of quality, and the website.

| Proof of Gate A | State on 11 October 2026 |
|---|---|
| Database: PostgreSQL with pgvector answers a vector query | **Passed.** 3,000 vectors of 3,072 numbers, the right neighbours first, an exact search in 27 ms. The result file is in `proofs/results/`. |
| Hedera write: a topic with no admin key, a message, read back from the ledger | **Passed** on the real test network. The topic has no admin key and one submit key, a 102-byte record was read back from the mirror node, and a topic with a stranger's submit key refused our message. The result file is in `proofs/results/`. |
| Google models: the two Gemini layers (Gemini 3.1 Pro reads the pages, Gemini 3.8 Flash does the search) and one embedding call | **Passed** on the real service. Both models returned a valid form for one real text, and the embeddings have the right size. The result file is in `proofs/results/`. |
| Lists: the ETHGlobal collector | **Passed** on 11 October 2026. A walk read the 21 pages of the showcase list with the filter "partner: Hedera": 658 projects in 14 events. A run read the page of every one of them and kept all 658, each without its team part: 92 with a Hedera prize, 81 with a prize of another sponsor only, and 485 with no prize. On every page the block "Winner of" agrees with the list. 732 requests were sent to the site in all, out of the 800 that the tool allows itself for it. The result file is in `proofs/results/`. The pages are not in this repository. |

Two more things work, and both were run on the real services:

- **The cost of the models is counted.** Every call to a model leaves one line in a ledger: the model, the tokens, the time, the cost. A budget stops a call before it is made when it could go over the cap. `python -m hackathon_memory.finops report` shows where the money went. The ledger holds numbers only, never the text of a call.
- **The history is searched for secrets.** `python -m hackathon_memory.secret_scan` looks for each secret of `.env` in every commit.

The tests (1,600 of them on 18 October 2026) run on every push, and pass on a clean Linux machine. They do not prove that the services answer as the code expects. That is what the live runs of the proofs are for.

What runs on the real data today:

- **The parser.** It reads every saved project page into its facts: the name, the short line, the event, the prizes, the links, the two texts word for word, and the Hedera IDs with their network and kind. It refuses a page whose visible part and data disagree. Words about people that a team wrote into its texts are hidden first (design 5.4).
- **The check on the ledger.** Every Hedera ID is asked of the public mirror node, and the proof rule of design 7.2 says whether the dates fit the event. A single transaction that a page or a README names is judged by its own moment: what the action was, whether it succeeded, and when (design 7.1).
- **The README of the code.** The README of each project's repository is read once through GitHub's API, cleaned of the part about the team, and searched for Hedera IDs, which are then checked like the IDs of a page (design 7.3).
- **The facts of the code and the life rule.** The dates of each repository (made, last push) are read once through GitHub's API, without anything about the account that owns it. With the activity of the project's own IDs on the ledger, they say whether a project is active, quiet, stopped or too early to tell. Only a change later than 30 days after the event counts as a sign of life (design 7.4).
- **Hedera in the code.** The code of each repository is read once, whole, from the archive of its default branch, which GitHub's API gives; the archive is read on the computer of the tool and not kept. Plain text matching finds the Hedera packages that the package files name, the files that import a Hedera library, the Hedera services that the code calls (by the class names of Hedera's SDKs), other signs such as Hedera's JSON-RPC relay, a Hedera chain ID, a Hedera network of an EVM tool, the system contracts or the mirror node, and the files that only name Hedera. Folders of other people's code are skipped, and .env files are never opened. Only what was found is kept, with the commit that was read, so every file opens on GitHub as it was read. It shows what the code names, not whether it runs (design 7.3). On 21 October 2026 the code of 579 repositories was read: of the 658 projects with a full card, the code of 508 shows a use of Hedera, 23 only name it and 50 show nothing, and of the 392 projects that name no Hedera ID, the code of 259 shows a use of Hedera (`evals/results/20261022T094650Z-code-findings.json`, counted again on 22 October 2026, after example numbers stopped counting as IDs). A reading took 3.45 seconds at the median and under 17.7 seconds for 95 of 100 (`evals/results/20261021T190159Z-code-times.json`).
- **The search, as a plain listing.** Each project is embedded with Google's embedding model. An idea is searched by meaning and by words, and the two lists are merged. Each result shows its facts and what the mirror node said about its IDs (design 8.2).
- **One command for the whole path**, and the proof of Gate B that runs it from an empty database, searches ideas written blind, and leaves the results to be marked on a scale of three: yes, n/a or no.

- **The cards.** Gemini 3.1 Pro reads a page and writes seven fields: what the project does, how it works, for whom, its Hedera services, its category, its problem and its solution. Each field carries a label and quotes, and a field whose quotes are not found on the page is dropped (design 6.3). Every one of the 658 full pages has its card (16 October 2026): 8,909 of the 8,931 quotes that the model gave were found word for word in their page, and 4 fields were dropped (`evals/results/20261018T050534Z-overview.json`). The 168 projects known only from organisers' lists of winners have none.

The three tests of quality, with their short reports:

- **Test 1, the fields of the model** (design 13.2): 60 pages, each card graded field by field against its page. In the second run, with the list of 17 categories, no field was graded wrong, 98.5% were fully right, 99.5% of the labels were right, and all four pass marks were met. See `evals/test1/report-gemini-3.1-pro.md`.
- **Test 2, the search** (design 13.3): of the known similar projects, 34 of 57 (59.7%) were in the first 10 results, under the pass mark of 80%. Most misses are tools for AI agents, a theme with many projects close to each other. See `evals/test2/report-2026-10.md`.
- **Test 3, the Hedera IDs** (design 13.4): 50 pages and their READMEs, every Hedera ID written down by a second reader (a language model that is not part of the tool) and checked against the mirror node. The tool found all 163 IDs that the reader found (pass mark 95%), gave 94.5% of them the same status (pass mark 90%), and counted 1 of its 164 IDs as the project's when it is not (0.6%, pass mark at most 2%): a number of a local test network. The first run, on 18 October 2026, counted 22 of 178 (12.4%). Three changes of the reader on 22 October brought it to 8 of 164 (4.9%), and 7 of those 8 were scheduled transactions, a kind of Hedera ID that the first guideline did not list. The maintainer then added schedules to the guideline, after that run, so the report gives both results. See `evals/test3/report-2026-10.md`.

The website, on one laptop: `python -m hackathon_memory.web` serves it at http://127.0.0.1:8000, for this computer only (design 12.1). Everything happens on one page. While an idea is typed, semantic results (or keyword results) appear as a grid of ten projects with numbered pages; no model writes anything for them. One button asks Gemini 3.8 Flash to sort the 30 closest and to say, for each of the first ten, what it shares with the idea and how it differs (design 8.2 and 8.3); its answers are kept for one day, so a reload or the back button never asks again. The card of a project opens in a window over the list, with buttons at its head for the project page, its code and its live demo, and names the projects that it is linked to by the same repository or the same Hedera ID. Filters in one row narrow the list by event, year, category, Hedera proof and activity after the event, and the switch "Insights" shows a few facts in sentences and the same list as charts, counted from the tables, with the projects linked across events first. Each term has an (i) that explains it, with numbered sources, Hedera's documentation first. The windows "How it works", "Common questions" and "Sources and references" open from the bottom of the page. A switch at the top right chooses a light or a dark theme, or follows the computer, and a request that fails says so in plain words. The page is built on Tabler, a design system on Bootstrap 5, with htmx and Chart.js.

A box beside the idea checks one submission from its GitHub link and, if wanted, its hackathon, from a list with the hackathons running now first and the past ones grouped by year (design 12.1, S3). The tool is a memory of past hackathons, not a live view, so without a hackathon it shows each fact with its own date and judges none. GitHub is asked for the dates of the code, the README and the newest commit, and the code is read for Hedera unless it was read before (up to 50 MB and 30 seconds; a larger archive is shown in part); the Hedera IDs of the README are checked on the mirror node; and the page shows the proof, the life of the code, the projects of the collection with the same code or the same ID, and the closest past projects by meaning, each of which opens in the same window. No model writes anything, except on the button "Compare these 5 with Gemini", which writes what each close project shares with the submission and how it differs. The team can then write it to the public register on Hedera's test network (design 9.2), from the box at the head of the check, for a hackathon of the list (when the collection already keeps the same code, the box offers that project's hackathon), once its README carries the line that the page gives: only who can change the repository can add it. One record of fingerprints and the commit ID only, read back from the mirror node, with its number, its time and a link to HashScan.

It is not online, and its screens have not passed their two reviews yet.

What does not exist yet: a first registration in the register (it needs a team's public repository that carries its line in the README), and the other facts of the code (the number of changes, the contributors).

## Run it

You need Python 3.11, Git and Docker Desktop. On Windows:

```text
python -m venv .venv
.venv\Scripts\python -m pip install -c constraints.txt -e ".[dev]"
copy .env.example .env        (only if you have no .env yet; do not copy over an existing one)
docker compose up -d --wait db
.venv\Scripts\python -m hackathon_memory.db migrate
.venv\Scripts\python -m pytest
.venv\Scripts\python -m hackathon_memory.setup_check
```

On Linux or macOS, use `.venv/bin/python` and `cp`. Fill `.env` with your own values: it is never committed. Put a password of your choice in `POSTGRES_PASSWORD`; it only protects your own copy of the database. The database keeps the password it was first created with: if you change it later, run `docker compose down -v` once (this deletes the local database) and start it again.

`setup_check` says which of the setup steps below are done and what blocks each proof. It prints no value.

### The setup steps

The steps have the numbers that `setup_check` prints. Each value goes into `.env`, and nowhere else.

| Step | What | Where it comes from |
|---|---|---|
| 1 | `HEDERA_OPERATOR_ID`, `HEDERA_OPERATOR_KEY` | A free test account at [portal.hedera.com](https://portal.hedera.com). Copy the account ID and the private key in the DER form (a long text that starts with `30`). The tool writes to the test network only. |
| 2 | `GITHUB_TOKEN` | GitHub, Settings, Developer settings, Personal access tokens, Fine-grained tokens. Choose "Public repositories (read-only)" and add no permission. It is used to read facts about public repositories. To let the tool read the READMEs, also set `COLLECT_GITHUB=on`. |
| 3 | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` | A Google Cloud project with the Vertex AI API turned on. The location is `global`. Sign in with `gcloud auth application-default login`. If you name a sign-in file, keep it outside the project folder. |
| 4 | `POSTGRES_PASSWORD` | Any password you choose. Then `docker compose up -d --wait db`. |
| 8 | `COLLECTOR_NAME`, `COLLECTOR_CONTACT_EMAIL` | A name for the tool and your own address. Both are sent in every request to a site, so that the site can see who reads it. Only needed to run a collector. |
| 9 | Project pages seen by hand | `data/by-hand/ethglobal.com/project-pages.txt`, one showcase address per line: projects that you saw yourself with "Winner of" and a line that starts with "Hedera". One is enough. The showcase list names a sponsor only by an id, and these pages tell the tool which id is Hedera. Only needed to run the ETHGlobal collector, and only with a written yes from the site. |

### The commands

| Command | What it does |
|---|---|
| `python -m proofs.database` | Proof 1, on the local database |
| `python -m proofs.hedera_write` | Proof 2, on the Hedera test network |
| `python -m proofs.google_models` | Proof 3, on Google's models (it costs a few cents) |
| `python -m proofs.lists` | Proof 4, on what the walk and the run left on disk. It sends no request: it checks that the rules for reading the site were kept. |
| `python -m hackathon_memory.collect ethglobal --plan` | Shows what the collector would read. It sends no request. |
| `python -m hackathon_memory.collect ethglobal --look` | Reads robots.txt and the first page of the hand-made list, and saves no page |
| `python -m hackathon_memory.collect ethglobal --find` | Walks through the showcase list with the filter "partner: Hedera" and writes down every project of it, with the sponsors of its prizes. It saves no page. `--pages 5` reads five pages of the list and can be started again. |
| `python -m hackathon_memory.collect ethglobal` | The run. It reads the page of every project that the walk found, and saves each one without its team part. `--pages 3` asks for three new pages, so the first saved pages can be looked at before the rest is read. `--pause 10` leaves ten seconds between two requests. `--wait` lets the run wait for the end of a cooldown by itself. |
| `python -m hackathon_memory.pipeline parse` | Reads every saved project page into the database. It sends no request, and a page that was read before by the same parser is passed over. |
| `python -m hackathon_memory.pipeline readmes` | Asks GitHub for the README of every project's code that is not saved yet, then reads every saved README for Hedera IDs. `--repos 5` asks for at most five new ones, `--no-requests` sends nothing, `--wait` waits for the end of a cooldown. |
| `python -m hackathon_memory.pipeline code` | Asks GitHub for the facts of every repository that are not saved yet (the same options as `readmes`), then writes them. |
| `python -m hackathon_memory.pipeline hedera_code` | Reads the code of every repository that was not read yet, whole, from its archive (two requests each, the same options as `readmes`), and writes what it says about Hedera. A repository that GitHub already said is gone is not asked for. |
| `python -m hackathon_memory.pipeline check` | Asks the Hedera mirror node about every ID and applies the proof rule. An answer is used again for seven days. |
| `python -m hackathon_memory.pipeline embed` | Makes the embedding of every project whose text changed. It costs money, through the meter and its budget. |
| `python -m hackathon_memory.pipeline all` | The six steps above, in order. |
| `python -m evals.sets draw` | Draws, once, the 15 pages for writing the instructions of the LLM and the 60 pages of Test 1, from six fixed groups (design 13.2). A set is never drawn again. |
| `python -m hackathon_memory.pipeline cards --set evals/sets/tuning.json` | Makes the card of every page of a set with Gemini, and checks every quote against the page (design 6.3). It costs money, through the meter and its budget; a card whose text did not change costs nothing. `--limit N` makes at most N cards. |
| `python -m hackathon_memory.pipeline cards --export FILE` | Writes every card to a file, with the address of its page. The file holds the model's answers with quotes of the pages, so it belongs in the `data` folder, out of git. |
| `python -m hackathon_memory.pipeline cards --restore FILE` | Puts the cards of such a file back into a database built again: a card comes back only when the text that the model read is the same, and its quotes are checked again. No model is called. |
| `python -m evals.code_times` | Counts how long the readings of the code took and how large the archives were, into a dated file of `evals/results`. It sends no request. |
| `python -m evals.rebuild <database in use> <new database>` | Counts the same things in the database in use and in one built again from the saved pages (its steps are written at the top of `evals/rebuild.py`), into a dated file of `evals/results`. |
| `python -m evals.cards_report evals/sets/test1.json` | Counts the cards of a set in numbers only (quotes found, labels, lengths, categories, cost) into a dated file of `evals/results`. |
| `python -m evals.test1.sheet` | Writes, once, the review sheet of Test 1 into `data/evals/test1`: each page next to its card, to be graded as `evals/test1/guideline.md` says. Open `sheet.html` there in a browser. `--name test1-card-form-2` writes the sheet of another run into its own folder. |
| `python -m evals.test1.report` | The numbers of Test 1, from the grades, into a dated file of `evals/results`. `--name` reads the sheet of another run. |
| `python -m evals.test2.ideas draw` | Writes, once, the list of projects for which the maintainer writes ideas in their own words (Test 2). `check` counts the written ideas. |
| `python -m evals.test2.run` | Test 2, the search test, into a dated file of `evals/results`. |
| `python -m evals.sets draw-test3` | Draws, once, the 50 pages of Test 3 from three groups: an ID on the page, an ID in the README only, and none found (design 13.4). |
| `python -m evals.test3.sheet` | Writes, once, the sheet of Test 3 into `data/evals/test3`: each page and its README, with every string shaped like an ID, to be checked by hand as `evals/test3/guideline.md` says. |
| `python -m evals.test3.run` | The numbers of Test 3, from the hand answers and the tool's tables, into a dated file of `evals/results`. |
| `python -m evals.search_modes` | Six ways to search on the cases of Test 2: the known projects found, the time and the cost of each, in numbers only. `--typos` puts two typing errors in each idea. |
| `python -m evals.compare_levels data/evals/test2/ideas.txt` | How long the comparison under the results takes at each thinking level, and what it costs, in numbers only. `--show` prints the sentences on the screen. |
| `python -m evals.overview` | The counts of the charts of the website, for each event, into a dated file: projects by prize, by Hedera proof, by life, by the kinds of Hedera ID the ledger confirms, and by theme, the projects linked across events, and the cards with the quotes found in their page. In numbers only. |
| `python -m hackathon_memory.hedera.registry open` | Creates, once, the topic of the public register on the test network, with no admin key and the tool's key as its submit key, and checks both keys on the mirror node. Then put the topic's ID in `.env` as `HEDERA_TOPIC_ID`. |
| `python -m hackathon_memory.web` | The website, at http://127.0.0.1:8000, on this computer only. `--port` picks another port. |
| `python -m hackathon_memory.search "an idea"` | The closest projects to an idea, as a plain listing with the facts of each one. `--numbers-only` shows no name or link. |
| `python -m proofs.gate_b` | Gate B, part 1: a new empty database, the whole path with one command, and the first 10 results of each idea of `data/by-hand/gate-b-questions.txt`, written to `data/by-hand/gate-b-results.txt` to be marked. |
| `python -m proofs.gate_b --questions Q --results R` | Gate B, part 1, for the ideas of another file of `data/by-hand`. |
| `python -m proofs.gate_b --marks R1 R2` | Gate B, part 2: reads the marks of one or more results files. An idea that expects close projects needs at least one result marked "yes"; an idea that says `expect: none` needs only its marks. |
| `python -m hackathon_memory.finops report` | Where the money for the models went, and what one project page costs |
| `python -m hackathon_memory.finops budget` | Where the two budgets stand |
| `python -m hackathon_memory.finops prices` | The prices in use, with the day each one begins |
| `python -m hackathon_memory.finops reconcile --billed 1.23` | Our own count against the amount on Google's bill |
| `python -m hackathon_memory.secret_scan` | Looks for the secrets of `.env` in every commit. It prints names, never values. |

Each proof writes a dated result file to `proofs/results/`.

## Design rules

The code and the tests point to these rules by number, for example "design rule 9". The numbers that are missing are about how the work is organised, not about the tool.

| # | Rule |
|---|---|
| 1 | The AI never gives a score, never ranks quality, never picks a winner, and never says that a project is a copy. It shows facts side by side, and people judge. |
| 2 | Facts never come from the LLM. IDs, links, dates, counts and statuses come only from the parser, the code host or the ledger. |
| 3 | Every field written by the LLM carries a label (stated, inferred or not found) and exact quotes from the page. Code checks every quote against the saved page. A field with no checked quote is dropped. |
| 4 | Parser first. A titled section is copied word for word, and the LLM is never asked to rewrite it. |
| 5 | A saved page is never edited afterwards. Before it is saved, the part that shows team members is cut out, and the page is written again by the parser: the text, the links and the order of the tags stay the same. One exception: personal data that is found in a saved page later is taken out, and the reason and the old fingerprint are written next to the page. |
| 6 | No number is shown unless it comes from a test with a dated result file. A model never grades its own work. |
| 7 | All LLM calls use Gemini on Vertex AI: Gemini 3.1 Pro reads and rewrites the pages, Gemini 3.8 Flash does the search. Embeddings use Google's embedding model. |
| 8 | Only a fixed fingerprint record goes to the Hedera topic. No free text, no names, no secrets. A message on a topic can never be deleted. |
| 9 | Secrets live only in `.env`. They never appear in git, in a log, in the database or in a test file. |
| 10 | The terms of a site are read before the first request to it. Requests go one at a time, with a pause, with the name of the tool and a contact address. A block is never worked around, and the tool never signs in. |
| 11 | No personal data that the check does not need: no names, emails or photos of team members. A handle, an email address or a link to a profile that a team wrote inside its own text is hidden before the text is stored. |
| 17 | No collector runs against a live site before the maintainer has said yes for that site and for the pages that will be read. |
| 18 | The way a site is read is fixed in the code, and each rule has a test. |

Comments in the code also name sections of the design, for example "design 5.7". The design is in [`DESIGN.md`](DESIGN.md), with the same section numbers. The most cited section is repeated below.

### How a site is read (design 5.7)

These rules are code, each with a test. ETHGlobal was asked before any program read its showcase. It agreed in writing to a slow, signed read of its Hedera prize projects, and the other projects that its showcase ties to Hedera are read in exactly the same way.

| The rule | What the code does |
|---|---|
| Only named pages | A walk reads one list of the showcase: the one with the filter "partner: Hedera". A run reads robots.txt and the pages of the projects on that list. No page of the list is saved. Every other address is refused before a request is sent. |
| A limit of requests | A fixed limit for each site: 800 for ETHGlobal's showcase. Every request is counted in one file, so the limit holds for all commands and all days together. |
| One time | A second run skips every page that is already saved, and every page that an earlier run read and did not keep. |
| One request at a time | One worker, a pause of two seconds, nothing in parallel. |
| Each request says who sends it | The name of the tool and a contact address are in every request. The collector refuses to start when one is empty. |
| No names, photos or profiles of team members | The team part is cut out before a page is saved. If a page shows a person where none is expected, the run stops. |
| Too many requests | When the site answers 429, "too many requests", the run stops at once. The tool sends nothing for one hour, or longer if the site names a longer time, and then it goes on five times slower. A third 429 within a day is taken for a no. |
| A no of the site | An answer of 401, 403 or 451, or a bot check, stops everything for that site. Nothing is worked around, and nothing is sent again until a person has decided how to go on. |
| It stops at once when asked | One switch for each site in `.env`, read again before every request. It is there for a stop order from the people who run the site. |
| The pages stay on one laptop | The data folder never enters git, and no text of a collected page is in a test file or a result file. |

## The event

This is an entry for the FSS Campus Edition of the Hedera Cross Campus Challenge 2026. It is built by one person, Mohamed Yaakoubi.

The line below lets this repository be registered for that event in the tool's own public register on Hedera. Only someone who can change the repository can add it, so it shows that the registration is the maintainer's own:

`jevadu: 5PZVM227`

## Licence and credits

Copyright 2026 Mohamed Yaakoubi.

The code and the documents of this repository are under the Apache License, Version 2.0, with its text unchanged. The full text is in [`LICENSE`](LICENSE), and the credit that travels with the code is in [`NOTICE`](NOTICE).

**If you copy or change Jevadu and share it,** the licence asks four things (its section 4): give a copy of the licence, mark the files that you changed, keep the copyright notices, and keep the credit of `NOTICE` in your copy. The licence gives no right to use the name Jevadu for another product (its section 6), so a changed copy should take a name of its own; it may say that it is based on Jevadu.

**Please credit the work you build on,** as Jevadu credits the work below. A line such as "Based on Jevadu by Mohamed Yaakoubi", with a link to this repository, is enough. GitHub's button "Cite this repository" gives a citation, from [`CITATION.cff`](CITATION.cff).

**Jevadu is built on the work of others:**

- htmx (0BSD), Tabler (MIT, built on Bootstrap, MIT), Chart.js (MIT), and the fonts IBM Plex Sans and Atkinson Hyperlegible Mono (SIL Open Font License 1.1). Their files and their licences are in `src/hackathon_memory/web/static/vendor/`.
- axe-core (MPL 2.0), which the tests use to check the pages for accessibility. Its file and its licence are in `tests/assets/`.
- The Python libraries named in `pyproject.toml`, each under its own licence, among them the Hiero SDK for Python.
- Hedera's public mirror node and HashScan, for every fact of the ledger, and Google's Gemini models, for the cards and the search.
- The projects themselves. Their pages and their code belong to their teams, and every card links to the page it comes from. Where the data comes from is said at the top of this README.

The licence does not cover the pages of other people's projects that the tool reads. Those belong to their authors, and they are not stored in this repository.
