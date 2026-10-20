# 01 · Research: from the idea to the tech stack

- **Dates:** 7 and 9 October 2026
- **Status:** done
- **Result:** `docs/blueprint.md` version 0.1

## Goal

Find out whether a memory of all Hedera hackathon projects can be built in the time left, what it needs, and how its claims can be measured.

## Approach

Nothing was taken from memory. Each question was answered by a real request, by reading the primary source, or by measuring real project pages.

## Method

All requests were single, read-only requests to public pages.

| Question | How it was answered |
|---|---|
| How many hackathons did Hedera run? | Hedera's own blog posts, AngelHack's report, the Africa hackathon announcement |
| Does this tool exist already? | Web searches, then the tool's own README |
| Can the project pages be read? | One simple request from the owner's laptop to a list page and to project pages |
| How are project pages organised? | A script read 31 pages and counted titles and section lengths. It printed counts only. |
| Does the ledger check work? | One request to the mirror node for a public topic and a public contract |
| What does the laptop have? | The install folders on disk |
| Which models and libraries fit? | Official pages of Google, Hedera, GitHub and PyPI |

## Results

**Hedera's hackathons.** At least 12 big ones since 2018. The seven that publish a number add up to more than 2,100 projects, on at least five websites. The table is in blueprint §1.2.

**What exists.** Solana's organiser built the same idea for Solana (Colosseum Copilot, 8,286 submissions). Many tools score submissions with AI. Nothing like a memory of projects was found for Hedera.

**Reading DoraHacks,** from the owner's laptop:

| Request | Answer |
|---|---|
| A project page, simple request | Works. One page held the title, the short line, 2 GitHub links, 4 video links, 2 Hedera IDs. |
| The list of an event, simple request | Only the first 19 projects. Asking for page 2 returns the same 19. |
| robots.txt | Does not exist. The terms of use were not read. They were read later the same day, and they forbid these scripted requests: see [entry 03](03-answers-and-terms.md). |

Other sites (ETHGlobal, Devpost, Hedera's blog) refuse simple requests from a script.

**How 31 real pages are organised** (19 from the first page of the Africa 2025 list, 12 winners of Hello Future Origins):

| Section title | Pages | Usual length |
|---|---|---|
| Problem | 16 (51%) | 73 words |
| Solution | 13 (41%) | 71 words |
| Overview or description | 12 (38%) | 84 words |
| How it works or architecture | 10 (32%) | 45 words |
| Tech stack | 11 (35%) | 48 words |
| Something about Hedera | 20 (64%) | 45 words |

- Both a Problem and a Solution title: 13 pages. Only one: 3. Neither: 15.
- All 31 pages use real headings, not bold lines.
- Of the first 10 pages, 5 short lines were slogans and 4 pages showed Hedera IDs.

**The ledger check.** For one public campus project, the mirror node returned: a contract created on 27 September 2026, and a topic with 31 messages from 27 to 29 September, all from one account. GitHub returned: 62 changes from 26 to 29 September, one author. The check works with plain requests.

**The laptop.**

| Thing | State |
|---|---|
| Python | 3.11.9, with requests, BeautifulSoup, lxml and Selenium. The database inside Python supports text search. |
| Docker Desktop | Installed, version 29.2.1. It was not running at the time. |
| Node | Version 23.7.0 |
| Chrome | Installed |
| Playwright | Browsers are on disk. The Python package is not installed. |
| Memory, disk, graphics card | 15.7 GB, about 37 GB free, 4 GB |

The tool shells do not see the owner's programs. Python 3.11 is at `C:\Users\MSI\AppData\Local\Programs\Python\Python311\python.exe`, Docker at `C:\Program Files\Docker\Docker\resources\bin\docker.exe`, Node at `C:\Program Files\nodejs\node.exe`. On this laptop, `curl` fails on several sites that a browser can read.

**Models and libraries.** The facts and their sources are in blueprint §18.2.

## What went wrong

Six mistakes by the assistant, all corrected by the owner. Each one is in [`lessons.md`](lessons.md).

1. It said Docker was missing. The shell it asked could not see any program.
2. It chose the first tech stack by what was installed and easy.
3. It removed the LLM from the plan to avoid a bill.
4. It said the rewrite was needed before it had looked at a single real page.
5. It allowed only "stated" or "empty" fields.
6. It proposed to "check about 30 rewrites" with no method behind it.

## What this does not prove

- The 31 pages are first-page projects and winners. The average page is probably less organised.
- One page was tested for a simple request. Hundreds of requests in a row may be answered differently.
- No list was collected with a browser yet. That is Gate A.
- No code was written. Every cost is an estimate.
- "Nothing like it exists for Hedera" rests on a few searches.

## Next

The owner's setup steps (blueprint §15), then Phase A (blueprint §14.2).
