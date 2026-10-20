# 04 · The other platforms and their rules

- **Date:** 9 October 2026
- **Status:** done. Some pages could not be read, and they are listed below.
- **Result:** blueprint §5.6, and the owner's standing rule in `CLAUDE.md` (hard constraint 17)

## Goal

The owner asked why only the terms of DoraHacks had been read. The tool is meant to cover every Hedera hackathon, and those sit on several websites. So: which site holds which event, can its project pages be read without a sign-in, and what do its rules say about a program that reads them?

## Approach

For each site: find the event pages, look for a public list of projects, read the terms of use and the robots.txt file. Each page was fetched once by the assistant's web reader, a tool that opens one page and answers questions about it. No collector was run, and no project page was saved.

## Method

| Site | What was read |
|---|---|
| DoraHacks | Its terms (entry 03) |
| Devpost | `info.devpost.com/terms`, `devpost.com/robots.txt` |
| StackUp | The Apex event page on `hackathon.stackup.dev`, and its robots.txt address |
| AngelHack | `angelhack.com/terms-of-service/`, which the StackUp event page links to as its terms |
| 4hacks | `4hacks.io/hackathons`, three event pages, the addresses `/terms` and `/robots.txt` |
| ETHGlobal | `ethglobal.com/showcase`, `ethglobal.com/terms`, its robots.txt address |
| Hedera | `hedera.com/terms`, the winner posts |
| The Africa hackathon winners site | `hedera-hackathon.hashgraph.swiss` |
| GitHub | Its policy (entry 03) |

## Results

### Which site holds which event

| Event | Where the projects are | Source |
|---|---|---|
| Hedera20 (45 projects) | A platform by BeMyApp. Its address no longer exists. | A search result, then a failed request |
| Hedera21 (54) and Hedera22 (118) | Devpost | `hedera21.devpost.com`, `hedera22.devpost.com/project-gallery` |
| Beyond Blockchain 2023, Hello Future 2024, Hello Future 2.0 | Run by AngelHack. The place of the submissions was not found. | Hedera's winner posts, AngelHack's event pages |
| Hedera x AI 2025 | Run by Hashgraph Online. Its site shows the winners. The place of the submissions was not found. | `hol.org` |
| Hello Future Origins 2025 (159) | DoraHacks | `dorahacks.io/hackathon/hello-future-origins` |
| Hedera Africa Hackathon 2025 (more than 1,300) | DoraHacks. A second site shows the winners with links to DoraHacks. | `dorahacks.io/hackathon/hederahackafrica` |
| Hello Future Ascension 2025 (135) | StackUp | `hackathon.stackup.dev` |
| Hello Future Apex 2026 (368) | StackUp. The page gives the dates 17 February to 23 March 2026 and 1,197 participants. | `hackathon.stackup.dev` |
| Hedera Cross Campus Challenge 2026 | 4hacks, with 12 campus editions. The organiser shown on every page is Dar Blockchain. | `4hacks.io/hackathons` |
| Projects that took a Hedera prize at an ETHGlobal event | ETHGlobal's showcase | `ethglobal.com/showcase` |

### What each site allows

| Site | Can a visitor see the projects without a sign-in? | What its rules say about a program | 
|---|---|---|
| DoraHacks | Yes | Forbidden. A collection needs "written permission from Company". |
| Devpost | Yes | Forbidden. The terms, last updated on 5 December 2025, forbid whoever "uses manual or automated software, devices, scripts robots, or other means or processes to access, "scrape," "crawl" or "spider" the Site". Its robots.txt lets normal search robots in, but the terms still hold. Contact: `support@devpost.com`. |
| StackUp, for the Hello Future events | No. The Apex page shows no list of projects to a visitor. | The event page links to AngelHack's terms, last updated on 20 January 2025. They forbid to "use any manual or automatic device in any way to gather content on the Website ... except where our express prior written consent has been obtained", and to "create a database by systematically downloading and storing any content on the Website". Contact: `info@angelhack.com`. |
| 4hacks | No. Two editions that have ended show "Submissions 0" to a visitor. | No terms page was found: the address `/terms` opens the sign-in form. There is no robots.txt file. |
| ETHGlobal's showcase | Yes | No rule about programs was found in the pages that could be read. That is not a permission. |
| hedera.com | Yes | No rule about programs was found in its terms, last updated on 24 November 2025. Its content "may not be copied, disseminated, altered or made accessible to third parties for commercial purposes". We read the few winner posts by hand anyway. |
| GitHub | Yes | Allowed through its API (entry 03). |
| Hedera's mirror node | Yes | It is a public API, made for programs. |

### What this means

- **Every site that holds the submissions either forbids a robot or hides the projects behind a sign-in.** DoraHacks, Devpost and AngelHack forbid it in writing. StackUp and 4hacks show nothing to a visitor.
- So a memory of all Hedera hackathons cannot be built by a robot alone. It needs the sites, or the organisers, to agree or to hand over the data. The owner said this on 7 October already: real use needs the sites to take part. Now the documents show why, site by site.
- For the proof, the open doors are: a written yes from a site, a list given by an organiser, GitHub's API, the ledger, and the public winner posts read by hand.
- An organiser can agree for its own site and its own data. It cannot agree for another company's site. Dar Blockchain ran the Africa hackathon, but those pages sit on DoraHacks, and the rules of DoraHacks apply to them.

## What went wrong

1. **Only one site's terms were read.** The first version was limited to two events, both on DoraHacks, so only DoraHacks was checked. That limit itself was chosen partly because DoraHacks pages answered the first test requests. The whole map should have been drawn before any event was chosen.
2. **"On at least five websites" was written without the list.** The blueprint gave the number and no table. The table is now in §5.6.

Both are in [`lessons.md`](lessons.md).

## What this does not prove

- The pages were read through a summary tool. A clause can be missed. Before any request for permission, the owner should open the terms in a browser.
- StackUp's own terms were not found. Only the AngelHack terms linked from the event page were read.
- ETHGlobal's site terms were not found. The address `/terms` holds the event rules.
- What a signed-in participant can see on 4hacks and on StackUp is unknown. Nobody signed in.
- Where the submissions of Beyond Blockchain 2023, Hello Future 2024, Hello Future 2.0 and Hedera x AI 2025 can be read was not found.

## Next

The owner decides which source may run first (open question Q10). Until they say yes for a site, no collector runs there (hard constraint 17).

---

## 9 October 2026, later: 4hacks is out, three more requests, the sites that are gone

### 4hacks is excluded

The owner looked at 4hacks while signed in. Every hackathon there shows this message: "Submissions are private. The organizer has chosen to keep submissions private for this hackathon. Projects will not be visible to the public." So there is nothing to read there, with or without an account. 4hacks is out of the plan.

### Who to write to

| Site | Address | Where the address comes from |
|---|---|---|
| Devpost | `support@devpost.com` | Its terms of service |
| ETHGlobal | `hello@ethglobal.com` | Its rules page |
| AngelHack, also for StackUp | `info@angelhack.com` | Its terms of service. StackUp is part of AngelHack: AngelHack's own blog says "StackUp joins AngelHack". |

Status of the three emails below: **written, not sent.** The owner sends them. Each answer is written here with its date.

### Email to Devpost

```text
To: support@devpost.com
Subject: Permission request: reading the public project pages of two Hedera hackathons for a student project

Hello Devpost team,

My name is Mohamed Yaakoubi. I am a computer science student at the Faculty of Sciences of Sfax, in Tunisia. I am taking part in the FSS Campus Edition of the Hedera Cross Campus Challenge 2026, which is organised by Dar Blockchain. The deadline is 20 October 2026.

Your Terms of Service do not allow scripts or robots on the site. So I am writing to ask for your permission before I do anything.

What I am building
A small research tool that lets a builder search past Hedera hackathon projects before starting a new one. For each project it shows the team's own description and what the public Hedera ledger shows for the Hedera IDs the team listed. It gives no scores and no rankings, and each project links back to its page on Devpost.

What I would like to read
- Only the public project galleries of two hackathons, Hedera21 (hedera21.devpost.com) and Hedera22 (hedera22.devpost.com), and the public project pages they link to. About 180 pages, one time.
- From each page: the project name, the tagline, the description text, the "Built With" list, the links to the code and the demo, and the prize if there is one.
- Not collected: names, photos, profiles or contact details of team members, comments, likes, and anything that needs an account.

How
- One request at a time, at least one second apart.
- Each request carries the name of my tool and my email address, so that you can identify it.
- I stop at once if you ask me to.

Use
The collected pages stay on my laptop. The jury sees the tool in a demo and in a short video. The tool is not online and not commercial. If the project continues after the event, I will ask you again before anything is published.

If you prefer another way, for example an export or an API, I will gladly use that instead. And if your answer is no, I will respect it.

Because of the deadline, an answer in the next few days would help me a lot. Thank you for your time.

Mohamed Yaakoubi
Faculty of Sciences of Sfax, Tunisia
```

### Email to ETHGlobal

```text
To: hello@ethglobal.com
Subject: A question before I read your public showcase with a program (student project on Hedera)

Hello ETHGlobal team,

My name is Mohamed Yaakoubi. I am a computer science student at the Faculty of Sciences of Sfax, in Tunisia. I am taking part in the FSS Campus Edition of the Hedera Cross Campus Challenge 2026, which is organised by Dar Blockchain. The deadline is 20 October 2026.

I found no rule about programs in your rules page. I prefer to ask you before I start, and I will not start without your answer.

What I am building
A small research tool that lets a builder search past projects built on Hedera before starting a new one. For each project it shows the team's own description and what the public Hedera ledger shows for the Hedera IDs the team listed. It gives no scores and no rankings, and each project links back to its page in your showcase.

What I would like to read
- Only the public showcase pages of projects that took a Hedera prize at your events. A few hundred pages at most, one time.
- From each page: the project name, the short description, the description text, the "How it's made" text, the links to the code and the demo, the event and the prize.
- Not collected: names, photos or profiles of team members, and anything that needs an account.

How
- One request at a time, at least one second apart.
- Each request carries the name of my tool and my email address, so that you can identify it.
- I stop at once if you ask me to.

Use
The collected pages stay on my laptop. The jury sees the tool in a demo and in a short video. The tool is not online and not commercial. If the project continues after the event, I will ask you again before anything is published.

If you already have a list of the projects with a Hedera prize, or an API, I will gladly use that instead. And if your answer is no, I will respect it.

Because of the deadline, an answer in the next few days would help me a lot. Thank you for your time.

Mohamed Yaakoubi
Faculty of Sciences of Sfax, Tunisia
```

### Email to AngelHack, first version

**Replaced later the same day.** The owner found that the submissions are private even for a signed-in visitor, so asking to read them with an account makes no sense. The version to send is further down, under "The email to the Hello Future team".

```text
To: info@angelhack.com
Subject: Permission request: the submissions of the Hedera Hello Future hackathons, for a student project

Hello AngelHack team,

My name is Mohamed Yaakoubi. I am a computer science student at the Faculty of Sciences of Sfax, in Tunisia. I am taking part in the FSS Campus Edition of the Hedera Cross Campus Challenge 2026, which is organised by Dar Blockchain. The deadline is 20 October 2026.

Your Terms of Service say that content may be gathered only with your express prior written consent. I am writing to ask for it.

What I am building
A small research tool that lets a builder search past Hedera hackathon projects before starting a new one. For each project it shows the team's own description and what the public Hedera ledger shows for the Hedera IDs the team listed. It gives no scores and no rankings, and each project links back to its original page.

What I am looking for
The project submissions of the Hedera hackathons that AngelHack ran: Hello Future Ascension (2025) and Hello Future Apex (2026) on hackathon.stackup.dev, and, if they still exist, Hello Future 2024, Hello Future 2.0 and Beyond Blockchain 2023.

As a visitor I see no public list of the submissions for these events. So I have two questions.
1. Is there a public page where these submissions can be read?
2. If not, could you share a list of the submitted projects, or allow me to read them with an account? I need only the project name, the description, the links to the code and the demo, the Hedera IDs, the track and the prize. I do not need any data about the team members.

How
- If a program is allowed: one request at a time, at least one second apart, with the name of my tool and my email address in each request.
- I can create an account if that is needed. I will not use an account with a program unless you say yes in writing.
- I stop at once if you ask me to.

Use
The data stays on my laptop. The jury sees the tool in a demo and in a short video. The tool is not online and not commercial. If the project continues after the event, I will ask you again before anything is published.

If your answer is no, I will respect it. Because of the deadline, an answer in the next few days would help me a lot. Thank you for your time.

Mohamed Yaakoubi
Faculty of Sciences of Sfax, Tunisia
```

### The sites that could not be found, or that are gone

| Event | What was found | What is still to check, by the owner in a browser |
|---|---|---|
| Hedera18 (2018) | It ran in several cities at once. Its BeMyApp address now sends the visitor to BeMyApp's general events page. A quick check of the Wayback Machine found no copy of that address. | Whether web.archive.org shows any copy |
| Hedera20 (2020) | The landing page `events.bemyapp.com/hedera20` still exists. The platform with the projects, `hedera20-platform.bemyapp.com`, is gone, and the quick check of the Wayback Machine found no copy. | Whether web.archive.org shows any copy |
| Beyond Blockchain 2023 | AngelHack ran it. Hedera's winner post names seven winners with no links and speaks of "dozens" of submissions. No submission site was found. | The answer of AngelHack |
| Hello Future 2024 and Hello Future 2.0 | Their site is `previous.hellofuturehackathon.dev`. Its security certificate has expired, so the assistant's reader refuses it. A news page names three winners of the first one and no submission site. | Open the site in a browser and see where the "submit" link pointed. The answer of AngelHack. |
| Hedera x AI 2025 | The pages `hol.org/hedera-ai-agents-hackathon` and `hol.org/blog/hedera-ai-hackathon-winners` exist, but they refuse the assistant's reader. | Open them in a browser and see where the project links go |
| Every Hedera event on DoraHacks | The page `dorahacks.io/org/hah` is the organiser page "Hedera Hacks". It should list all its events. The assistant cannot read DoraHacks. | Open it in a browser and note the events that are not in blueprint §5.6 |
| Hello Future Ascension and Apex | On StackUp. A visitor sees no list of projects. | Whether a signed-in visitor sees a list. This is only a look by hand. |

### The Wayback Machine

- It is a public archive of old web pages, at `web.archive.org`. It has doors for programs: one that says whether a copy of an address exists, and one that lists all copies of a site.
- The quick check through the first door found no copy for the three addresses tried. That check can miss copies that sit under a slightly different address. The second door gives the full list, but the assistant's reader cannot reach it.
- Its terms of use could not be read with the assistant's tools. They must be read before any program uses it. A news page says that in September 2026 the archive added protections against heavy automated traffic.
- **The rule for this project:** the Wayback Machine is used only for a site that no longer exists. It is never used to get the pages of a site that said no, or that has not answered. That would be a way around a block, and hard constraint 10 forbids it.

### What this later part does not prove

- Nobody checked that the three email addresses are read by a person.
- "No copy in the Wayback Machine" rests on a quick check of three exact addresses.
- The count "about 180 pages" for Devpost comes from Hedera's own numbers for the two events (54 and 118 projects), not from the galleries.

---

## 9 October 2026, last: what the owner found in their browser

The owner opened every site of the list above by hand.

| Site | What they found |
|---|---|
| `dorahacks.io/org/hah` | The organiser page "Hedera Hacks". It lists one event only: the Hedera Africa Hackathon, with the number 1,396 and "Winner Announced". Its text says that The Hashgraph Association and the Exponential Science Foundation give the money and the direction, and that Dar Blockchain is the partner that runs the events. |
| `hol.org/hedera-ai-agents-hackathon` | Only the winners of Hedera x AI 2025, each with a description. No link to the submissions. |
| `previous.hellofuturehackathon.dev` | It cannot be opened in any browser. Its security certificate expired on 5 September 2025, and the site's own safety setting forbids the browser to go on. |
| `hackathon.stackup.dev`, signed in | The events are shown. The submissions are private, also for a signed-in visitor. The old copy in the Wayback Machine shows the same. |
| `hedera18hackathon.bemyapp.com` | It sends the visitor to BeMyApp's general site. They searched about 20 pages of its events and found nothing about Hedera. |
| The Wayback Machine, for `hedera18hackathon.bemyapp.com` | A copy exists. It lists the winners with a very short description each, and no code. The assistant's quick check had said "no copy". The quick check was wrong for this address. |
| `platform.bemyapp.com` | The address is dead, and the Wayback Machine never saved it. |

They also found two public pages that the assistant had missed: `hellofuturehackathon.dev/originswinners` and `hellofuturehackathon.dev/ascensionwinners`. A page for the Apex winners is expected.

### What the two winners pages hold

The assistant opened each page once.

| Page | Winners | What each entry shows | What is missing |
|---|---|---|---|
| Origins winners | 12, in four tracks | The name, a description of a paragraph, a link to the project's website | The code, any Hedera ID, the team |
| Ascension winners | 16, in five tracks and one more group | The name, a description of three to five sentences, the tech stack, a link to the website or a video | The code, any Hedera ID, the team |

The footer of the site points to AngelHack's terms of service. So AngelHack's rule applies here too: no gathering of content without its written consent. The site gives its own address: `support@hellofuturehackathon.dev`.

**One thing these pages show.** The name Effisend appears among the winners of three events of 2025: Origins, the Africa hackathon and Ascension. ChargeFrog, MedQ and Golden Needle appear among the winners of both Ascension and Apex. A name that returns is a hint, not a proof that it is the same team. But nobody can see these returns in one place today.

### What it means for the plan

- **For eight of the twelve big events, no place was found where the submissions can still be read.** The platforms of Hedera18 and Hedera20 are gone. The old Hello Future site cannot be opened. The submissions of Ascension, Apex and this year's campus challenge are private. For Beyond Blockchain 2023 and Hedera x AI 2025 only the winners are public. The full submissions are public for four events: Hedera21 and Hedera22 on Devpost, Origins and Africa 2025 on DoraHacks.
- So the memory has two kinds of entry. A **full card** where the submission page is public. A **winner entry** where only the organiser's announcement is left. This is now blueprint §4.6.
- The first line of the project, "every project sent to a Hedera hackathon", says more than the data can give. The honest line is in blueprint §1.4.

### The email to the Hello Future team

The owner left the choice to the assistant: keep AngelHack or drop it. **Decision: keep it, with a smaller request.** The reasons are in blueprint §4.6. Status: **written, not sent.**

```text
To: support@hellofuturehackathon.dev
Cc: info@angelhack.com
Subject: Permission request: using the public winners pages of the Hello Future hackathons in a student project

Hello Hello Future team,

My name is Mohamed Yaakoubi. I am a computer science student at the Faculty of Sciences of Sfax, in Tunisia. I am taking part in the FSS Campus Edition of the Hedera Cross Campus Challenge 2026, which is organised by Dar Blockchain. The deadline is 20 October 2026.

Your Terms of Service say that content may be gathered only with your express prior written consent. I am writing to ask for it.

What I am building
A small research tool that lets a builder search past Hedera hackathon projects before starting a new one. It gives no scores and no rankings, and each project links back to the page it comes from.

What I would like to use
- Only your public winners pages: hellofuturehackathon.dev/originswinners and hellofuturehackathon.dev/ascensionwinners, and the Apex winners page when it is published. Three pages.
- From each winner: the project name, the track, the description, the tech stack and the link to its website.
- No data about team members.

How
- I read these three pages once, by hand or with a small program, whichever you prefer.
- I stop at once if you ask me to.

One question
The submissions of these events are private on StackUp, also for a signed-in visitor, and I understand that. If it is ever possible to share a list of all the submitted projects, with only the name, the description and the links, it would make the tool much more complete. If not, the winners pages are enough.

One thing you may want to know
The old site previous.hellofuturehackathon.dev cannot be opened any more. Its security certificate expired on 5 September 2025, and browsers refuse the connection. The footer of your site still links to it for Hello Future 1.0 and 2.0.

Use
What I collect stays on my laptop. The jury sees the tool in a demo and in a short video. The tool is not online and not commercial. If the project continues after the event, I will ask you again before anything is published.

If your answer is no, I will respect it. Because of the deadline, an answer in the next few days would help me a lot. Thank you for your time.

Mohamed Yaakoubi
Faculty of Sciences of Sfax, Tunisia
```

---

## 9 October 2026, 16:50: the first answers

| Site | Answer | When |
|---|---|---|
| ETHGlobal | **Yes, in writing.** | 9 October 2026, 16:33 |
| Devpost | **No** for a program. Yes for normal browsing and for links. | 9 October 2026, 16:35 |
| The Hello Future team, AngelHack | The owner sent the second version of the email. No answer yet. | Sent on 9 October 2026 |
| DoraHacks | No answer yet. The owner's mail tool shows that the email was opened. | Sent on 9 October 2026 |

The owner keeps the emails themselves. They are the proof. The names of the people who answered are left out here on purpose.

### What ETHGlobal wrote

"If everything that you have described is accurate, then this request would be completely fine as long as you honor your commitment."

So the yes holds only as long as every promise of our email is kept. The promises and what they mean for the code are in blueprint §5.7.

### What Devpost wrote

"Unfortunately, we're not able to grant exceptions to the restrictions on automated access in our Terms of Service, and we don't currently offer an export or API for project galleries."

"You're welcome to browse the Hedera21 and Hedera22 project galleries normally and refer to the projects in your tool, linking back to their Devpost pages."

So no program ever touches Devpost. A person may browse it and note names and links.

### The owner's decisions after these answers

- **ETHGlobal's showcase is the first source.** Their words: "I believe we can start with ETH scraping." This is their yes for this site under hard constraint 17. It covers only what the email described.
- **The winners page of Hedera x AI on `hol.org` is kept, with no request.** It is one page of one event. It is read by hand in a browser, because the site refuses the assistant's reader, and a refusal is a block that we do not work around.

### What the assistant found for the ETHGlobal collector

A web search, not a request to ETHGlobal, names these events with a Hedera prize: Prague 2025, Cannes 2025, New York 2025, New Delhi 2025, ETHOnline 2025, Cannes 2026 and New York 2026. There may be more. Each event has a page of the form `ethglobal.com/events/<event>/prizes/hedera`.

The number of projects will be small. Our email asked for the projects that took a Hedera prize, and an event gives such a prize to about five to ten teams. So the estimate is 40 to 70 projects in all. The collector gives the real number.

After the yes arrived, the assistant did not open any ETHGlobal page. Its web reader does not carry the owner's contact address, and the email promised that every request does.

### What this last part does not prove

- The numbers of winners (12 and 16) and the returning names were read through a summary tool, once. Before they are used in a pitch, the owner should look at the pages themselves.
- The list of ETHGlobal events comes from one web search. It must be checked by hand before the collector runs.
- The promises in blueprint §5.7 are taken from the draft of the email. If the owner changed words before sending, the sent text counts.

---

## 9 October 2026, about 17:10: the first winner entries, and the yes for Hedera's posts

### The winners of Hedera x AI, copied by hand

The owner opened `hol.org/blog/hedera-ai-hackathon-winners` in their browser, copied the text and pasted it into the chat. No program read that site.

Three files now sit in the local data folder. Git does not see them.

| File in `data/by-hand/hol.org/` | What it is |
|---|---|
| `hedera-x-ai-2025-winners.page.txt` | The text as the owner pasted it. One line was cut out before saving: the name of the post's author. |
| `hedera-x-ai-2025-winners.meta.json` | Where the text comes from, how and when, and its fingerprint |
| `hedera-x-ai-2025-winners.entries.json` | Six winner entries. A small script cut each description out of the text, so each one is word for word. The script checked that. |

What the post gives, as facts:

| Track | First place | Second place |
|---|---|---|
| Agent Kit / MCP | Franky | TalentAI |
| HCS-10 Open ConvAI | Unthink AI | Novix |
| Eliza OS | HederaPayBot | Contracts Auditor |

- The post is dated 12 June 2025.
- It names more than 300 hacker sign-ups. It does not say how many projects were sent in.
- It gives no link to any code and no Hedera ID. So these six are winner entries (blueprint §4.6).

### Hedera's own winner posts: by a program

The owner's words: "For hedera by program if the tool call wasnt refused by the server." So this is their yes for the winner posts on `hedera.com`, with one condition: if the server refuses the program, we do not work around it. Then the pages are saved by hand.

**Not collected yet, on purpose.** The assistant's web reader gives a summary of a page and only short quotes. It cannot give the exact text, and a winner entry needs the description as it was published. So the real collector reads these pages, in the build.

**One warning.** On 9 October a simple request from the owner's laptop to `hedera.com` failed. Other sites failed the same way, so it may be the laptop and not a refusal. The collector tries one request first. If Hedera's server refuses it, nothing more is tried: the owner saves the nine pages from their browser with "Save page as" into `data/by-hand/hedera.com/`, and the parser reads them from there.

The nine posts that we know:

| Event | Address |
|---|---|
| Hedera20 | `hedera.com/blog/hedera20-hackathon-winners` |
| Hedera21 | `hedera.com/blog/announcing-the-hedera21-hackathon-winners` |
| Hedera22 | `hedera.com/blog/congratulations-to-the-hedera22-hello-smart-contract-hackathon-winners` |
| Beyond Blockchain 2023 | `hedera.com/blog/the-winning-projects-of-the-beyond-blockchain-hackathon-2023` |
| Hello Future 2024 | `hedera.com/blog/these-are-the-winners-of-the-2024-hellofuture-hackathon` |
| Hello Future 2.0 | `hedera.com/blog/these-are-the-winners-of-the-hellofuture-hackathon-2-0` |
| Hello Future Origins | `hedera.com/blog/these-are-the-winners-of-the-hello-future-origins-hackathon` |
| Hello Future Ascension | `hedera.com/blog/these-are-the-winners-of-the-hello-future-ascension-hackathon` |
| Hello Future Apex | `hedera.com/blog/these-are-the-winners-of-the-hello-future-apex-hackathon` |

Two things are not covered by this yes, because they are other sites:

- The winners of the Africa hackathon are on `hedera-hackathon.hashgraph.swiss`.
- The winners of Hedera18 are only in an old copy in the Wayback Machine.

### What this part does not prove

- The text of the Hedera x AI post is the owner's copy from their browser. Nobody compared it with the page a second time.
- Whether Hedera's server accepts the collector is not known yet.
- The nine addresses come from web searches and from earlier reading. Each one is checked when the collector first asks for it.

---

## 9 October 2026, 17:25: the winners of Hedera18, copied by hand

The site of Hedera18 is gone. The Wayback Machine holds an old copy of it, saved on 22 November 2018:
`web.archive.org/web/20181122212620/http://hedera18hackathon.bemyapp.com/`

The owner opened that copy in their browser, copied the winners part and pasted it into the chat. No program read the archive. So the rule about programs and the Wayback Machine (blueprint §5.6) is not touched.

Three files now sit in the local data folder. Git does not see them.

| File in `data/by-hand/web.archive.org/` | What it is |
|---|---|
| `hedera18-winners.page.txt` | The text as the owner pasted it. One line was cut out before saving: the names of the four members of the winning team. |
| `hedera18-winners.meta.json` | Where the text comes from, how and when, and its fingerprint |
| `hedera18-winners.entries.json` | Eight winner entries. A small script cut each description out of the text and checked that it is word for word. |

What the page gives, as facts:

| Winner | Where | Result |
|---|---|---|
| PayPer | London | Global winner, first place, and the prize of its own city |
| Blume | Bangalore | Local winner |
| Hash Name Service | Dallas | Local winner |
| Helpon | Moscow | Local winner |
| Proof of Life | Paris | Local winner |
| H X | San Francisco | Local winner |
| Artgraph | Singapore | Local winner |
| Cronos | Tel Aviv | Local winner |

- The event ran in eight cities at once.
- The page gives one sentence per project. It gives no code and no Hedera ID. In 2018 the public network of Hedera was not open yet, so there is nothing on the ledger to check for these projects. They are winner entries (blueprint §4.6).
- The page does not say how many projects were sent in.

### Where the winner entries stand

| Event | Winner entries |
|---|---|
| Hedera18 | **Done by hand:** 8 |
| Hedera x AI 2025 | **Done by hand:** 6 |
| The nine events with a winner post on `hedera.com` | To do in the build, by the collector, or by hand if the server refuses it |
| Africa 2025 | Its winners are on another site. No yes yet. |

### What this part does not prove

- The text is the owner's copy of an old copy. Nobody compared it with the archive a second time.
- "The public network was not open yet in 2018" is from memory of Hedera's history. It was not checked on this day.
- "The same name" was not checked against a repository or a Hedera ID. It is a hint.
- What the number 1,396 on the DoraHacks page counts was not checked. It fits the "more than 1,300 projects" of the press.
