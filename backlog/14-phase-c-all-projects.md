# 14. Phase C: all projects of the chosen events

Started on 11 October 2026 on `phase-c-all-projects`, from `phase-b-thin-path`.

## Goal

All projects of the chosen events: collect, parse, check. Phase C ends when the counts are written here (`CLAUDE.md` section 4).

## Done

- **The winner entries copied by hand.** Six of Hedera x AI (`data/by-hand/hol.org/`) and eight of Hedera18 from the archive copy (`data/by-hand/web.archive.org/`), read by `parse/winner_entries.py`. Commits `d36ffb2` (refactor: the kind of entry goes with a parsed page), `a908a9f` (read the winner entries), `435d5da` (count the words hidden in winner entries). Parse run 23 and check run 24 on the main database: 672 projects.
- **Phase B merged in** twice: `bc38133` (12 October, afternoon) and `6957447` (12 October, evening, after Gate B), 1,269 tests.
- **Embed run 25** (12 October, evening): 14 new embeddings (819 tokens), the 658 others the same as before. All 672 projects can be searched.

## The look at the Africa winners page (12 October 2026, evening)

Built first: the skeleton printer now shows the keys of the data that a Next.js page pushes, with their counts and never a value; a key seen once is not shown, and the keys of a map of records are not counted (`f48e10f`). Then the small collector `collect/africa_winners.py` with its look (`37210e8`): the page and its robots.txt only, its own switch `COLLECT_AFRICA_WINNERS` (turned on in `.env` on the owner's yes of 10 October), its own count of requests with a limit of 10, a refusal remembered, nothing saved. 1,283 tests.

The live look, 12 October about 19:00 UTC: 2 signed requests (robots.txt: 404; the page: 200, 39,518 bytes), nothing saved, no address in the output. What its shape shows:

- The winners stand in the HTML, in `section#winners`. Six track tabs (`track-tab-cross`, `-onchain`, `-dlt`, `-immersive`, `-ai`, `-special`), each with a count of one digit.
- **Only the first track is in the HTML**: one panel with 5 winner cards. Each card is a link to DoraHacks with a place (a short line above the title), the project's name (`h3`), a text of 140 to 225 letters and a logo. The other five tracks are not in the page: its own scripts show them when a tab is clicked. The data that the scripts push (5,954 characters) holds only keys of the page's layout, no winners.
- No list of team members on a card. The page has two forms for a waiting list, which ask a visitor for an email; nothing is ever sent to them.

So the page alone gives 5 winners of 6 tracks. Q35 asks the owner how to get the others.

## The read of the Africa winners (12 October 2026, late evening)

**The owner's answer to Q35: "option 1".** The collector may read the script files that the page itself loads from its own site, each once, at most five.

Built: a reader of data written as JavaScript (`parse/jsdata.py`, `32e42f5`), which reads literals only and runs nothing; the read step of the collector (`0f85e57`), which stops at the first script file with more winner links than the page, and empties the literal value of every key about people and cuts every email address before saving; a lenient read that passes over code inside a record (`8ef4fc7`), because each winner's logo is a picture that the script imports (`logo:H.silsilat`); a refactor (`4aaf732`) so that the records of the script and of the files copied by hand become winner entries the same way; the reader of the Africa winners and its place in the parse step (`bda4646`). 1,310 tests.

The live read (12 October, about 22:00 UTC, `--read`): robots.txt (404), the page, script file 1 (no winner link), script file 2 (19 winner links, more than the 5 of the page): saved next to the page. Nothing was cut: no key about people and no email address. 6 of the 10 requests of the site used in all; three script files were never asked for. The switch `COLLECT_AFRICA_WINNERS` is off again: the page is saved and nothing more is read.

What the script holds (seen with every string masked): a list of six tracks (`{id, label}`), the description of each track, and a map from each track to its winners (`{title, logo, buidlUrl, description}`); one record has `fallbackLogo` in place of `logo`. The Cross-Track repeats five winners of the other tracks; the page gives no place inside a track. Each winning project is one winner entry, its own track first ("On-Chain Finance and Cross-Track"), with the link to its DoraHacks page for a person to open. The event is "Hedera Africa Hackathon 2025" (the page's title says "Hedera Africa Hackathon Winners"; the year comes from the announcement of the winners, `DESIGN.md` 18.2).

**A mistake on the way** (`lessons.md`): a local tool that was meant to mask the strings of the saved script started its window inside a string, and printed some project names and descriptions into the session. Public texts of the page, no person. The tool now masks the whole file first.

Runs on the main database: parse 26 (19 new winner entries, 33 in all), check 27 (no new id: none of the 19 descriptions gives one), embed 28 (19 embeddings, 932 tokens).

| Track | Winners |
|---|---|
| DLT for Operations | 5 (one also in the Cross-Track) |
| On-Chain Finance | 5 (one also in the Cross-Track) |
| AI & DePIN | 4 (two also in the Cross-Track) |
| Immersive Experiences | 4 (one also in the Cross-Track) |
| Special Prize | 1 |

## The counts of Phase C so far (12 October 2026)

| Source | Projects | Kind |
|---|---|---|
| ETHGlobal's showcase, every project that it ties to Hedera | 658 | full cards |
| The winners page of the Africa hackathon 2025 | 19 | winner entries |
| The winners of Hedera18, from the archive copy, copied by hand | 8 | winner entries |
| The winners of Hedera x AI, from hol.org, copied by hand | 6 | winner entries |
| **All** | **691** | 691 with an embedding |

Proof statuses (check run 27): 272 proof found, 6 dates do not fit, 4 another kind, 3 not found, 406 no id given. Counts of runs, for planning.

## Hedera's own winner posts (night of 12 to 13 October 2026)

The owner: "Give me the Africa link" (https://hedera-hackathon.hashgraph.swiss/) and "Continue with your work". Then a screenshot of the Africa page: its six tabs show 5, 5, 5, 4, 4 and 1 winners, as read; the five of the Cross-Track are the five in the database with "and Cross-Track". The owner's point: each card leads to DoraHacks, which has not said yes; if DoraHacks says yes one day, its pages of these projects must not become second cards (decisions of 13 October).

Built, in order: a refactor that puts what the small collectors share in `collect/small_site.py` (`187aa87`); the look at Hedera's posts (`2f5ebdc`); their read, which cuts the lines that list a team, the meta tag of the author and the "Person" of the structured data before saving (`8458dcc`); two fixes of the people cut (`0c41af9`: "Team Member" in the singular and other labels; `c3c9790`: the signature under a quote); the reader of the winners (`2710ea7`). 1,347 tests.

The live requests to hedera.com (the owner's yes of 9 October; terms read on 9 October): the look (robots.txt, 184 bytes, obeyed; the post of Hedera20, 226,550 bytes, a WordPress page, no line about people found by the first pattern); the read of the nine posts, each once. Each post sends the request on to its address with a "/" at the end, so each cost two requests: 22 of the 25 of the site in all. The switch `COLLECT_HEDERA_POSTS` is off again. If the posts are ever read again, their addresses should end with "/".

Cut before or after saving: the author (meta tag and "Person") in all nine; "Team members" lines, 4 in Beyond Blockchain 2023 and 2 in Hello Future 2024, at the save. Then, with `RawStore.remove_text` and the local tool `tools/hedera/cut_people_from_saved_posts.py` (each cut written in the small file of the post, without its text): 3 more lines in Beyond Blockchain 2023 and the "Team Member:" line of Hello Future 2024 (22:43 UTC), then the 10 signatures under the quotes of Beyond Blockchain 2023. None is left by the rules. Six of the signatures had been printed into the session by a local tool before the cut (`lessons.md`).

The five layouts and what each post gives (`python -m hackathon_memory.parse.hedera_posts --counts`, counts of a run):

| Post | Winner lines | Projects | Left out |
|---|---|---|---|
| Hedera20 | 12 | 10 | |
| Hedera21 | 17 | 13 | |
| Hedera22 | 25 | 19 | 2 lines that list several projects |
| Beyond Blockchain 2023 | 8 | 7 | |
| Hello Future 2024 | 33 | 26 | 1 winner named after a person (Q36) |
| Hello Future 2.0 | 24 | 18 | 10 lines that are only a name (Q36) |
| Hello Future Origins | 12 | 12 | |
| Hello Future Ascension | 15 | 15 | |
| Hello Future Apex | 15 | 15 | |
| **All** | **161** | **135** | |

A winner of Hello Future Ascension is written "1st Place: Project – Team"; the name of the entry is the project, and the name of the team after the dash is left out of it. The list of the names of people is `data/by-hand/hedera.com/names-of-people.sha256`, fingerprints only.

Runs on the main database: parse 29 (135 new winner entries, 168 in all), check 30 (no new id), embed 31 (135 embeddings, 8,633 tokens).

## The counts of Phase C (13 October 2026)

| Source | Projects | Kind |
|---|---|---|
| ETHGlobal's showcase, every project that it ties to Hedera | 658 | full cards |
| Hedera's own winner posts, nine events from Hedera20 to Hello Future Apex | 135 | winner entries |
| The winners page of the Africa hackathon 2025 | 19 | winner entries |
| The winners of Hedera18, from the archive copy, copied by hand | 8 | winner entries |
| The winners of Hedera x AI, from hol.org, copied by hand | 6 | winner entries |
| **All** | **826** | 826 with an embedding |

Proof statuses (check run 30): 272 proof found, 6 dates do not fit, 4 another kind, 3 not found, 541 no id given. Counts of runs, for planning. DoraHacks and AngelHack have not answered: nothing of them is read. Devpost said no: nothing of it is read by a program.

## Next

1. **The owner:** Q36 (the winner named after a person, and the lines that are only a name), and whether Phase C is done, for the merge into `main` and the tag `phase-c`.
2. Phase D: the LLM fields with the quote check, first on the 15 tuning pages (Q29).
