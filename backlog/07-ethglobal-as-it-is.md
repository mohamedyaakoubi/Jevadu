# 07. ETHGlobal as it really is, and the collector that follows from it

- **Date:** 10 October 2026
- **Who:** the owner (Mohamed Yaakoubi), with Claude Code
- **Branch:** `phase-a-proofs`
- **Status:** the collector is rebuilt and tested, and a look passed on a real page. The first run that saves pages waits for the owner's list and their yes.

This file stays on the laptop (`CLAUDE.md`, hard constraint 20). It is never committed.

## Goal

The owner looked at ETHGlobal in their browser and wrote: "it doesn't list the winners or submissions, it only shows prizes and themes for each sponsor". The collector of entry 05 was built on the opposite guess: that the Hedera prize page of an event links to the winning projects. They also asked whether the video of the closing ceremony could be given to Gemini. And they allowed an investigation: "You can run signatured requests to ETH if you want to investigate further." They confirmed that the email to ETHGlobal was sent unchanged (Q19).

## What was read, and how

Every request went through the project's own `PoliteClient`: the tool's name and the owner's address in each one, two seconds apart, one at a time, no cookie, no sign-in, a stop at the first refusal. Nothing was saved to disk. The scripts printed the shape of the pages and public facts (event names, sponsor names, link shapes), never the value of a key that could hold a person. No request was refused.

| # | Address | Why |
|---|---|---|
| 1 | `/robots.txt` | The rules of the site |
| 2, 5, 10 | `/showcase` (three times) | The list of all projects: first for its links, then for its HTML, then to pick the first project |
| 3, 4 | `/events` (twice) | The list of events: first for its data blocks, then for its HTML |
| 6, 9 | `/events/cannes2026` (twice) | The owner's example. The second time for the schedule |
| 7, 8 | `/events/cannes2026/prizes/hedera` (twice) | A Hedera prize page. The first answer was lost when the script crashed on an emoji |
| 11 | `/showcase/<the first project of the list>` | A project page with no prize |
| 12 | `/events/cannes/prizes` | All the prizes of a past event (Cannes 2025) |
| 13 | `/events/cannes/prizes/hedera` | The Hedera prize page of a past event |
| 14, 16, 17, 19 | `/showcase/contragent-8x0c9` (four times) | A known winner: its prize block, its content, its page data, and the look with the real code |
| 15 | `/showcase/hedera-agent-trust-mur21` | A second known winner |
| 18 | `/robots.txt` | The look reads it first |

**19 requests in all.** Pages were read more than once because nothing was saved, so each new question needed the page again. That is the price of keeping the promise "no team member data saved" before the team cut was proven on a real page. The email promised "a few hundred pages at most, one time", and named the showcase pages of the winners. The events list, one event page and three prize pages are next to that promise, not inside it. They must be named in the next email to ETHGlobal.

## What the pages show

| Question | Answer | How it was measured |
|---|---|---|
| Does robots.txt forbid anything? | There is none: the address answers 404. | Request 1 |
| Does the events list say which events had Hedera as a partner? | No. The page holds 87 event addresses in 1.85 MB, and the word "hedera" does not occur once, also not in its scripts. | Requests 3 and 4 |
| Does an event page say it? | Yes. `/events/cannes2026` links to 12 sponsor prize pages, one of them `/prizes/hedera`, with the Hedera logo. | Request 6 |
| Does a Hedera prize page list the winners? | **No.** It lists the prizes and the bounties (15,000 dollars in tracks), with links to Hedera's documentation and to GitHub. It has no link to a project. The same for a past event. | Requests 8 and 13 |
| Does the page with all the prizes of an event list winners? | **No.** 1.4 MB, 27 sponsor links, no link to a project. | Request 12 |
| Does the showcase list show prizes? | No. 33 project cards for each page (`?page=2` gives the next), each with a name, a short line and the event. No prize, no sponsor, no filter in the HTML, only a search box. | Requests 2 and 5 |
| Does a project page show its prizes? | **Yes.** A box holds the block "Winner of", with one line for each prize: "Hedera - AI, Agents & Hedera Services 1st place". The page data holds the same under `prizes`, `prize`, `sponsor`. | Requests 14, 15, 16 |
| Does a project page show its team? | **No.** No profile link, no avatar, no class or id that names a person. The page data has 96 key names and none holds a person. The tags `author` (9 characters) and `twitter:creator` (10 characters) hold the name of the site, not a person. | Requests 14 to 17 |
| Does the schedule give the video of the ceremony? | Not in the visible page. The page data of the event holds 15 YouTube addresses, and they were not matched to schedule entries. | Requests 6 and 9 |

So the owner was right, and the first design was wrong. A winner is known only from its own project page. There is no public page that lists the winners of one sponsor.

## What follows for the collector

1. **The list is a list of project pages**, made by hand or sent by ETHGlobal: `data/by-hand/ethglobal.com/project-pages.txt`. The old `prize-pages.txt` is no longer read.
2. **The page itself must show a Hedera prize**, or it is read but not kept. The check reads the block "Winner of", not the text of the page, so a project that only talks about Hedera is not kept.
3. **The team cut has tripwires.** A real page shows no team, so there is nothing to cut. If a page ever shows a profile link, an avatar, or a data key that holds people, the run stops. The names of the site in the author tags are not taken for a person. Without that last rule the self-check would have refused every real page: the handle of the site also stands in the page data.
4. **The shape is checked.** `ETHGLOBAL_SHAPE.verified_on` is `2026-10-10`, from 3 project pages (2 winners). A live run is no longer refused for the shape. It still needs the switch, the address, the list and the owner's yes.
5. **The look** reads robots.txt and the first page of the list (2 requests), prints the shape, and says whether the cut passes and whether the page shows a Hedera prize. It ran once on a real page (requests 18 and 19): the cut passed with 2 elements removed and no string guarded, the prize was found, nothing was saved.

Commits: `bcb3517` the team cut (tripwires, script keys, site names), `402f502` the collector on a list of project pages. 359 tests pass. These numbers change when the history is rewritten (entry 08).

## How to get the list of winners

| Way | What it gives | Judgement |
|---|---|---|
| **A. The owner makes the list in their browser.** If the showcase has a filter by sponsor or by prize, they uses it and copies the addresses. If it has none, they searches "Hedera" and opens each result. | The exact winners, with no request by a program before the run | **Recommended**, with B at the same time |
| **B. Ask ETHGlobal for the list.** The email already said: "If you already have a list of the projects with a Hedera prize, or an API, I will gladly use that instead." | The official list | **Recommended.** One short email. The same email names the pages that the investigation read |
| C. The video of the closing ceremony, read by Gemini | The finalists, which is a small part of the winners of all sponsors, and not the same as the winners of the Hedera prizes | Not as a source. Only as a cross-check, after a test with known answers |
| D. A search engine | A few indexed winner pages. It found Contragent, Hedera Agent Trust, Reputify and Dead Men Tell Tales, and eight more names without a clear prize | A seed, not a list |
| E. GitHub search for "ETHGlobal" and "Hedera" | Candidates, and the code facts | Useful later. It needs the owner's yes (Q17) |

A draft of the list is in `data/by-hand/ethglobal.com/project-pages.txt`: two pages that were seen, two that a search says are winners (to check), and eight to look at.

## The video and Gemini

From Google's page "Video understanding" (read on 10 October 2026 through a summary tool):

- A YouTube address can be given to the model. The video must be public, one address for each request, and the feature is marked Preview.
- For Gemini 3.1 Pro and Gemini 3.8 Flash: about 45 minutes with sound for each request, about 1 hour without sound.
- The model samples one frame each second. A frame costs 70 tokens at the default setting (280 at HIGH).
- Fast scenes lose detail at one frame each second.

The ceremony lasts 2 hours, so it needs three requests. The cost is small: at about 100 tokens each second (70 for the frame, and about 30 for the sound, which Google's page does not state), 2 hours are about 720,000 tokens, so about 0.5 dollars with Flash and about 3 dollars with Pro. These are estimates, not measurements. The problem is not the price. The ceremony shows the finalists of the whole event, and a winner of a Hedera prize is often not a finalist. Names of projects are said aloud and shown on slides, and both are easy to read wrong.

## What went wrong

1. **The first collector was built on a guess about the site.** The rule "send one real request and look at the answer before you write a collector" could not be followed while no request was allowed, and the guess was not marked as the main risk of the plan. The owner found the truth in five minutes with their browser. A design that depends on the shape of a site must say so in its first line, and the first allowed request must test it.
2. **A script crashed while printing, after the page had arrived.** The page was lost, and it was requested again. A script that reads a site must set its output to UTF-8 before the first request.
3. **Pages were requested up to four times.** Each new question needed the page again, because nothing was saved. One careful script that answers many questions would have used fewer requests.
4. **A shell command lost its backslashes again**, the third time. Scripts with backslashes are written with the file tool, never inside a shell command.

## What this does not prove

- Three project pages were read. Older events may have another shape. The tripwires stop a run if they do.
- Nobody checked whether the showcase has a filter by sponsor for a visitor. The HTML of the list has none. The owner can see it in their browser.
- That the search engine's list is right. Only two of its pages were opened.
- The numbers about the video are estimates from Google's page. No video was given to a model.

## Next

1. The owner checks the draft list in their browser, adds what they find, and says yes for the run. Or they writes to ETHGlobal for the list.
2. The run on the list, then the first saved pages are read for anything unexpected.
3. Then Gate A is complete, and the owner decides on the merge and the tag.

## Later on 10 October 2026: the showcase has a filter after all

Two lines of this entry were overtaken the same day. The story is in [entry 10](10-ethglobal-walk-and-first-run.md).

- "Does the showcase list show prizes? No [...] no filter in the HTML". The plain list has none. But the owner found a filter in their browser, `/showcase?partners=hedera`, and the data of that list says which sponsors gave each project a prize. So the list of winners did not have to be made by hand.
- The way A of the table above ("the owner makes the list in their browser") became: the owner's two pages only tell the tool which sponsor id is Hedera, and a walk finds the 92 winners.
- The count of requests of this entry is 19. The whole day came to 140, of the 300 that are the limit.
