# Hackathon Memory: governing rules

This file is loaded in every session. It outranks habit, tutorials and patterns from training data. If something you are about to build conflicts with a rule here, stop and tell me.

"I" and "me" in this file mean the owner, Mohamed Yaakoubi.

## 0. What this is, and where the reasoning lives

- **The project:** one place that knows every project sent to a Hedera hackathon: what it claimed, what really happened, and whether it is still alive. The working name is Hackathon Memory.
- **The event:** FSS Campus Edition of the Hedera Cross Campus Challenge 2026. **The submission opened on 19 October 2026 and closes on 7 November 2026** (my words of 20 October: "Wtf submission opened on 19/10/2026 they suddenly lowered 1 day [...] Anyway submission closes 7 novemeber, so I still got 17 days"). The registration opened on 10 August 2026 (my words of 18 October: "FSS registration opened Aug 10, 2026, still waiting for submission closure announecement"), so that is the first day of the hackathon, and 7 November 2026 is its last.
- **The one behaviour that matters most:** a builder types an idea and sees the closest past Hedera hackathon projects, each with what the Hedera ledger says about it. Everything else is optional.
- **The reasoning** is in `docs/blueprint.md`. This file gives orders, and the blueprint explains them. Marks like (§6.3) always point into the blueprint. A section of this file is named in words, like "section 9 of this file". If the two files disagree, that is a bug: fix both and tell me.
- **The history** is in `backlog/`: what was done, how, and what went wrong. Start at `backlog/INDEX.md`. This file, `backlog/` and `docs/` are committed and pushed since 20 October 2026 (constraint 20).
- **The public design document** is `DESIGN.md`, in the repository. It is written from the blueprint, in a neutral voice, with the same section numbers, and it names no working note. When the blueprint changes something that `DESIGN.md` says, change both in the same session.
- **No other planning files.** Do not commit a PLAN, TODO, STATUS or FINDINGS file. A working plan for one session stays out of git. Its result goes into the backlog entry and the commit messages.
- **The repository** is private: `github.com/mohamedyaakoubi/hackathon-memory`. The folder around this one is a separate research repository. Never add this folder to it. The remote repository holds no working note (constraint 20) and no sign of the assistant (constraint 19).
- **My standing order from 2026-10-09:** build everything, and run no collector on any site until I say yes for that site (hard constraint 17). My yes is recorded for three: ETHGlobal's showcase, GitHub's API (Q17, 2026-10-10), and the one page of `hedera-hackathon.hashgraph.swiss` with the winners of the Africa hackathon (2026-10-10). On 2026-10-10 I widened the collection on ETHGlobal: every project that its showcase ties to Hedera, 658 pages, and not only the 92 with a Hedera prize that my email named. I send no second email (backlog entry 11). I confirmed that my email to ETHGlobal was sent unchanged (Q19). The note for the next session is at the top of `backlog/INDEX.md`.

Read order for a new session: this file, then `backlog/INDEX.md`, then the parts of `docs/blueprint.md` that the task needs.

## 1. Verify before you build

Never write these from memory. Check the primary source first, and write the date you checked into the backlog entry.

- **The shape of a library's functions.** Read the installed package's own source or its current official page. This matters most for `hiero-sdk-python`, the Google Gen AI SDK and Playwright.
- **Model names, prices and limits.** Read Google's own page for the Gemini models in use (3.1 Pro and 3.8 Flash) and for the embedding model on the day you write the code.
- **How a website behaves.** Send one real request and look at the answer before you write a collector for it.
- **A Hedera rule or fee.** Read docs.hedera.com.
- **A claim about another project.** Read its code or its own status notes, not only its README.

## 2. Hard constraints

The numbers are fixed forever. Never renumber, never reuse a number. "Decision" means I can change it. "Mandate" means an outside rule that neither of us can change.

| # | Constraint | Kind |
|---|---|---|
| 1 | The AI never gives a score, never ranks quality, never picks a winner, and never says a project is a copy. It shows facts side by side, and people judge. (§3.3) | Decision |
| 2 | Facts never come from the LLM. IDs, links, dates, counts and statuses come only from the parser, the code host or the ledger. (§6.4) | Decision |
| 3 | Every field written by the LLM carries a label (stated, inferred or not found) and exact quotes from the page. Code checks every quote against the saved page. A field with no checked quote is dropped and logged. (§6.3) | Decision |
| 4 | Parser first. A titled section is copied word for word. The LLM is never asked to rewrite a section the parser already copied. (§6.1) | Decision |
| 5 | Raw pages are saved as received and never edited afterwards. There are two exceptions, both made before the page is saved. First, the part of a page that shows team members is cut out, because that was promised to the sites. Second, because the cut needs an HTML parser, the page is written again by the parser: the text, the links and the order of the tags stay the same, and the spaces between tags and the spelling of the markup may change. The fingerprint of what the site sent is kept beside the page. Everything else must be rebuildable from the saved pages with one command. (§5.3, §5.7) | Decision, changed 2026-10-09 (the team part), and again on 2026-10-10 (the parser) |
| 6 | No number is shown to anybody unless it comes from a test in `evals/` with a dated result file. The model under test never grades its own work. (§13) | Decision |
| 7 | All LLM calls use Gemini on Vertex AI: Gemini 3.1 Pro for the first layer (reading and rewriting the project pages into cards), Gemini 3.8 Flash for the search. Embeddings use Google's embedding model. No other paid model or service without my decision. **Since 20 October 2026 my Google Cloud account holds about $15 of credit in all: before any call that costs money on it, tell me how much and for what, and wait for my yes** (my words: "My whole gcp account credit now only has $15 so if you need to use any let me know first how much u'd need and for what"). (§11.3) | Decision, 2026-10-09, changed the same day; the credit added 2026-10-20 |
| 8 | Only the fixed fingerprint record goes to the Hedera topic. No free text, no names, no secrets. A message on a topic can never be deleted. (§9.3) | Mandate |
| 9 | Secrets live only in `.env` or the system's credential store. They never appear in git, logs, the database, a test file or the chat. Check that a secret exists without printing it. (§15) | Decision |
| 10 | Read a site's terms of use before the first request to it. If they ask for permission, send no automated request until I have a yes in writing. Today: ETHGlobal said yes in writing. Devpost said no, so no program ever touches Devpost. DoraHacks and AngelHack have not answered, so no program touches them (§5.6). When collection is allowed: one request at a time per site, at least one second apart, a real name and a contact address in each request, stop after repeated errors. Never work around a block. Never sign in to a site, unless I lift that for one site in the chat. **A 429, "too many requests", is a speed limit and not a block:** the tool stops the run, waits one hour (longer if the site names a longer time) and goes on five times slower, by itself. A real no (401, 403, 451, a bot check, or a third 429 within a day) still needs my decision. The stop that I promised to a site is for a stop order from its people, and that is the switch in `.env`. (§5.2) | Decision, tightened 2026-10-09, the 429 added on 2026-10-11 ("the stop on refusal is meant as the siteowner to send a stop order") |
| 11 | Store no personal data that the check does not need: no team member names, emails or photos. A repository owner's name is kept only as part of the repository link. (§5.4) | Decision |
| 12 | Choose by need. A tool or a shortcut must be justified by what the job needs and by a source. "Already installed", "easy" and "free" are not reasons. (§11) | Decision, 2026-10-09 |
| 13 | Documents and reports: simple English, short sentences, no em dashes, every technical word explained the first time. **The website talks like a normal product** (changed 2026-10-20, my words: "talk normally in the website"): plain, natural sentences with the usual words of the field (embedding, semantic search, keyword search, mirror node, HashScan, topic), each explained once in its (i) note, and never a made-up paraphrase such as "turns your idea into numbers". **The chat with me** stays easy, detailed and full of context (my words: "am the dumbest one here, you talk to me in easy detailed full context way"). | Decision, changed 2026-10-20 (the website) |
| 14 | No page of the website is built before its screen is described in §12. No screen is called done before both review layers. (§12) | Decision |
| 15 | Use only the limits the event states. Do not add the law or the market of a country that nobody named. | Decision |
| 16 | Stay inside this project folder. Anything outside it is out of scope: my personal notes (my vault), my other projects and the other folders of my machine. Do not open, list, search or change it, unless I ask in the chat. Never print a secret. | Decision, changed 2026-10-10 (the vault is out of scope) |
| 17 | **No collector runs against a live site until I say yes in the chat for that site.** Write the collectors and test them on saved sample files: that is allowed and wanted. Before the first live run on a site, ask me, name the site and what will be read, and wait for my yes. A yes for one site is not a yes for another, and a yes from an earlier session does not count unless it is written in `backlog/decisions.md`. This covers every site in §5.6, GitHub's search included. Not covered, so free to use: the Hedera mirror node, the Hedera test network, Google's two models, the local database. (§5.2) | Decision, 2026-10-09 |
| 18 | **The way a site is read is a rule for the code.** For every site we asked: one request at a time with a pause, my tool's name and my contact address in every request, no team member data saved, a stop switch per site, no page text in git, nothing online, a page is never asked for twice, a limit of requests for each site that is counted on disk, and a new request before anything is published. Each has a test. No other tool reads these sites for us, also not your own web reader. **The scope for ETHGlobal is my decision of 2026-10-10:** every project that its showcase ties to Hedera (658 pages, a limit of 800 requests), and not only the projects with a Hedera prize that my email named ("Only the public showcase pages of projects that took a Hedera prize [...] A few hundred pages at most"). My reading: the answer of ETHGlobal is about the method, no sensitive data and no heavy load, and a second email is not needed. The assistant told me once that this goes past the letter of the email, and then did it. It does not write anywhere that the consent of ETHGlobal covers the other pages. (§5.7) | Mandate for the method, 2026-10-09. The scope: my decision, 2026-10-10 |
| 19 | **No co-author line, and no sign of the assistant in the product.** No "Co-Authored-By" line for Claude or any other tool, no "Generated with" line, no sentence such as "built with an AI coding assistant", and no mention of the assistant in a commit message, a pull request, the code, a comment or the README. **Changed on 2026-10-20:** the working notes are pushed (constraint 20) and name the assistant by nature; this rule no longer covers them. A hook that only exists on this laptop (`.git/hooks`, its source `backlog/tools/hooks/check_public.py`) blocks a commit message or a push that breaks the rest of the rule. What the rule said before: nothing that left the laptop showed that an AI assistant helped, because the stereotype of "vibe coding" hurts the person who ships the work. | Decision, 2026-10-10, changed 2026-10-20 |
| 20 | **Changed on 2026-10-20: the working notes are committed and pushed.** My words: "I made a mistake in the beginning of the project where I said no claude.md should be shared and no backlog etc, I pull these words, from now on they become public and pushed and yes you can put the mistakes in the backlogs so future AIs can learn from it." So CLAUDE.md, `backlog/` and `docs/` are in git, and the backlog keeps every mistake with its lesson. What stays out: secrets, `data/`, any text taken from a collected page, my personal notes and my other projects, and the vendored copy of git-filter-repo (`backlog/tools/rewrite/filter_repo_pkg/`, excluded in `.git/info/exclude`). What the rule said before: the notes stayed on this laptop only. | Decision, 2026-10-10, changed 2026-10-20 |
| 21 | **Dropped on 2026-10-10: Dar Blockchain holds no historical submissions, so nothing of it is read.** My words: "drop dar blockchain unless you can prove me the opposite that they got any data". What the rule said before: Dar Blockchain is not a global company. It is an internal matter of the faculty (FSS), and my teacher said that I do not have to be formal with it. Requests to its site carry no tool name, no contact address and no signature. Everything else of constraint 10 stays: one request at a time, a pause, a stop at the first refusal, no sign-in, no team member data. Constraints 10 and 18 (a name and an address in each request) hold for every other site. Constraint 17 also holds: before the first run on its site I say yes for the pages that will be read. | Decision, 2026-10-10 |

## 3. Where this project is most likely to be built wrong

Each line names the wrong pattern. Refuse it.

- **"The ID exists, so the proof is real."** Almost every small number exists on Hedera as something. Proof needs the right kind of thing and dates that fit the event. (§7.2)
- **"No Problem title, so the page says nothing about the problem."** The label depends on the content, not on the titles. (§6.3)
- **"Ask the list for page 2 with a simple request."** The DoraHacks list returns the same first 19 projects. It needs a real browser. (§5.1)
- **"Test network and main network share IDs."** The same number is a different thing on each network. Always store the network with the ID. (§7.1)
- **"The same ID in two projects means the same team."** Some IDs are shared services that many projects use. (§8.4)
- **"The LLM summary reads well, so it is right."** Only the quote check and the graded test say that. (§13)
- **"A full-page screenshot shows the page."** One capture can miss content that appears on scroll. Use the page as a person does. (§12.3)
- **"The command was not found, so the program is not installed."** On my laptop the tool shells do not see my programs. Check the install folder. (`backlog/01-research.md`)
- **"A long message fits in one topic message."** One message holds about 1 KB. Ours must stay far below. (§9.3)
- **"The page is public, so a program may read it."** The site's terms decide that, not the fact that a browser can open the page. The terms of DoraHacks ask for written permission. (§5.2)
- **"Copy the topic example from the tutorial."** Hedera's Python example sets an admin key. Our topic must have none. (§9.5)
- **"Anything shaped like 0.0.123 is a Hedera ID."** A version number has the same shape. The words around it decide. (§6.1)
- **"300 graded fields are 300 separate items."** They come from 60 pages, and the fields of one page go wrong together. Compute the range by project. (§13.1)
- **"It must be production level, so add Spark, Kafka or a big pipeline tool."** The whole data is about one gigabyte. Production level means careful habits, not big tools: migrations, steps that are safe to run again, a job list inside PostgreSQL, a table of runs, backups, tests on every change. (§11.6)
- **"The site is gone, so take its pages from the Wayback Machine."** Only for a site that no longer exists, after its terms are read and after my yes. Never as a way around a site that said no or has not answered. (§5.6)
- **"Put a fast index on the embedding column."** The embeddings have 3,072 numbers, and the normal index stops at 2,000. At our size the exact search needs no index. (§11.6)
- **"ETHGlobal said yes, so read the whole showcase."** Not the whole showcase. Only the list with the filter `partners=hedera` and the pages of its 658 projects, winners or not (my decision of 2026-10-10). The walk saves no page of the list. The limit is 800 requests over all runs. (§5.7, backlog entry 11)
- **"A 429 means the site said no."** It means: too fast. The tool waits one hour and goes on five times slower, by itself. Start a run with `--wait` and it does both. Never go faster than the pause that is written in the count file. (backlog entry 11)
- **"Two seconds between requests is polite enough."** It was our own number. At one request every 2.5 seconds, 26 a minute, ETHGlobal answered 429. A pace is checked against what the site bears, and the tool must be able to slow down. (backlog entry 11)
- **"Tell the reader of the repository every detail."** The public notes stay general (my decision of 2026-10-10): who was asked, who agreed, how a site is read. No account of single requests, no list of small sources, nothing that only makes me look bad. But never a sentence that says the opposite of what happened, and never that a consent covers more than it does. The whole story stays in the backlog. (backlog entry 11) **Since 20 October 2026 the backlog is pushed too, with the whole story and its mistakes** (constraint 20); the README and the design document stay general.
- **"The Hedera prize page lists the winners."** It does not. The prize pages of ETHGlobal list prizes and bounties only, and so does the page with all the prizes of an event (measured on 10 October 2026, backlog entry 07). A winner is shown only on its own project page, in the block "Winner of / Hedera / prize / place". The winners are found by the walk through the Hedera list of the showcase (backlog entry 10).
- **"Give the ceremony video to Gemini and get the Hedera winners."** The video shows the finalists, not all the Hedera prize winners. Google says that one request takes about 45 minutes of video with sound, that a YouTube address is a preview feature, and that a frame costs 70 tokens at the default setting, so small slide text is lost. Use the video only as a cross-check, after a test with known answers. (backlog entry 07)
- **"The most common sponsor id is Hedera."** The showcase list names a sponsor by an id, not by a name. The id of Hedera is decided by pages that a person saw with a Hedera prize: it is the one id that all of them have. Each page is then checked again by its own "Winner of" block. (backlog entry 10)
- **"A page of the list holds 33 new projects."** It holds 32. Its last row is the first row of the next page. (backlog entry 10)
- **"Run the walk or the run once more, to be sure."** A page is read once. A walk or a run that is started again sends a request only for what is missing. `python -m proofs.lists` checks what is on disk and sends no request.
- **"The browser was blocked, so the tool needs a login or a browser robot."** A browser loads the data of every card at once. Try the slow, signed request first. Never use a login on a site that was promised "nothing that needs an account". (backlog entry 10)
- **"The page gives the Hedera ID."** Only 6 of the 92 pages of ETHGlobal do. 90 link to GitHub. The ID is also searched in the README of the code. (backlog entry 10)
- **"Use the scores that are in the page data."** ETHGlobal's pages carry scores and a summary that the site computes (`autoOriginality`, `autoPracticality`, `autoTechnicality`, `autoSummary`). Never read them out, never show them. (constraint 1)
- **"A section ends at the next title."** Six pages of ETHGlobal have titles of the team's own inside the two texts. A section ends at the next known title. (backlog entry 10)
- **"Just look at one ETHGlobal page with the web reader first."** Every request to a site we asked must carry my tool's name and my contact address. Your web reader does not. Use the collector, or ask me to look in my browser. (§5.7)
- **"Save the raw page exactly as it came."** Not the team part: it is cut out before saving. (§5.3)
- **"Put an example from a real page in the test file or the report."** No text from a collected page enters git. (§13.1)
- **"Use the six page groups for Test 1."** They were measured on DoraHacks pages. Form the groups again for each source, before the cases are drawn. (§13.2)
- **"Devpost is public, so a few requests are fine."** Devpost said no in writing. A person may browse it and note links. No program, ever. (§5.6)
- **"The same name in two events is the same project."** A name is a hint. "Seen before" needs the same repository or the same Hedera ID. (§8.4)
- **"Every project gets a full card."** For eight of the twelve events only the winners are public. Those get a winner entry: no LLM rewrite, and no ledger fact unless the page gives an ID. (§4.6)
- **"The tool knows every Hedera hackathon project."** The first line of this project says so, and the data gives less: the projects whose page is still public, and the winners of the rest. Until I choose a new first line (open question Q15), do not repeat "every project" on a new screen or in the pitch without that limit. (§1.4)

## 4. Build order

The order is fixed. The reasons are in §14.

| Phase | Work | Ends when |
|---|---|---|
| A | Setup and four small proofs: the collectors pass their tests on sample files, write to and read from a Hedera topic, one LLM call and one embedding call, the database with vector search | **Gate A** passes, with the live list proof still open until I allow a source |
| B | The thinnest full path: collect, parse, check, store, search. First on invented sample pages, then on 50 real projects from a source I allowed | **Gate B** passes, on real projects only |
| C | All projects of the chosen events: collect, parse, check | Counts are written in the backlog |
| D | LLM fields with quote check, embeddings, search, compare | The search test runs |
| E | Website: search screen and project card | Review layer 1 is done |
| F | Website: check a submission, register on Hedera | A real registration is read back from the ledger |
| G | The tests and my grading; overview and method screens | Result files and the short report exist |
| H | Review layer 1 and layer 2, then fixes | I sign off each screen |
| I | README for judges, Hedera details, demo video, pitch, rebuild from a clean copy | Launch gates pass |

**Gate A and Gate B are gates, not milestones.** Build no designed page until Gate B passes. If I ask you to skip a gate, tell me that it is a gate before you do anything.

- **Gate A:** each of the four proofs works on the real service, or its fallback is chosen and written down. The list proof is the exception: it runs on sample files until I allow a source (constraint 17), and the backlog says that it is still open. (§14.2)
- **Gate B:** from an empty database, one command processes 50 real projects. For three written questions with known answers, the known projects are in the first 10 results, and each result shows facts read from the mirror node. Only a plain debug listing exists. Real projects need a source I allowed. Until then, build and run the same path on invented sample pages, and do not call Gate B passed. (§14.3)

**Gate A on 2026-10-10:** all four proofs passed on the real services for the first scope, the 92 projects with a Hedera prize (backlog entry 10). **I said the same day that Phase A is not done.** The collection was widened to all 658 projects of the Hedera list, and the lists proof was open again until they were read (backlog entry 11).

**Gate A passed on 2026-10-11** for all 658 projects (`proofs/results/20261011T031418Z-lists.json`). On my word of that day, "consider phase A as completed now with the gap of waiting answers from other companies", Phase A was merged into `main` (`115d170`) and tagged `gate-a`. Phase B is built on `phase-b-thin-path` (backlog entry 13). **Phase A is closed for ETHGlobal only.** When DoraHacks or AngelHack says yes, the collecting work of Phase A is taken up again for that site: its terms, its collector on sample pages, my yes for the run, the run, its proof, and its name in the README.

Waiting for a source does not stop the build. The website work of phases E and F may start on sample pages once the path of Gate B runs on them. Say clearly in the backlog which gate is still open and why.

## 5. Launch gates

All must be true before the project is submitted. Do not call the project ready while one is open, and tell me if I ask you to submit past one. When a gate is done, strike it through and write the date and the evidence. Never delete it.

1. ~~A stranger can start the whole project from a clean copy with the commands in the README.~~ Done on 18 October 2026: a clone of `f38aa70` (it holds only the public files), with the README's commands: the install, `.env` from `.env.example` with a password, the database started healthy, the migrations, 1,614 tests passed, `setup_check` named only the secrets of the stranger as missing, and the website answered. Two changes were needed on this laptop only, because the real database runs here: the copy's database had its own Docker project and port. The log is `data/review/2026-10-18-clean-copy.txt`; the copy and its database were removed after. (Struck on 18 October 2026.)
2. ~~The database was deleted and rebuilt from the raw pages, and the counts matched.~~ Done on 18 October 2026: the database was built again from the saved pages into a new, empty database, and the one in use was kept as the reference (`evals/results/20261018T102138Z-rebuild.json`, the steps at the top of `evals/rebuild.py`). 33 of 36 counts are the same, among them every count that the site uses: 826 projects, 1,320 Hedera IDs, every status of the ledger (asked again), the 658 cards of the version in use with 8,909 of 8,931 quotes found again, 826 embeddings made again, and the 2 groups linked across events. The 3 others are one outdated card of the first version of the instructions, rightly refused because its page text changed after it was made. The cards came back from a saved file with no model call (`cards --restore`). (Struck on 18 October 2026.)
3. A registration was written to the Hedera topic and read back from the mirror node, and its link opens on HashScan.
4. ~~The test of the LLM fields ran, I graded it, and the report shows the four numbers with their ranges.~~ Done: I graded projects 1 to 10 and asked the assistant to grade the rest (decision of 15 October 2026, said again on 17 October: "I did 10 projects and told you to complete the rest"). Results `evals/results/20261014T231416Z-test1.json` and `evals/results/20261015T011908Z-test1-card-form-2.json`; the report `evals/test1/report-gemini-3.1-pro.md` shows the four numbers with their ranges, and all four pass marks are met in the second run. (Struck on 17 October 2026.)
5. ~~The search test ran and its result file exists.~~ Done on 14 October 2026: `evals/results/20261014T235346Z-test2.json`. It found 34 of 57 known projects in the first 10 (59.7%), under the pass mark of 80%, and the README says so. (Struck on 16 October 2026.)
6. ~~The check of Hedera IDs ran on the hand-checked pages and its result file exists.~~ Done on 18 October 2026: `evals/results/20261018T185311Z-test3.json`, report `evals/test3/report-2026-10.md`. Found 156 of 156 and status 94.9% meet their marks; added IDs 12.4% does not (mark at most 2%), and the README says so. (Struck on 18 October 2026.)
7. Every screen passed both review layers.
8. No secret is in the repository or its history.
9. The README says plainly what works, what does not, and what already exists elsewhere.
10. The README says in general where the data comes from and which sites gave their consent. A few projects taken from a public page are not listed there. Every card links to the page it comes from. (Added 2026-10-09. Changed by me on 2026-10-10: "what we need is that in general, ETH gave the consent and it's logged [...] if we take a few numbered projects sitting online dont mention them".)
11. The way a site is read was kept, and each rule has a passing test: only named pages, the pause, my contact address in every request, no team member data, the limit of requests, no page text in git. Nothing is made public before I wrote to the site again. (§5.7, added 2026-10-09. On 2026-10-10 I widened the scope for ETHGlobal myself, constraint 18.)
12. The remote repository shows no co-author line in any commit, and no mention of the assistant in the code, the comments, the README or the commit messages. The working notes are in it on purpose since 20 October 2026. (Constraints 19 and 20, added 2026-10-10, changed 2026-10-20.)

## 6. Ask me rather than decide

**What I judge, and what you decide.** I am not a software engineer. I judge whether the tool will be used, how it feels to use, and whether a reason holds. Technical choices are yours: the language, a library, a data shape, a threshold. Decide them, give the need and a source in plain words, and write them in `backlog/decisions.md`. Do not hand me a technical "A or B" question. Ask me about use, about my own time and money, and about the things below.

Ask when a decision is hard to undo, or when somebody other than you pays for a mistake.

- Anything that costs money or uses my credits, the two Google models included since 20 October 2026: my Google Cloud credit is about $15 (constraint 7). Say how much and for what.
- Anything written to a public ledger other than the fixed record, and any change to the keys of the topic (§9.5).
- Making the repository public, inviting somebody to it, or changing its licence.
- Moving a pass mark after it is fixed (§13.6), and removing or changing a test case after a run.
- Adding a website to collect from, or a new way of using one we already read.
- Any sentence in the interface that makes a claim about a project or a team.
- Anything outside this folder.
- Anything where this file and current official documentation disagree.

Everything else that is cheap to undo and stays inside this codebase is yours to decide. Tell me afterwards.

## 7. Settled, do not re-open

These were argued and decided. Do not raise them again unless a test result contradicts them.

- **Two Gemini layers, both on Vertex AI.** I decided on 2026-10-09. The first layer reads and rewrites the project pages into cards with Gemini 3.1 Pro, for the quality of the rewrite. The search uses Gemini 3.8 Flash. The rewrite runs at the thinking level HIGH. The search runs at LOW since 2026-10-16 (my words: "Make ai reasoning for search low", after the measure of 15 October: 7.5 s against 26 s, a third of the cost). The models and the levels are settings in `.env` (`GEMINI_REWRITE_*` and `GEMINI_SEARCH_*`). This replaces my first decision of the same day, "Gemini 3.8 Flash for every call". The calls go on for as long as the tool is used, so one provider that my credits cover is still the choice. Gemini 3.1 Pro is a public preview model: if Google changes or retires it, I decide again.
- **The store is PostgreSQL with pgvector.** SQLite was rejected on 2026-10-09: its only advantage was "no setup". It allows one writer at a time, its vector add-on is young, and it is awkward to host next to a website.
- **Collection is a proof, and it follows each site's terms.** A browser robot and simple requests are used only where the terms allow it or the site said yes in writing. DoraHacks has said neither yet, so nothing automated touches it (constraint 10). Real use would need the sites to give the data themselves. That sentence belongs in the pitch, not in the code.
- **The language is Python,** with pages made on the server. Decided on 2026-10-09 after I asked for a researched choice. On 2026-10-16 I asked again whether a Python-only website can have a good design; the assistant researched it and kept the stack, adding htmx 2.0.11 and a design system of its own (backlog entry 16): the failure was the missing design work, not the language. Only two things re-open it: Gate A fails on the Hedera write, or teams must sign with their own wallet. (§11.5)
- **The repository is private and named `hackathon-memory`.** It is separate from the research folder around it. The licence is Apache 2.0. (§15)
- **No collector runs before my yes for its site.** I decided this on 2026-10-09. Do not argue that a site's rules allow it: ask me. (constraint 17)
- **4hacks is excluded.** Its organiser keeps every submission private, also for a signed-in visitor. Do not build a collector for it. (§5.6)
- **StackUp is excluded for the same reason.** The Hello Future events are covered by winner entries. (§4.6, §5.6)
- **ETHGlobal's showcase is the first source.** ETHGlobal said yes in writing on 2026-10-09, and I said yes the same day. Only the projects with a Hedera prize, inside the promises of §5.7. On 2026-10-10 I learned that the prize pages list no winners (backlog entry 07). The winners are found by a walk through the showcase list with the filter `partners=hedera`, and the collection was done that day: 92 pages (backlog entry 10).
- **No login and no browser robot for ETHGlobal.** The slow, signed request was never refused. The email promised "nothing that needs an account". (backlog entry 10)
- **GitHub's API is allowed.** I said yes on 2026-10-10: "Q17: yeah why not." Public repositories only, one request at a time. (§7.3)
- **The analytics are six blocks on the event overview screen.** I left the choice to the assistant on 2026-10-10. Nothing that predicts, and no share of fewer than 20 projects. (backlog entry 09)
- **The cost of every model call is counted.** Every call goes through `metered_client` of `finops/meter.py`. There are two environments, `test` and `prod`, each with its own budget in `.env`. A price that is not in the price book is never guessed. I left the scope to the assistant on 2026-10-10. (backlog entry 08)
- **The notes and the tools of the work are in git since 2026-10-20.** `CLAUDE.md`, `backlog/` and `docs/` are committed and pushed (constraint 20), each change of the notes in its own `docs(notes)` commit. `backlog/tools/` holds the scripts for a commit: stage, then `sh backlog/tools/test_staged.sh`, then commit.
- **Dar Blockchain is dropped as a source.** I decided on 2026-10-10: it holds no historical submissions. Do not raise it again unless there is proof that it has data.
- **Every Hedera project of ETHGlobal's showcase is collected, and no second email is sent.** I decided on 2026-10-10 (constraint 18). Do not ask me again to write to ETHGlobal about the scope.
- **The public notes are general.** I decided on 2026-10-10 (launch gate 10, section 3 of this file).
- **A 429 is a speed limit.** I decided on 2026-10-11 (constraint 10).
- **The winners page of the Africa hackathon, `hedera-hackathon.hashgraph.swiss`, is a source.** I said yes on 2026-10-10. It is one page with no rules file and no terms. Its winners become winner entries, and no program follows its links to DoraHacks.
- **Devpost is closed to programs.** It said no on 2026-10-09. Hedera21 and Hedera22 get winner entries, and I may add Devpost links by hand. (§4.6)
- **The winners page of Hedera x AI on hol.org is read by hand,** with no request. It is one page. No program is sent to that site. (§4.6)
- **Two kinds of entry:** a full card where the submission page is public, a winner entry where only the organiser's announcement is left. I left this choice to the assistant on 2026-10-09. (§4.6)
- **No big data tools.** I aim at production level after the event, and that changes the habits, not the tools. Build with the habits of §11.6 from the first table.
- **The topic has no admin key and one submit key.** (§9.5)
- **The pass marks are fixed.** (§13.6)
- **The demo runs on my laptop and in a video.** Nothing is published online for now.
- **Organisers stay users of the tool,** even though nobody asked them.
- **Fields have three labels,** not "stated or empty". An empty field is wrong when the page has the information without a title for it.
- **The parser copies titled sections.** The LLM gives structure and reads what has no title.
- **Ollama and other local LLMs are not used.** The graphics card has 4 GB and the data is public.

## 8. Working style

- Commits and branches follow section 9 of this file. In short: one logical change per commit, every commit works, and the backlog is updated in the same working session as the work it describes, and committed in its own `docs(notes)` commit (constraint 20).
- Before each commit: `git add` the files of one change, then `sh backlog/tools/test_staged.sh` (the lint and all the tests on exactly what is staged), then commit.
- End every phase with three lines: what changed, what you could not verify, what you would clean up next.
- When you say you will check or measure something, it must leave a file behind: a test case, a script, a dated result. Your own reasoning is not a measurement.
- A phase is done when I can see it or run it, not when the code exists.
- Explain in the chat in plain text. Leave out features for "later" unless I ask.
- **Give me the context with everything you tell me or ask me, in easy language.** I am not a native English speaker, and I do not follow the work while it runs: I let you do the job and come back when you have finished. So for every piece of information, question or instruction: say what it is about and why the tool needs it, what exactly I should do, step by step, with an example of the answer, and what happens if I do nothing. Never give me a bare label such as "Q30" or the name of a file or a rule without one plain sentence that says what it is. (Decision, 2026-10-11: "whenever give me info or insturctions give me the context of it and explain everything in easy language".)
- Admit a mistake first, then fix it, then add a line to `backlog/lessons.md`.
- **Consider a refactor every time you touch code.** Look at the code around the change first: copied code, a function that does two jobs, a name that says the wrong thing, a module that has grown too big. If a refactor makes the change simpler or safer, do it first, in its own commit, with the behaviour unchanged and the tests green. Say in one line what you changed, or why you left it. Do not reshape code that you are not touching, and never mix a refactor with new behaviour in one commit. (Decision, 2026-10-10.)

## 9. Commits and branches

The history in git is a register. I search it when something breaks. Three questions must be quick to answer: which commit changed this, why, and can it be undone alone. The reasons are in §20. My skill `commit-splitting-cost-ceiling` holds the long version of 9.2.

### 9.1 One logical change per commit

- One commit holds one change that I can name in one line and undo alone.
- These belong together in the same commit: the code of the change, its tests, its sample files and its database script. The backlog and the other notes get their own commits (`docs(notes)`), so that a change of the code can be undone alone (constraint 20).
- These always get their own commit:

| Own commit | Because |
|---|---|
| A refactor: the code is reshaped and the behaviour stays | Inside a feature it hides the few lines that matter |
| Formatting and reordering | It makes the real change unreadable |
| Files written by a tool: lock files, generated code | To see what a person decided and what a tool wrote |
| A fix noticed in passing | So that it can be undone alone |

### 9.2 Do not overpay for a split

| Where the two changes are | What to do |
|---|---|
| In different files | Split. It costs two commands. |
| In the same file, in separate blocks | Split, by staging the blocks. |
| In the same file, mixed line by line | One commit. The message names both changes with numbers and says why they are together. |

- Never edit the content of a file only to make a split possible. Never rebuild the history with a script, unless I ask.
- When a refactor and a feature would mix: do the refactor first, commit it, then build the feature on top.

### 9.3 Every commit works

Before each commit the tests pass. For documents, the checks of section marks and links pass. Never commit a state that was not run. A commit that never ran is a false save point: the search for a bug stops on it for the wrong reason.

### 9.4 The message

```text
type(scope): what changes, as an order, in under 60 characters

Why the change is needed, and why this way. What was left out.
One line with the result of the tests.

```

- **type**, one of: `feat` (new behaviour), `fix` (a wrong behaviour is corrected), `refactor`, `test`, `docs`, `build` (Docker, dependencies), `ci`, `perf`, `chore`.
- **scope**, one of: `collect`, `parse`, `read`, `check`, `search`, `register`, `web`, `db`, `evals`, `finops`, `infra`, `readme`, `notes`. Use `pipeline` only when a change truly crosses the whole path.
- The first line is an order to the code: "add", "cut", "stop". Not "added" and not "adds". No full stop at the end.
- The body is simple English. It says why. The diff already shows what.
- No `Refs:` line (it would point at notes that are not in the repository) and no `Co-Authored-By` line (constraint 19). A commit that closes a proof of a gate carries `Gate: A`.
- A change that breaks something older puts `!` after the scope, and the body says what breaks.

Examples:

```text
feat(collect): add the ETHGlobal collector with its request limit
fix(parse): stop reading version numbers as Hedera IDs
refactor(check): move the proof rule into one function
test(evals): add planted wrong cards to Test 1
docs(readme): add the Hedera details
```

### 9.5 Branches and tags

- `main` holds only what I have seen: the documents, and each phase after I said it is done.
- Each phase is built on its own branch: `phase-a-proofs`, `phase-b-thin-path`, `phase-c-all-projects`, and so on.
- When I say a phase is done, its branch is merged into `main` with a merge commit and is never squashed: `merge: phase A, Gate A passed`. Then `git log --first-parent main` reads as one line per phase, and every small commit stays inside it.
- A tag with a note marks each gate and each finished phase: `gate-a`, `gate-b`, `phase-c`. The day of submission gets `submitted`.
- Pushed history is never rewritten: no forced push, and no change to a commit that was pushed. A mistake is corrected by a new commit or by `git revert`.
- **One exception, allowed by me on 2026-10-10:** a single rewrite of the pushed history, to remove the co-author lines and to take the working notes out of the remote (constraints 19 and 20). It was done on 2026-10-10 (backlog entry 08). The old history is kept in `.local-backup/old-history-20261010.bundle`. This rule holds again with no exception.

### 9.6 What never enters a commit

Secrets. The `data/` folder. Any text taken from a collected page. Anything from my personal notes or from my other projects. The vendored copy of git-filter-repo (`backlog/tools/rewrite/filter_repo_pkg/`). Since 20 October 2026 the rules file, the backlog and the other working notes are committed (constraint 20).

### 9.7 What you may do without asking

- Commit on the phase branch when a chunk is finished and its tests pass.
- Push the phase branch at the end of each block of work, so that nothing lives only on my laptop.

Ask me before: a merge into `main`, a tag for a gate, a revert of a commit that is already on `main`, and the removal of a branch.

### 9.8 Finding things later

| I want to know | Command |
|---|---|
| The phases, one line each | `git log --oneline --first-parent main` |
| Everything that touched one part | `git log --oneline --grep "(parse)"` |
| All fixes | `git log --oneline --grep "^fix"` |
| What changed between two gates | `git log --oneline gate-a..gate-b` |
| Which commit broke it | `git bisect start`, then `git bisect bad` and `git bisect good gate-a` |
| Why this line is here | `git blame <file>`, then `git show <commit>` |

Each backlog entry lists the commits of its step by their short numbers. So the way goes in both directions: from the story to the commit, and from the commit to the story.

The first five commits on `main` are older than this section and keep their messages.
