# Hackathon Memory

One place that knows every project sent to a Hedera hackathon: what it claimed, what really happened, and whether it is still alive.

> **State on 11 October 2026:** Phase A is done. The four proofs of Gate A passed on the real services. The last one, the lists proof, passed on 11 October 2026 for every project that ETHGlobal's showcase ties to Hedera: 658 projects. See "What works today" below. Everything on this page apart from that is the plan.
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
4. **Check.** The Hedera mirror node says what each ID really is and when it was active. GitHub says when the code was written. No AI.
5. **Link and search.** The tool finds the past projects closest to an idea and shows the facts side by side.

## Where Hedera is used

- **Reading.** The public ledger is the ground truth for every claim a project makes about Hedera.
- **Writing.** A public register on a Hedera topic. A team registers a fingerprint of its submission and gets a timestamp that nobody can change. If the same fingerprint appears again at another event, the tool says "seen before".

## What the AI may and may not do

It may read pages, give them structure and find similar ideas. It may not give a score, pick a winner, say that a project is a copy, or state a fact. Facts come from the parser, the code host and the ledger.

## What already exists

Solana's hackathon organiser built this idea for Solana: [Colosseum Copilot](https://github.com/colosseumorg/colosseum-copilot). Its own page says its records show "what teams submitted, not what they run today". We found nothing like it for Hedera, and the check on the ledger is what we add.

Many tools score hackathon submissions with AI. This tool does not score.

## What works today

There is no website yet and no search. What exists is the ground that they will stand on, and four small proofs that it holds.

| Proof of Gate A | State on 11 October 2026 |
|---|---|
| Database: PostgreSQL with pgvector answers a vector query | **Passed.** 3,000 vectors of 3,072 numbers, the right neighbours first, an exact search in 27 ms. The result file is in `proofs/results/`. |
| Hedera write: a topic with no admin key, a message, read back from the ledger | **Passed** on the real test network. The topic has no admin key and one submit key, a 102-byte record was read back from the mirror node, and a topic with a stranger's submit key refused our message. The result file is in `proofs/results/`. |
| Google models: the two Gemini layers (Gemini 3.1 Pro reads the pages, Gemini 3.8 Flash does the search) and one embedding call | **Passed** on the real service. Both models returned a valid form for one real text, and the embeddings have the right size. The result file is in `proofs/results/`. |
| Lists: the ETHGlobal collector | **Passed** on 11 October 2026. A walk read the 21 pages of the showcase list with the filter "partner: Hedera": 658 projects in 14 events. A run read the page of every one of them and kept all 658, each without its team part: 92 with a Hedera prize, 81 with a prize of another sponsor only, and 485 with no prize. On every page the block "Winner of" agrees with the list. 732 requests were sent to the site in all, out of the 800 that the tool allows itself for it. The result file is in `proofs/results/`. The pages are not in this repository. |

Two more things work, and both were run on the real services:

- **The cost of the models is counted.** Every call to a model leaves one line in a ledger: the model, the tokens, the time, the cost. A budget stops a call before it is made when it could go over the cap. `python -m hackathon_memory.finops report` shows where the money went. The ledger holds numbers only, never the text of a call.
- **The history is searched for secrets.** `python -m hackathon_memory.secret_scan` looks for each secret of `.env` in every commit.

The tests (1,200 of them on 12 October 2026) run on every push, and pass on a clean Linux machine. They do not prove that the services answer as the code expects. That is what the live runs of the proofs are for.

Phase B, the first full path, is being built. What runs on the real data today:

- **The parser.** It reads every saved project page into its facts: the name, the short line, the event, the prizes, the links, the two texts word for word, and the Hedera IDs with their network and kind. It refuses a page whose visible part and data disagree. Words about people that a team wrote into its texts are hidden first (design 5.4).
- **The check on the ledger.** Every Hedera ID is asked of the public mirror node, and the proof rule of design 7.2 says whether the dates fit the event.
- **The README of the code.** The README of each project's repository is read once through GitHub's API, cleaned of the part about the team, and searched for Hedera IDs, which are then checked like the IDs of a page (design 7.3).
- **The facts of the code and the life rule.** The dates of each repository (made, last push) are read once through GitHub's API, without anything about the account that owns it. With the activity of the project's own IDs on the ledger, they say whether a project is active, quiet, stopped or too early to tell. Only a change later than 30 days after the event counts as a sign of life (design 7.4).
- **The search, as a plain listing.** Each project is embedded with Google's embedding model. An idea is searched by meaning and by words, and the two lists are merged. Each result shows its facts and what the mirror node said about its IDs (design 8.2).
- **One command for the whole path**, and the proof of Gate B that runs it from an empty database, searches three ideas written blind, and leaves the results for a person to mark.

What does not exist yet: the cards, the other facts of the code (the number of changes, the contributors, a Hedera library in the package files), the website, the register, and the tests that measure the quality of the AI fields and of the search.

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
| `python -m hackathon_memory.pipeline check` | Asks the Hedera mirror node about every ID and applies the proof rule. An answer is used again for seven days. |
| `python -m hackathon_memory.pipeline embed` | Makes the embedding of every project whose text changed. It costs money, through the meter and its budget. |
| `python -m hackathon_memory.pipeline all` | The five steps above, in order. |
| `python -m hackathon_memory.search "an idea"` | The closest projects to an idea, as a plain listing with the facts of each one. `--numbers-only` shows no name or link. |
| `python -m proofs.gate_b` | Gate B, part 1: a new empty database, the whole path with one command, and the first 10 results of each idea of `data/by-hand/gate-b-questions.txt`, written to `data/by-hand/gate-b-results.txt` to be marked. |
| `python -m proofs.gate_b --marks` | Gate B, part 2: reads the marks. Each idea needs at least one result marked "yes". |
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

## Licence

Copyright 2026 Mohamed Yaakoubi.

The code and the documents of this repository are under the Apache License, Version 2.0. The full text is in [`LICENSE`](LICENSE).

The licence does not cover the pages of other people's projects that the tool reads. Those belong to their authors, and they are not stored in this repository.
