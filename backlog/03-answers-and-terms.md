# 03 · The owner's answers, and the terms of DoraHacks

- **Date:** 9 October 2026
- **Status:** the checks are done. The permission from DoraHacks is **waiting**: the owner sent the email on 9 October 2026, and no answer has come yet.
- **Result:** `docs/blueprint.md` version 0.2, a `LICENSE` file, and the email below

## Goal

The owner answered the nine open questions. For most of them the answer was "you decide, as long as it is justified". So each decision needed a checked reason. Question 8 asked for an email to DoraHacks, and that needed its terms of use to be read first.

## Approach

Each decision was checked against a primary source on the same day. Nothing was taken from memory.

## Method

| Question | How it was checked |
|---|---|
| What do the terms of DoraHacks say? | The page `dorahacks.io/legal/terms`. To repeat it, open the page in a normal browser. |
| Whom to write to? | The "Contact Us" part of the same terms |
| Is a start possible without DoraHacks? | GitHub's Acceptable Use Policies, then seven searches through GitHub's official search API (`api.github.com/search/repositories?q=...`) |
| Python or JavaScript? | Hedera's page that lists its libraries, the PyPI page of the Python library, Hedera's "create your first topic" tutorial |
| Which licence? | choosealicense.com (GitHub's guide), the licence of the libraries we use, the page of the FSS challenge |
| Which keys for the topic? | Hedera's "create a topic" page |
| Which events? | The winner posts of Hedera, the Apex tracks page, press pages for the dates |
| Which pass marks? | Our own range calculations, Anthropic's retrieval post, a public test of summaries by Vectara |

## Results

### The terms of DoraHacks

Last updated on 20 September 2026. The part named "Prohibited Activities" forbids, word for word:

| About | The words |
|---|---|
| Building a collection | "systematic retrieval of data or other content from the Website to create or compile, directly or indirectly, a collection, compilation, database or directory without written permission from Company" |
| Robots | "engaging in any automated use of the system, such as using any data mining, robots or similar data gathering and extraction tools" |
| Scripts | "except as may be the result of standard search engine or Internet browser usage, using or launching, developing or distributing any automated system, including, without limitation, any spider, robot (or "bot"), cheat utility, scraper or offline reader that accesses the Website, or using or launching any unauthorized script or other software" |
| Competing products | "using any information, tools, or content obtained from the Website or Company Services for any purpose that is directly or indirectly competitive with Company or that seeks to replicate, reverse engineer, or build a similar or competing product, service, or community" |

What a visitor may do with a team's content: "access, download, print and otherwise use your Contributions for their internal purposes and not for distribution, transfer, sale or commercial exploitation of any kind".

The teams keep the ownership of what they post. The contact address in the terms is `hi@dorahacks.com`.

**What this means.**

- Our plan needs the written permission of DoraHacks. This is true for a robot, and by the first line also for a collection built by hand.
- DoraHacks sells its own AI product to organisers. Its terms name "automated BUILD review, judging". So it may see our tool as close to its own. Our tool gives no score and no judgement, and the email says so.
- No program touches DoraHacks until a written yes arrives. This is now part of hard constraint 10.

### The email to DoraHacks

Status: **sent by the owner on 9 October 2026,** to `hi@dorahacks.com`. No answer yet. When the answer arrives, it is written here with its date.

The text below is the draft. The owner may have changed some words before sending.

```text
Subject: Permission request: reading public BUIDL pages of two Hedera hackathons for a student project

Hello DoraHacks team,

My name is Mohamed Yaakoubi. I am a computer science student at the Faculty of Sciences of Sfax, in Tunisia. I am taking part in the FSS Campus Edition of the Hedera Cross Campus Challenge 2026, which is organised by Dar Blockchain. The deadline is 20 October 2026.

Your Terms of Use say that systematic retrieval of content to build a collection needs written permission from you. I am writing to ask for that permission.

What I am building
A small research tool that lets a builder search past Hedera hackathon projects before starting a new one. For each project it shows the team's own description and what the public Hedera ledger shows for the Hedera IDs the team listed. It gives no scores and no rankings, and each project links back to its page on DoraHacks.

What I would like to collect
- Only the public BUIDL pages of two hackathons: the Hedera Africa Hackathon 2025 (dorahacks.io/hackathon/hederahackafrica) and Hello Future Origins 2025. About 1,500 pages, one time.
- From each page: the project name, the short description, the description text, the links to the code and the demo, the Hedera IDs, the track and the prize.
- Not collected: names, photos, profiles or contact details of team members, comments, and anything that needs an account.

How
- One request at a time, at least one second apart.
- Each request carries the name of my tool and my email address, so that you can identify it.
- I stop at once if you ask me to.

Use
The collected pages stay on my laptop. The jury sees the tool in a demo and in a short video. The tool is not online and not commercial. If the project continues after the event, I will ask you again before anything is published.

If you prefer another way, for example an export or an API for these two events, I will gladly use that instead. And if your answer is no, I will respect it.

To be open with you: on 9 October, before I had read your terms, I sent about 40 test requests to public pages with a script, to see whether the idea was possible. I stopped when I read them.

Because of the deadline, an answer in the next few days would help me a lot. Thank you for your time.

Mohamed Yaakoubi
Faculty of Sciences of Sfax, Tunisia
```

### A start that needs no permission

GitHub's policy says: "Scraping does not refer to the collection of information through our API." It also lets researchers use public, non-personal information when what they publish is open to read.

Seven searches of public repositories through the official API:

| Search | Repositories |
|---|---|
| The README contains "hedera africa hackathon" | 86 |
| The name or the description contains it | 23 |
| The README contains "hello future" and "hedera" | 180 |
| The README contains "hedera" and "hackathon", created from June to October 2025 | 311 |
| The topic is "hedera-africa-hackathon" | 0 |
| The topic is "hedera-hackathon" | 1 |
| The topic is "hedera" | 366 |

So a few hundred public repositories name a Hedera hackathon. That is enough to build and test every step. It is not "all projects". This is open question Q10.

### Python or JavaScript

| Fact | Source |
|---|---|
| Hedera has six official libraries: JavaScript, Java, Go, Swift, Rust and C++. Python is listed apart, as kept by the community. | Hedera's list of libraries |
| The Python library is version 0.2.10, from 30 July 2026, and is labelled "Pre-Alpha". Its licence is Apache 2.0. | PyPI |
| Hedera's "create your first topic" tutorial has examples in JavaScript, Java, Go and Python. The Python one uses `TopicCreateTransaction` and `TopicMessageSubmitTransaction` from this library. | The tutorial |
| Google's own library for Gemini exists for Python and for JavaScript, and both reach Vertex AI. | Google's library pages |

Decision: Python, with the Hedera write tested at Gate A. The reasoning is in blueprint §11.5.

### The licence

| Fact | Source |
|---|---|
| MIT: "A short and simple permissive license with conditions only requiring preservation of copyright and license notices." | choosealicense.com |
| Apache 2.0 gives the same rights and adds three things: an explicit right to use the patents of the contributors, a duty to say what you changed, and no right to use the project's name as a brand. | choosealicense.com |
| With no licence, "nobody else can copy, distribute, or modify your work without being at risk". | choosealicense.com |
| Hedera's Python library is under Apache 2.0, like the Hedera code we build on. | PyPI, Hedera's list of libraries |
| The FSS challenge asks for a "source-code repository". Its page does not say that it must be public, and it names no licence. | The FSS page on 4hacks |

Decision: Apache 2.0. The official text is in `LICENSE`, copied unchanged from apache.org. The repository stays private for now, so the licence starts to matter on the day the code is shared.

### The keys of the topic

Hedera's page says: "If no Admin Key is specified, the topic is immutable." And: "If no adminKey is specified, anyone can increase the topic's expirationTime with updateTopic, but they cannot use deleteTopic."

Decision: no admin key, and a submit key held by the tool's account. The reasoning is in blueprint §9.5.

One trap: the Python example in Hedera's tutorial sets an admin key. Ours must not.

### The events

| Fact | Source |
|---|---|
| Hello Future Origins ran from 21 July to 8 August 2025. | AngelHack's event page |
| The Hedera Africa Hackathon ran from 1 August to 30 September 2025. | Press pages. To confirm when the events table is filled. |
| Hello Future Apex took its submissions on StackUp, another website. | The Apex tracks page |
| Apex had a track named Legacy Builders: "For returning participants from past Hedera Hackathons, including Origins, to build on previous ideas or apply their experience to new concepts." | The Apex tracks page |
| The winner posts of Apex and Ascension link to demo sites and videos, not to project pages. | Hedera's blog |

Decision: the two events stay as planned, if DoraHacks agrees. The reasoning is in blueprint §3.4.

### The pass marks

| Fact | Source |
|---|---|
| A measured 95% on 300 separate items gives a range from 91.9% to 96.9%. When the items come in groups, as our fields do, the range is wider. | Our own calculation |
| Anthropic's best search setup missed 1.9% in its first 20 results. | Anthropic |
| A public test of free summaries, updated on 22 September 2026, measured unsupported content at 8% to 14% for the Gemini 3 and 3.1 models. Gemini 3.8 Flash is not in its list. A model does the judging in that test, not people. | Vectara |

Decision: the marks are fixed in blueprint §13.6, each with its reason.

## What went wrong

1. **Requests before the terms.** On 9 October the assistant sent about 40 scripted requests to DoraHacks: 31 project pages, the list pages, the robots.txt address, and on this day the home page and the terms page. The terms forbid scripted access. They should have been read before the first request. The blueprint even said "not read yet" and went on.
2. **A false name.** Those requests carried the name of a normal browser. A polite collector says who it is.
3. **MIT without research.** The first suggestion for the licence was MIT, given with no check. After the check the suggestion is Apache 2.0.
4. **Fields counted as separate items.** The first range for Test 1 treated 300 fields as 300 separate items. They come from 60 pages, so the range must be computed by project.

All four are in [`lessons.md`](lessons.md).

## What this does not prove

- DoraHacks may say no, or may not answer in time.
- The GitHub counts are totals from a search. They overlap, and some results are not hackathon projects. Nobody looked at them one by one.
- How READMEs are organised was not measured. The 31 pages of entry 01 were DoraHacks pages.
- The choice of a licence is not legal advice.
- The Vectara numbers were read through a summary of the page, and they describe another task than ours.
- The Python Hedera library was not run. That is Gate A.

## Next

1. Done on 9 October 2026: the owner sent the email, and answered Q9.
2. The rules of the other platforms: [entry 04](04-other-platforms.md).
3. Phase A.
