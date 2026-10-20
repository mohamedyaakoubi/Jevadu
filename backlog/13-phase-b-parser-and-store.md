# 13. Phase B: the parser, the store and the check on the ledger

- **Date:** 11 October 2026
- **Who:** the owner (Mohamed Yaakoubi), with Claude Code
- **Status:** in progress on `phase-b-thin-path`. Built: the parser, the store, the table of runs, the parse step, the ledger check, the proof rule, the ends of events typed by hand. Not built yet: the Hedera IDs in the README of the code, the facts of the code, the embeddings and the search, Gate B.

This file stays on the laptop (`CLAUDE.md`, hard constraint 20). It is never committed.

## Goal

Gate B (blueprint §14.3): from an empty database, one command processes 50 real projects through collect, parse, check and store. Three written questions find their known projects in the first 10 results, each with facts read from the mirror node.

## What was read first, and when

All on 11 October 2026.

| What | Source |
|---|---|
| BeautifulSoup 4.15.0 leaves a comment out of `get_text()` | The installed source, `Tag._all_strings` |
| The shape of an ID with a check word of five letters | hiero-sdk-python 0.2.10, `utils/entity_id_helper.py`, `ID_REGEX` |
| The first number that a user can own is 1001 | The setting `firstUserEntity`, default 1001, in `HederaConfig.java` of hiero-ledger/hiero-consensus-node (the raw file on GitHub) |
| The public mirror node allows 50 requests a second for one address | docs.hedera.com, the page of the REST API |
| The test network was last emptied on 1 February 2024, and later dates were skipped | A search summary of docs.hedera.com's page on the test network. Not read in full. |
| What the mirror node answers for each kind of thing | Real answers of the test network: `tools/mirror/probe_shapes.py`, `tools/mirror/probe_account_activity.py` |

Two things that only real answers showed. A list of another kind of thing comes back empty with the answer 200, so the thing itself must be asked first. The transactions of an account are searched 60 days at a time, and an empty answer carries a link to the 60 days before.

## What the saved pages are like

Script counts on the 658 saved pages, with `tools/ethglobal/inspect_shape.py`, `inspect_prize_lines.py`, `inspect_prize_text.py`, `parse_all.py`, `check_blocks.py` and `judging_times.py`. Planning numbers, not a test (hard constraint 6).

- The header holds the name (h1), the short line (the p after it), and up to two links: "Source Code" and "Live Demo". The page data holds the same name and short line on every page.
- A prize line is the sponsor, a dash, and the name of the prize. A prize of the kind "tier" adds the place.
- 653 pages link to their code on GitHub, 510 to a demo, 615 have a video.
- 81 pages give at least one Hedera ID in their texts or links: 134 IDs, 118 different, 5 of them on more than one page.
- The two texts of a page together: median 3,176 characters, the longest 44,218, and 2.67 million in all.
- The judging timer in the page data: for ten weekend events, all the judging falls on the Sunday, two days after the Friday start. Four events do not settle their end: Singapore 2024 and ETHOnline 2024 show no judging, ETHOnline 2025 shows judging spread over six months, ETHOnline 2026 shows one day of judging ten days after the start.

## What was built

| Commit | What |
|---|---|
| `f54ab06` | refactor: the prize lines move into a new package, `parse` |
| `11e92f8` | the text of a page as blocks, word for word |
| `e90a463` | Hedera IDs with their network and kind |
| `2a9cc92` | refactor: the reader of the page data moves to `parse` |
| `06a3d79` | a project page of ETHGlobal into its facts |
| `7a9600d` | six tables for the parsed projects (migration 0003) |
| `7881442` | the table of runs (migration 0004) |
| `9934656` | refactor: the store lists its saved pages |
| `3e98e5a` | the parse step: `python -m hackathon_memory.pipeline parse` |
| `468439c` | the mirror node client asks what happened on an ID |
| `6a006b5` | the ledger facts of an ID |
| `e3e0fc9` | the proof rule |
| `1244495` | the tables of the ledger facts and of the result of the rule (migration 0005) |
| `be2f37d` | test: the stand-in for the mirror node is shared |
| `13ddb14` | fix: the connection text stays out of a failed test |
| `c148c58` | the one more question of the rule: was the thing used inside a time? |
| `6e6147d` | the check step: `python -m hackathon_memory.pipeline check` |
| `2dbe5b2` | test: two tests no longer name the next version of the parser |
| `59d970d` | fix: the words after a list inside an item stay in their place |
| `475bb68` | merge of `main` after Gate A |
| `d276f48` | the file of the ends of events |
| `59d2423` | the parse step writes the ends of events |
| `dfc9ab8` | docs: `DESIGN.md` sections 6.1, 6.5, 7.2, 11.2 and 13.3 follow blueprint 0.14 |
| `35ae279` | the parser hides words about people in the short line and the two texts (Q31) |
| `90bbbc8` | the store can take personal data out of a saved page, with the reason written next to it |
| `2d747b3` | refactor: the list of profile sites gets a name |
| `daccc03` | fix: a profile link behind another first part ("uk.linkedin.com") is hidden too |
| `bc6021a` | a link of the header to a profile site is kept without its address (migration 0006) |
| `8f2a4bd` | refactor: the hiding runs from one list of rules |
| `808fb48` | a link to an account page on GitHub (one name only) is hidden |
| `41c4e25` | docs: `DESIGN.md` 5.3, 5.4, 6.1 and two rows of the README describe the hiding |
| `5ee2b7e` | refactor: the polite client judges an answer in one method |
| `a30bb42` | fix: an email address is hidden also inside code |
| `2af21bd` | the photo of an account and a handle inside a link are hidden |
| `e766664` | a README is cleaned before it is saved (`parse/markdown.py`) |
| `50654d4` | refactor: the raw answer of a site has a public name |
| `a0e8936` | the polite client for GitHub's API, the switch `COLLECT_GITHUB` |
| `c899b05` | the store keeps facts of an answer next to a saved page |
| `778a433` | refactor: the reader of an API message has a public name |
| `4110e96` | each README is asked for once and saved without people |
| `c304a4c` | the table of repositories and the IDs of a README (migration 0007) |
| `dbb0e44` | the step `python -m hackathon_memory.pipeline readmes` |
| `ce899f2` | fix: a handle in a link with no scheme is hidden |
| `1badce0` | docs: the README step in `DESIGN.md` 5.3, 5.4, 7.3 and the README |
| `c2fe3c6` | gemini-embedding-2 for the search, the setting `GEMINI_EMBEDDING_MODEL` |
| `480fb8c` | the step `embed` and the embeddings (migration 0008) |
| `0110799` | the search: `python -m hackathon_memory.search` |
| `6a46c1c` | refactor: one step runs in a function of its own |
| `23f4120` | the step `all`: the whole path with one command |
| `cbbe392` | fix: BM25 for the words, the fusion over the top of each list |
| `ef6a6cd` | the proof of Gate B, `python -m proofs.gate_b` |
| `2dec175` | docs: the search and Gate B in `DESIGN.md` 8.1, 8.2, 11.3 and the README |
| `cb60fcd` | refactor: one shared loop asks GitHub once for each repository |
| `c06862d` | the facts of each repository, kept to a fixed list of fields (no account) |
| `35a36f2` | refactor: linking projects to repositories in a function |
| `e3546bf` | the step `python -m hackathon_memory.pipeline code` (migration 0009) |
| `b7cdede` | the life rule (`check/life.py`) |
| `27e2001` | the listing shows the life and the dates of the code |

1023 tests pass. CI is green on `41c4e25` (checked 11 October 2026). The parser is at `ethglobal-page-6`.

`collect/ethglobal.py` still has about 800 lines. Only the prize lines left it. The rest of the split waits until the file is touched again.

## Results on the real data

| Step | What happened |
|---|---|
| parse | 658 pages read, none refused. The parser and the walk agree on the prize of every project: 92 with a Hedera prize, 81 with another sponsor's prize only, 485 with none. Runs 2 and 4 in the table of runs. |
| check | 186 questions about IDs (an ID with no network is asked on both networks), 895 requests to the public mirror node, no error. A second run asked 5 new questions: the table of answers works. Runs 3 and 5. |
| proof rule | After the ends of ten events: 19 projects with proof found, 60 that wait for the end of their event, 1 found but empty, 1 found as another kind of thing, 577 with no ID given. |

What the counts suggest, for planning only: of the 92 winners of a Hedera prize, only 7 give an ID on their page, and of the 485 projects with no prize, 68 do. The IDs in the README of the code may change this a lot.

## The README of the code, the ledger check, the embeddings and the search (11 and 12 October 2026)

Read first, on 11 October 2026: GitHub's pages on rate limits, best practices, the README endpoint and the API versions; Google's embeddings page, price page and the model page of gemini-embedding-2 on Vertex AI; the installed google-genai 2.29.0 (`embed_content`, `t_is_vertex_embed_content_model`) and pgvector 0.5.1 (`Vector.to_list`). On 12 October: PostgreSQL's page on ranking (12.3.3) and Elasticsearch's page on reciprocal rank fusion. Three real requests to GitHub (`tools/github/probe_readme.py`) showed the shapes of 200, 301 and 404 before the client was written.

Results of the runs, for planning (they come from runs, not from a test):

| Run | What happened |
|---|---|
| readmes, run 14 | 5 READMEs, to try the live path. |
| readmes, run 15 | 651 repositories of 653 projects. 646 asked, none failed, no refusal, no rate limit; 676 requests to GitHub in all. 561 READMEs found, 90 repositories without one. Taken out before saving: 53 parts about the team (438 lines), 93 words of people, and no Hedera ID in a cut part. 259 projects have IDs in their README (963 IDs). A second pass of the rules over the 561 saved READMEs changes nothing (`tools/github/rules_again_on_saved_readmes.py`). |
| check, run 16 | 842 new answers of the mirror node, 3,694 requests, no error. Projects: 76 proof found (before: 19), 200 found but waiting for the end of their event (before: 60), 2 dates do not fit, 4 another kind, 3 not found, 373 no ID given (before: 577). |
| embed, runs 18 and 19 | 658 embeddings, 588,194 tokens, about 12 cents. One text was longer than the model reads. |
| code, runs 20 and 21 | 651 repositories, 651 asked, none failed, no refusal; 1,258 requests to GitHub in all by then. 581 found, 70 gone or private, 0 blocked; 2 archived, 12 forks, 22 moved or renamed. The account was dropped from all 581 answers; no email, profile link or photo in any saved GitHub file (`tools/github/people_in_saved_readmes.py`). |
| life rule, 12 October | `tools/life_counts.py`: 313 active, 20 quiet, 150 stopped, 175 unknown (107 because the end of their event is not typed in, 68 with nothing to look at). |

The first real search (an idea in my own words, `--numbers-only`) showed that the closest project in meaning came seventh, then not in the first ten. Two causes, fixed in `cbbe392`: PostgreSQL's ranking has no global information (common words decided), and the fusion over 50 of each list favoured the middle of both lists. After the fix, the first places alternate between the best of each list.

A weakness of the life rule as written (blueprint §7.4), seen in the counts: a project whose event ended less than 90 days ago is "active" because of the work during the event itself. Asked as Q33, because the status is a claim about a project shown to users.

Gate B waits for the owner's three questions. The tool `tools/gate_b_candidates.py` wrote `data/by-hand/gate-b-candidates.txt` (the 76 projects with proof found, with name, short line, event and link) and an empty `data/by-hand/gate-b-questions.txt` with an example in comments.

## Gate B part 1, and the life rule (12 October 2026, afternoon)

**The owner's answers.** Blind ideas for Gate B ("if i read them my brain will unconsciously get biased to describing them"), the four ends of events, and a reason behind every number of the life rule. Then, about the life rule: "you are right about the 30 days stopped flag, keep it that way, my 15 days was a confusion about the inverse of it."

**Gate B, part 1** (`python -m proofs.gate_b`, result written at 12:14 UTC): from an empty database, one command took the 658 projects through parse, readmes, code, check and embed. Check: 1,008 new answers of the mirror node, 4,629 requests. Embed: 658 embeddings, 589,959 tokens, about 12 cents; one text cut. Projects: 272 proof found, 6 dates do not fit, 4 another kind, 3 not found, 373 no ID given. Three ideas, ten results each: 5 of the 30 show ledger facts, 25 say that no ID is given. Passed: `proofs/results/20261012T121412Z-gate_b.json`, committed in `9f9ce28`. The results wait for the owner's marks in `data/by-hand/gate-b-results.txt`, and the pass rule waits for a yes (Q34). The `life:` lines of that file were written with the old rule; the owner was told not to use them for the marks.

**The life rule** (Q33 answered): a sign of life is a sign later than 30 days after the last day; "too early to tell" while the event ended less than 90 days ago; unknown with no known end. `f2e26fd` (code and tests, 1,234 passed), `a1c15f3` (DESIGN 7.4 and the README). On the real data (`tools/life_rule_before_after.py`, its output `tools/results-20261012-life-rule-before-after.txt`; counts for planning): the old rule called 312 of 672 projects active, the new rule calls 26 active and 286 too early to tell. The other statuses did not change: 33 quiet, 245 stopped, 82 unknown.

**Phase B into Phase C:** merge `bc38133`, 1,245 tests passed. Both branches are pushed.

## Gate B part 2: the judgement, and a run that met a change of Wi-Fi (12 October 2026, evening)

**The owner's words.** "I know none of my ideas were hedera related, I wanted to see how'd the search behave that way, after all expect someone's idea to could be actually inexistant, anyway you can test the hedera closeness yourself." "I ranked using N/A as has even very minor utility even though it's unrelated to the idea [...] And No as totally no utility and unreletaed, you can defiently rejudge if you disagree with me." "no need to give me more projects after my ranking, the judgement is yours but always mark a methodology behind it." "the searching system feels like it did an effort even though it didnt really have so that's whats another explanation of N/A." "Always if you agree with me ofcourse, never take my words granted, am not a fault tolerance source." "the network error is my fault i switched wifi, and thats a reason to make yo uthink about possible crashes/throttles/rate limits."

**The method** (the decisions of 12 October): the owner's scale of three marks; the owner's three ideas say "expect: none" and need only their marks; three Hedera ideas, written blind by the assistant at 16:59 UTC before any search for them and before any result was read (`data/by-hand/gate-b-hedera-ideas.txt`), need at least one "yes" in their first 10; every result is marked; nothing beyond the first 10. The proof reads both files: `ba749f4` (code), `9be52e3` (`DESIGN.md` 14.3, README). The owner's file got only the three lines "expect: none"; the file as the owner marked it is kept as `data/by-hand/gate-b-results.as-marked.txt`.

**The owner's marks of the owner's ideas.** Idea 1: 3 n/a, 7 no. Idea 2: 6 n/a, 4 no. Idea 3: 4 n/a, 6 no. No yes. The first result was "n/a" for all three, and the mean place of an "n/a" was above the mean place of a "no" each time (2.0 and 7.0; 4.5 and 7.0; 3.5 and 6.8). That supports "the searching system feels like it did an effort", on a small sample (counts for planning).

**The assistant's reading of the owner's marks** (the owner asked for it): 24 of 30 the same. Six differ, all between "n/a" and "no", and none would be "yes". The owner's marks stay the record; this reading is only here.

- Idea 2, place 6: owner n/a, assistant no. The project keeps evidence safe; it does not read or rebuild a video.
- Idea 2, place 9: owner no, assistant n/a. AI agents that make art and videos: making video is near guessing the next scene.
- Idea 3, place 6: owner n/a, assistant no. Savings and loans, not the cost of cloud computing.
- Idea 3, place 7: owner no, assistant n/a. A person approves an agent's work and the verdict is signed on Hedera: the approval and the attestation steps of the idea.
- Idea 3, place 9: owner no, assistant n/a. Replayable measurements of what a swap really costs: the measurement step.
- Idea 3, place 10: owner no, assistant n/a. One approval funds a budget that the agent cannot pass: approval and a spending limit.

**The Hedera ideas.** Part 1 ran again from an empty database for them (17:57 to 18:31 UTC): passed, `proofs/results/20261012T175716Z-gate_b.json`. Marks, each with a reason on a "why:" line, in `data/by-hand/gate-b-hedera-results.txt`. Idea 1 (agents that pay other agents in HBAR for data): 8 yes, 2 n/a. Idea 2 (a market where companies buy and retire carbon credits as tokens): 3 yes, 5 n/a, 2 no. Idea 3 (concert tickets as NFTs with a cap on the resale price): 1 yes, 6 n/a, 3 no. The first "yes" at place 1 each time. The only "yes" of idea 3 was checked against its own text: Hedera NFT tickets, resale with royalties, a check that a human resells; no price cap, but a big part of the idea.

**Part 2** (`python -m proofs.gate_b --marks gate-b-results.txt gate-b-hedera-results.txt`): passed, `proofs/results/20261012T183221Z-gate_b_marks.json`. Commit `224cc0b` with `Gate: B`, pushed. Merged into Phase C: `6957447`, 1,269 tests. The merge into `main` and the tag `gate-b` wait for the owner's yes (`CLAUDE.md` section 9.7).

**The crash.** The first run for the Hedera ideas (17:10 UTC) stopped at 17:42 in the embed step: the owner changed Wi-Fi, Google's server closed a connection without an answer (`httpx.RemoteProtocolError`), and the step caught only Google's error answers. No database was left behind. The review of every client that talks to the network:

| Client | A short loss of network | "Too many requests" | A server error | Fixed |
|---|---|---|---|---|
| Google (google-genai 2.29.0) | The library tries again only after a timeout or a connection that could not be made. Now: 5, 15, 45 seconds, then again; the embed step counts a failure as a problem and stops after 3 in a row | The library tries again (our options) | The same | `6ca8661` |
| Mirror node | Each failure was at once "not checked". Now: 5, 15, 45 seconds, then again | Now the same pauses, or the "Retry-After" up to five minutes | Now the same pauses | `76d5ee6` |
| The polite client (ETHGlobal, GitHub, the Africa page) | A failed page, a stop after five in a row: on purpose for the sites; a new run asks only for what is missing | The cooldown of one hour, then five times slower | A failed page | Unchanged |
| The pipeline's main | | | | Stops with a plain message on "Google is away", "the mirror node is away" and the budget |

**A finding for the search screen and Test 2.** When nothing in the data is close to an idea, the listing still shows ten results, and nothing tells the reader that none is close. On the owner's ideas the results of some use came first, but a builder cannot tell "close" from "the best of nothing". The search screen (S1) and the test of the search (blueprint §13.3) must deal with it. A sentence that tells a builder "nothing close" is a claim about the data, so the owner chooses its words (`CLAUDE.md` section 6).

## What went wrong

1. **A password in the log of this session.** At about 02:17 UTC two new tests failed, and pytest printed the values that they had been given. One of them was the connection text of a test database, with the password of the local PostgreSQL. The cause is fixed in `13ddb14`: the fixtures give a text that prints as a short note, and a test checks what pytest would print. The assistant fixed the cause at once but told the owner only at the end of the turn. It should have stopped and told them first. Open question Q32 asks them whether to change the password.
2. **The local database refused migration 0003,** because migration 0001 had been edited on 10 October: one word of a comment. The kept copy of the old history proved that only the comment had changed. Fixed on this laptop with `tools/accept_0001_comment_change.py`. A lesson is written.
3. **The blocks changed the order of words** where an item of a list holds a list and then more words. The check of every letter on all saved pages found it on one page. Fixed in `59d970d`. The parser's version word changed, so the parse step read every page again.
4. **A pattern for words with "@" stepped back past a slash again,** in a new local tool (`tools/ethglobal/where_people_words.py`). It was the mistake of the lesson of 10 October. It counted 389 words where 23 were real. Fixed in the tool before any number was used.
5. **The laptop slept** for about eleven hours during the turn, between 03:14 and 14:05 UTC. No run was going on, and nothing was lost.

## Found on the pages: words about people inside the teams' own texts

ETHGlobal shows no team block to a visitor who is not signed in, and the team cut found nothing on any page. But the teams' own texts hold a few words about people:

- 23 words that start with "@" stand inside the two texts, on 13 pages, outside code. Some may be the handles of people. The parser copies the two texts, so they are in the table `sections`.
- 1 page holds an address at a public mail service, most likely of a person, in its page data. It is not in the visible page, and the parser does not copy it. It is only in the saved file.
- 4 "Live Demo" links go to Telegram: bots of the projects, not people.

The promise to ETHGlobal is "no names, photos or profiles of team members", and hard constraint 11 says "no team member names, emails or photos". Open question Q31 asked the owner what to do.

**The owner's answer, 11 October 2026: "Q31 if its people then hide them".** What was done:

- The parser hides, in the short line, in the two texts and in the words of the header links: a word that starts with "@" (not a package such as "@scope/package", and nothing inside code), an email address, a link to a profile on a social site (also behind another first part, such as "uk.linkedin.com"), and a link to GitHub with one name only. `parse/people.py`.
- A link of the header that leads to such a site is kept without its address: the row keeps its kind and the site (`links.hidden_on`, migration 0006). A card will send the reader to the page.
- The one email address in the data of one saved page was cut out with `RawStore.remove_text`, on 11 October 2026 at 15:52 UTC, by the local tool `tools/ethglobal/cut_address_from_saved_pages.py --cut`. The parser read the page the same way before and after. The reason and the old fingerprint are in the small file next to the page. Email-like strings left in the saved pages: 0.
- Result on the real data, run 10 (parse, 11 October 2026): 29 words and links hidden. Five of them are demo links: 4 to Telegram (3 bots by their names, 1 not clear) and 1 to an account page on GitHub. Checked afterwards with `tools/ethglobal/people_in_stored_links.py`, `profile_links_left.py`, `people_left_in_texts.py` and `shape_of_github_links.py`: no text, no short line, no name and no stored link holds a handle, an address or a profile link. Counts only, for planning.
- What stays, and why: the account name inside a link to a repository (653 code links, and the demo links to a repository or to a page at github.io). Hard constraint 11 keeps it: "A repository owner's name is kept only as part of the repository link."
- The run 11 of the check gave the same statuses as before: the hiding took no ID away.

## What this does not prove

- That the parser reads the meaning of a text right. It copies. Nobody graded a block.
- That an ID belongs to the team that names it.
- That the ten ends taken from the days of the judging are the ends that the pages of the events give. They come from the data of the projects' pages.
- That 30 and 14 days are the right numbers for the window. Test 3 says that.

## Next

1. The owner: a yes for the merge of Phase B into `main` (a merge commit, never squashed) and the tag `gate-b`.
2. Phase C goes on in [14](14-phase-c-all-projects.md).
