# 09. Analytics for all users: research and proposal

- **Date:** 10 October 2026
- **Who:** the owner (Mohamed Yaakoubi), with Claude Code
- **Status:** research done, proposal written. Nothing is built. The owner decides the scope (open question Q23).

This file stays on the laptop (`CLAUDE.md`, hard constraint 20). It is never committed.

## Goal

The owner: "An aspect that I forgot to ask for in the beginning, it's a feature not aspect, which is we let all users benefit from the data analytically if possible. (Make the needed researches)".

Until now the tool answers one question at a time: "what is close to my idea?". Analytics answer questions about the whole collection: how many, which kind, how long they lived.

## What the research found

All of this was read on 10 October 2026. Where a summary tool read the page, the line says so.

| Question | Finding | Source |
|---|---|---|
| Does a registry or a dashboard of Hedera hackathon projects exist? | None was found. The winners of each event are in separate blog posts. Nothing follows the projects after the event. | One web search. It supports the README line "we found nothing like it for Hedera". One search is not a proof. |
| Do organisers care whether a project continues? | Yes. Hello Future Origins and Apex let teams continue projects from earlier Hedera hackathons. ETHOnline 2026 has a Hedera prize of 1,000 dollars for "teams bringing back a project you have already built on Hedera". | Hedera's winner posts; the Hedera prize page of ETHOnline 2026 and a news article, both through a search summary |
| What does research say about hackathon projects after the event? | A large study found that short-term and long-term continuation are different things. Winning and preparation go with short-term continuation. Skill diversity and the will to expand go with long-term continuation. | Nolte, Chounta, Herbsleb, "What Happens to All These Hackathon Projects?", CSCW 2020, through a search summary. No exact rate was read. |
| How much hackathon code lives on? | In 22,183 Devpost projects, about 9% of the code was created during the event, and about a third of that code was reused in other projects. | Imam, Dey, Nolte, Mockus, Herbsleb, "The Secret Life of Hackathon Code", MSR 2021 (arXiv 2103.01145), through a search summary |

So the question "what happened to the projects" is one that organisers already pay for, that researchers measure, and that nobody answers for Hedera.

## What can be counted, and from where

The rule stays: a fact never comes from the LLM (hard constraint 2). Analytics are counts of facts.

| Fact | Where it comes from | Needs |
|---|---|---|
| The event, the prize, the sponsor of a project | The parser, from the saved page | A source that allows collection |
| What each Hedera ID really is (account, token, topic, contract), when it was created, when it was last used | The Hedera mirror node | Nothing. It is public and free |
| First and last change of the code, number of changes, languages, whether a Hedera library is named | GitHub's API | The owner's yes (Q17) |
| The same repository or the same Hedera ID at two events | Our own comparison | Two events in the data |
| The category of a project (16 categories) | The LLM, with a label and quotes | It is an opinion with evidence, not a fact. It must be shown as such |

## Proposal: one screen and one export

The build order already has an "overview" screen in Phase G. The proposal is to make that screen the analytics, and to add an export.

**For a builder**

1. Around my idea: of the closest projects, how many are active, quiet or stopped, and how long the code lived after the event.
2. Which Hedera services are used: counts by the kind of the IDs that the ledger confirms. This is a fact from the ledger, not a reading of the text.

**For a judge**

3. For one event: how many submissions give a Hedera ID at all, and how many of those IDs are of the right kind and from the right dates.
4. How many submissions were seen before (the same repository or the same Hedera ID).

**For an organiser**

5. A survival curve for each event: the share of projects whose code was still changed N months after the event.
6. Continuity: how many projects came back at a later event.

**For everybody**

7. An export of the facts as a file (CSV): one line for each project, with its event, its links, its ledger facts, its code facts and its status. No page text and no text written by the LLM.

## Rules that the analytics must keep

| Rule | What it means here |
|---|---|
| The AI never ranks and never scores (hard constraint 1) | No list of "best" projects, no score of a team. Counts and shares only |
| No number without a dated result file (hard constraint 6) | Each number on the screen comes from a job that writes a dated file in `evals/`. The screen shows the date |
| No personal data (hard constraint 11) | Nothing by person. A repository owner's name is only part of a link |
| Small numbers | Every share is shown with the count behind it and with a range. A curve for 8 projects is not shown as a curve |
| Projects that are still young | A project whose last change is recent has not "stopped". The survival method that handles this is called Kaplan-Meier: it counts a young project only for the time we have seen |
| The promise to ETHGlobal | A demo and a video for the jury are allowed. Anything online needs a new request first, and so does the export if it holds their projects |

## What it costs

- **Money:** almost nothing. The counts are database queries. The categories come from the rewrite that is paid for anyway.
- **Work:** the queries and one screen. The survival curve is the only part that needs care.
- **Data:** this is the real limit. With ETHGlobal alone there will be about 40 to 70 projects, and they are all winners. A curve of winners says nothing about the others. The one large set is the Hedera Africa Hackathon 2025, with more than 1,300 submissions, which Dar Blockchain led. If Dar Blockchain can give an export of the public fields, the analytics become worth showing.

## Recommendation

1. Build views 2, 3 and 4 first. They need only the ledger and the pages, and they are what no other tool has.
2. Build views 1, 5 and 6 when GitHub is allowed (Q17) and there are at least two events with all their projects.
3. Build the export last, and only with the facts that no site owns.
4. Ask Dar Blockchain for an export of the Africa 2025 submissions. It would do more for this feature than any code.

## What this does not prove

- That users want these views. Nobody was asked.
- The two studies were read through a search summary, not in full. Their numbers must be read in the papers before they are used in a pitch.
- That the mirror node gives the "last used" date cheaply for every kind of ID. The client of entry 05 reads accounts and topics. Tokens and contracts were not tried.

## Next

The owner answers Q23: which of the seven views do they want for the hackathon, and does they ask Dar Blockchain for an export.

## Later on 10 October 2026: the owner left the choice to the assistant

The owner: "Q23: I dont know you tell me, how'd people benefit analytically from all historical projects, like what project themes mostly win and what ismostly done etc."

The same evening the first real data came in (entry 10). So the choice is made on what exists, not on a hope.

**What the data is.** 92 projects that took a Hedera prize at 14 ETHGlobal events, from 2024 to 2026, each with its page. For each of these events also two numbers: how many projects were tied to Hedera (658 in all) and how many took a prize of some sponsor (173). And the winner entries of Hedera's own events.

**What people get from it, and what is built for the hackathon.** One screen, the event overview (S5 of blueprint §12.1), with these six blocks:

| # | Block | The question it answers | Where the numbers come from |
|---|---|---|---|
| A | What took a Hedera prize | Which themes win? For each event and year: the categories of the winners, and the names of the Hedera prize tracks. | The category is the LLM's reading, with its label. The prize track is copied by the parser. |
| B | What it was built with | Which Hedera services do winners really use, and how did that move over the years? | The kinds of the IDs on the ledger, and the Hedera libraries named in the code. What the page only says is shown apart. |
| C | What happened after | Are the winners still alive? Active, quiet or stopped, for each event. | The life rule (blueprint §7.4), from GitHub and the ledger. |
| D | How much proof | How many winners give a Hedera ID that checks out? | The proof rule (blueprint §7.2). |
| E | How many, and how many won | For each event: projects tied to Hedera, and winners of a Hedera prize. For example 10 of 271 at ETHOnline 2026. | The walk of entry 10. With one warning on the screen: for the older events the list holds almost only winners. |
| F | Came back | Which projects stand in more than one event? | The same repository or the same Hedera ID (blueprint §8.4). |

**Who gets what.**

- A builder sees which themes are crowded among the winners, which prize tracks come back every time, what the winners built with, and whether projects like theirs are still alive.
- A judge gets a baseline: how many winners gave proof that can be checked.
- An organiser sees what the prizes produced and what is left of it.

**What is not built, and why.**

- **"What is mostly done"**, the themes of all projects and not only of the winners. The data is not there: ETHGlobal's yes covers the winners. It needs the second part of the email in entry 10, or the answer of DoraHacks.
- **Anything that predicts,** such as "what will win" or a rate of success for a theme. An event has 3 to 11 winners. A share of so few is noise, and a rate of success is a ranking of quality through the back door (hard constraint 1). The screen shows counts. It shows a share only when at least 20 projects stand behind it.
- **The export.** It would hold ETHGlobal's projects, so it needs a new request first (blueprint §5.7).

**The rules stay as written above:** every number from a job that leaves a dated result file, the date on the screen, nothing by person, and a category shown as what it is: a reading with evidence, not a fact.

This is a decision by the assistant that the owner can change. It replaces the recommendation above: views 2, 3 and 4 are now blocks B, D and F, and the two new blocks A and E answer their own question about themes.

## 10 October 2026, late: all projects, not only winners

The owner: "your analytics are good and thats why I need all projects and not just winners." They decided the same evening that every project of ETHGlobal's Hedera list is collected (entry 11): 658 projects, of which 92 took a Hedera prize, 81 a prize of another sponsor only, and 485 none.

What this changes in the six blocks:

- **Block A becomes two columns:** what was built, and what took a Hedera prize, for each theme. This is their question "what project themes mostly win and what is mostly done". The line "not built: what is mostly done" of the decision above no longer holds for ETHGlobal.
- **Blocks B, C and D** get the same split: winners next to the other submissions. For example: do winners name a Hedera ID more often, and are they more often still alive?
- **One limit stays, and the screen must say it.** For the older events the Hedera list holds almost only projects with a prize (for example 6 of 6 at one event), and for the newer ones it holds every project (271 at ETHOnline 2026). So "built against won" is shown only for the events where the list holds the others too. The rule of 20 projects for a share stays.
- **Nothing that predicts.** With all projects it is tempting to show "the chance to win with this theme". That is still a ranking through the back door (hard constraint 1), and a theme with 3 winners out of 40 says little.
- **The cost.** The category of a project comes from the first model layer. 658 pages cost about seven times more than 92 (Q29).

A card says which of the three a project is: took a Hedera prize, took a prize of another sponsor, or took no prize. The parser reads that from the block "Winner of" of the page itself.

