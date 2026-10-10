# Hackathon Memory

One place that knows every project sent to a Hedera hackathon: what it claimed, what really happened, and whether it is still alive.

> **State on 10 October 2026:** Phase A is built and tested. Three of the four proofs of Gate A have passed on the real services. The fourth, the first run of the collector on ETHGlobal, waits for a hand-made list of project pages. So Gate A is not passed yet. See "What works today" below. Everything on this page apart from that is the plan.
>
> **Where the data comes from.** Every site was asked before any program reads it. ETHGlobal allowed its showcase in writing, for the projects with a Hedera prize. Devpost said no, so no program reads Devpost. DoraHacks and AngelHack have not answered yet, so no program reads them.

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

| Proof of Gate A | State on 10 October 2026 |
|---|---|
| Database: PostgreSQL with pgvector answers a vector query | **Passed.** 3,000 vectors of 3,072 numbers, the right neighbours first, an exact search in 27 ms. The result file is in `proofs/results/`. |
| Hedera write: a topic with no admin key, a message, read back from the ledger | **Passed** on the real test network. The topic has no admin key and one submit key, a 102-byte record was read back from the mirror node, and a topic with a stranger's submit key refused our message. The result file is in `proofs/results/`. |
| Google models: the two Gemini layers (Gemini 3.1 Pro reads the pages, Gemini 3.8 Flash does the search) and one embedding call | **Passed** on the real service. Both models returned a valid form for one real text, and the embeddings have the right size. The result file is in `proofs/results/`. |
| Lists: the ETHGlobal collector | **Not run yet.** The collector reads a hand-made list of project pages and keeps only the pages that show a Hedera prize. It is tested on invented pages. A look at one real page passed on 10 October 2026 (two requests, nothing saved): the team cut passed and the prize was found. The first run that saves pages needs the list and a yes for the pages on it. |

Two more things work, and both were run on the real services:

- **The cost of the models is counted.** Every call to a model leaves one line in a ledger: the model, the tokens, the time, the cost. A budget stops a call before it is made when it could go over the cap. `python -m hackathon_memory.finops report` shows where the money went. The ledger holds numbers only, never the text of a call.
- **The history is searched for secrets.** `python -m hackathon_memory.secret_scan` looks for each secret of `.env` in every commit.

The tests (450 of them on 10 October 2026) run on every push, and pass on a clean Linux machine. They do not prove that the services answer as the code expects. That is what the live runs of the proofs are for.

What does not exist yet: the parser, the cards, the checks of the ledger and of the code, the search, the website, the register, and the tests that measure the quality of the AI fields.

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
| 2 | `GITHUB_TOKEN` | GitHub, Settings, Developer settings, Personal access tokens, Fine-grained tokens. Choose "Public repositories (read-only)" and add no permission. It is used to read facts about public repositories. |
| 3 | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS` | A Google Cloud project with the Vertex AI API turned on. The location is `global`. Sign in with `gcloud auth application-default login`. If you name a sign-in file, keep it outside the project folder. |
| 4 | `POSTGRES_PASSWORD` | Any password you choose. Then `docker compose up -d --wait db`. |
| 8 | `COLLECTOR_NAME`, `COLLECTOR_CONTACT_EMAIL` | A name for the tool and your own address. Both are sent in every request to a site, so that the site can see who reads it. Only needed to run a collector. |
| 9 | The list of project pages | `data/by-hand/ethglobal.com/project-pages.txt`, one showcase address per line. Only needed to run the ETHGlobal collector, and only with a written yes from the site. |

### The commands

| Command | What it does |
|---|---|
| `python -m proofs.database` | Proof 1, on the local database |
| `python -m proofs.hedera_write` | Proof 2, on the Hedera test network |
| `python -m proofs.google_models` | Proof 3, on Google's models (it costs a few cents) |
| `python -m hackathon_memory.collect ethglobal --plan` | Shows what the collector would read. It sends no request. |
| `python -m hackathon_memory.collect ethglobal --look` | Reads robots.txt and the first page of the list, and saves nothing |
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
| 5 | A saved page is never edited afterwards. Before it is saved, the part that shows team members is cut out, and the page is written again by the parser: the text, the links and the order of the tags stay the same. |
| 6 | No number is shown unless it comes from a test with a dated result file. A model never grades its own work. |
| 7 | All LLM calls use Gemini on Vertex AI: Gemini 3.1 Pro reads and rewrites the pages, Gemini 3.8 Flash does the search. Embeddings use Google's embedding model. |
| 8 | Only a fixed fingerprint record goes to the Hedera topic. No free text, no names, no secrets. A message on a topic can never be deleted. |
| 9 | Secrets live only in `.env`. They never appear in git, in a log, in the database or in a test file. |
| 10 | The terms of a site are read before the first request to it. Requests go one at a time, with a pause, with the name of the tool and a contact address. A block is never worked around, and the tool never signs in. |
| 11 | No personal data that the check does not need: no names, emails or photos of team members. |
| 17 | No collector runs against a live site before the maintainer has said yes for that site and for the pages that will be read. |
| 18 | A promise made to a site is a rule for the code, and each promise has a test. |

Comments in the code also name sections of the design notes, for example "design 5.7". The most cited one is below. A design document for readers will be added before the submission.

### The promises made to the sites (design 5.7)

A yes from a site holds only as long as these are kept. Each one is code, with a test.

| The promise | What the code does |
|---|---|
| Only the pages we named | The collector reads the pages on a hand-made list and robots.txt. It never walks through a whole site. A fixed limit stops it after 300 requests. |
| One time | A second run skips every page that is already saved. |
| One request at a time | One worker, a pause of two seconds, nothing in parallel. |
| Each request says who sends it | The name of the tool and a contact address are in every request. The collector refuses to start when one is empty. |
| No names, photos or profiles of team members | The team part is cut out before a page is saved. If a page shows a person where none is expected, the run stops. |
| It stops at once when asked | One switch for each site in `.env`, read again before every request. |
| The pages stay on one laptop | The data folder never enters git, and no text of a collected page is in a test file or a result file. |

## The event

This is an entry for the FSS Campus Edition of the Hedera Cross Campus Challenge 2026. It is built by one person, Mohamed Yaakoubi.

## Licence

Copyright 2026 Mohamed Yaakoubi.

The code and the documents of this repository are under the Apache License, Version 2.0. The full text is in [`LICENSE`](LICENSE).

The licence does not cover the pages of other people's projects that the tool reads. Those belong to their authors, and they are not stored in this repository.
