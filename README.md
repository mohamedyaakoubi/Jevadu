# Hackathon Memory

One place that knows every project sent to a Hedera hackathon: what it claimed, what really happened, and whether it is still alive.

> **State on 9 October 2026:** Phase A is built and tested. Three of the four proofs of Gate A have passed on the real services. The fourth, the first run of the collector on ETHGlobal, waits for the maintainer's inputs. So Gate A is not passed yet. See "What works today" below. Everything on this page apart from that is the plan.
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

1. **Collect.** A program reads the public project pages of past hackathons and saves them unchanged. It does this only where the site's terms allow it or the site said yes in writing.
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

| Proof of Gate A | State on 9 October 2026 |
|---|---|
| Database: PostgreSQL with pgvector answers a vector query | **Passed.** 3,000 vectors of 3,072 numbers, the right neighbours first, an exact search in 27 ms. The result file is in `proofs/results/`. |
| Hedera write: a topic with no admin key, a message, read back from the ledger | **Passed** on the real test network. The topic has no admin key and one submit key, a 102-byte record was read back from the mirror node, and a topic with a stranger's submit key refused our message. The result file is in `proofs/results/`. |
| Google models: the two Gemini layers (Gemini 3.1 Pro reads the pages, Gemini 3.8 Flash does the search) and one embedding call | **Passed** on the real service. Both models returned a valid form for one real text, and the embeddings have the right size. The result file is in `proofs/results/`. |
| Lists: the ETHGlobal collector | The collector is written and tested on invented pages. **Never run on a live site.** It refuses a live run until the maintainer has given the list of prize pages, the contact address, and two real pages saved by hand to check its page shape. |

The tests (259 of them on 9 October 2026) run on every push, and pass on a clean Linux machine. They do not prove that the services answer as the code expects. That is what the live runs of the proofs are for.

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

`setup_check` says which of your setup steps are done and what blocks each proof. It prints no value. The proofs run with `python -m proofs.database`, `python -m proofs.hedera_write` and `python -m proofs.google_models`. Each one writes a dated result file to `proofs/results/`. `python -m hackathon_memory.collect ethglobal --plan` shows what the collector would read, without sending a request.

## The event

This is an entry for the FSS Campus Edition of the Hedera Cross Campus Challenge 2026. It is built by one person, Mohamed Yaakoubi.

## Licence

Copyright 2026 Mohamed Yaakoubi.

The code and the documents of this repository are under the Apache License, Version 2.0. The full text is in [`LICENSE`](LICENSE).

The licence does not cover the pages of other people's projects that the tool reads. Those belong to their authors, and they are not stored in this repository.
