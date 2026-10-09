# Hackathon Memory

One place that knows every project sent to a Hedera hackathon: what it claimed, what really happened, and whether it is still alive.

> **State on 9 October 2026:** design and documents only. No code yet. Everything below is the plan. This page will say plainly what works as soon as something does.
>
> The terms of DoraHacks ask for written permission before its pages are collected. I asked for it. Until the answer comes, no program reads DoraHacks.

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

## The event

This is an entry for the FSS Campus Edition of the Hedera Cross Campus Challenge 2026. It is built by one person, Mohamed Yaakoubi.

## Licence

Copyright 2026 Mohamed Yaakoubi.

The code and the documents of this repository are under the Apache License, Version 2.0. The full text is in [`LICENSE`](LICENSE).

The licence does not cover the pages of other people's projects that the tool reads. Those belong to their authors, and they are not stored in this repository.
