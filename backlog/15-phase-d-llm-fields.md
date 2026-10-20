# 15. Phase D: the LLM fields, the quote check, the search

Started on 13 October 2026 on `phase-d-llm-fields`, from `main` after the merge of Phase C. The owner: "Continue to phase D".

## Goal

The LLM fields with the quote check, the embeddings, the search and the comparison. Phase D ends when the search test runs (`CLAUDE.md` section 4). Before Saturday 17 October, the cards of the 60 pages of Test 1 must exist, for the owner's grading (blueprint 13.2).

## What was read first

Blueprint 4.1 to 4.6 (the card), 6.2 to 6.5 (what the LLM is asked, the labels and the quote check, facts never from the LLM, the cache), 13.1 to 13.6 (the principle of the tests, Test 1, Test 2, the pass marks). The card form of Phase A (`llm/card_form.py`, `card-form-0`) and the call (`llm/gemini.py`, `fill_card`), and the state of the budget: 0.20 of 15 dollars spent in `test`.

## Built

| Commit | What |
|---|---|
| `52e3d0a` | The quote check (`read/quotes.py`): quote marks, dashes, spaces and case made uniform; a quote counts with three words or more, when it stands word for word in the text the model read; a field with no quote left is dropped, with the reason. |
| `0369462` | The table of the cards (migration 0010) and its store (`db/cards.py`): one card for each project, model and version of the instructions, with the checked fields, the answer before the check, the counts, the tokens and the cost, and the fingerprint of the text the model read (the exact cache of blueprint 6.5). Only full cards: a winner entry gets no card of the LLM. |
| `54a30d6` | The draw of the sets (`evals/sets.py`): six groups (the length of the text in thirds, an id given or not), 15 tuning pages, 60 pages of Test 1, ten of each group, the seed written, never drawn again. |
| `a48f694` | The two sets, drawn on 13 October: `evals/sets/tuning.json` (15) and `evals/sets/test1.json` (60); the lengths cut at 2,526 and 4,472 letters. Addresses, groups, dates and fingerprints only. |
| `ad7471a` | A refactor: the reader of a set file moved into the package, so that the pipeline does not import from `evals`. |
| `d94733b` | The step `cards` (`read/cards.py`, `python -m hackathon_memory.pipeline cards --set FILE`): the card of each page of a set, the quote check, the store; the same text costs nothing; three failures in a row stop it; a wrong set stops before any call; not part of `all`. 1,369 tests. |
| `9f613e3` | The instructions `card-form-1`, written on the 15 tuning pages only: sentences of at most 20 words in common words, "what it does" in one sentence, "stated" only when one sentence of the page says it, the category "stated" only when the page names its field of life. |
| `f2eb636` | `evals/cards_report.py`: the cards of a set in numbers only (quotes, labels, lengths, steps, categories, cost), into a dated file. |
| `d96fd10` | The counts of the two tuning runs (`card-form-0` and `card-form-1`). card-form-1: "what it does" in 17 words in the middle, against 28; fewer "stated"; the quotes found as often as before; about 4.7 cents a card. |
| `2cc5ba4` | Gate B counts its Google calls in the main ledger (one counted client on the main database, for the pipeline and the searches), so the budget sees them and the count is not deleted with the temporary database. The test fails on the old code. |
| `0777e6f` | `read/quotes.place_of`: where a quote stands in a text, compared as the quote check compares, so that a sheet can mark it. |
| `4f8c413` | Test 1: `evals/test1/guideline.md` (the rules of grading, fixed before anybody grades, invented examples only) and the review sheet (`evals/test1/sheet.py`, `sheet.html`): one HTML page with no network, the text that the model read next to the card, each quote marked in the text, the category and the services asked before the card opens and closed after, the grades kept in the browser and written to a file the grader picks (or downloaded). Written once into `data/evals/test1`, with a fixed order (seed 20261014), 10 parser checks (seed 20261015), and 3 to 6 planted fields chosen with a seed that is not kept. |
| `1b49ac9` | The sheet tested in a real browser (Playwright 1.62.0 and the Chromium build 1234 that is already on this laptop): the card opens only after the questions before it, the grades survive a reload, are saved to a file and opened again, a file of another sheet is refused, a quote is marked. Skipped where no Chromium is installed (GitHub's runner). |
| `b8e6561` | The counts file says what its counts are for: a tuning run, or the cards of a test set before any grading. |
| `4b74ac4` | The counts of the 60 cards of Test 1 (`evals/results/20261013T005711Z-cards-test1-card-form-1.json`). |
| `ff3b10b` | README: the commands of the sets, the cards, the counts and the sheet. |
| `91f7eb4` | `constraints.txt` written again by pip freeze, with Playwright 1.62.0, greenlet and pyee. |
| `bc959d2` | The terminal view of the sheet prints "?" for a sign that a Windows console cannot show, instead of stopping in the middle of a page. Found while reading the pages as the second grader. |
| `c7f58d7` | The report of Test 1 counts a grading that does not cover every project: a grader's numbers on its projects graded in full; the pass marks from a grader who graded all; agreement on the shared projects; a planted field counts for the graders who graded its project. |
| `8fcb9e5` | DESIGN 13.2 and 13.6: the same rule in public words, with the counts of the run (10 and 60) and no reason. |
| `0bfd82f` | The result of Test 1 (`evals/results/20261014T231416Z-test1.json`) and its short report (`evals/test1/report-gemini-3.1-pro.md`). |
| `f7c2de1`, `1672cdf` | The people cut no longer reads "Node.js" as a website; the parser version became ethglobal-page-10, so every page was read again. |
| `57ee56f` | The prices of Gemini 4 Argon in the price book. |
| `095b95e`, `657cefe` | Test 2: its rules (`evals/test2/guideline.md`), its 39 pairs with their reasons (`cases.py`), the runner, and the comparison of other setups of the merge (added after the first run, and said so). |
| `b0a97cb` | The result of Test 2 (`evals/results/20261014T235346Z-test2.json`), its short report, and the counts of the Argon cards on the tuning pages. |
| `b389ad8`, `7217592` | The list of categories split once: "Tools for AI agents"; instructions card-form-2; DESIGN 4.5. |
| `81a3300` | Test 2, the owner's ideas (`evals/test2/ideas.py`): 30 projects drawn once (seed 20261014) outside the 75 pages of the tuning set and Test 1, into `data/evals/test2/ideas.txt` (name and short line); the owner writes 15 ideas; `check` counts them and flags an idea that repeats four words in a row from its project. |
| `7e0a3a7` | `evals/test1/report.py`: the four numbers of each grader with their ranges by project (10,000 draws, seed 20261017), the marks of blueprint 13.6 on the maintainer's numbers (not decided while a field is unanswered), the planted fields caught or not, the check of the categories (4.5), the agreement of the graders. Written before any grade exists. 1,398 tests passed before this commit. |

## Measured

- **The cards of the 60 pages of Test 1**, run 34, 13 October 00:14:56 to 00:51:46 UTC (37 minutes), Gemini 3.1 Pro at HIGH, `card-form-1`: 60 cards, 841 of 843 quotes found, 414 fields kept, 6 not found, 0 dropped by the quote check. Tokens: 151,726 in, 47,834 out, 175,142 of thinking. Cost 2.98 dollars, 4.97 cents a card. Thinking is more than half of the tokens.
- **From that, the run on all 658 pages** would cost about 33 dollars at the normal price (658 x 4.97 cents), and about half in batch mode if batch mode takes this preview model. Not measured: batch mode.
- **The sheet of Test 1** was written on 13 October at 01:05 UTC: 60 projects, 10 parser checks, a few planted fields. Its key (`planted-key.json`) has not been opened. It must stay closed until both graders are done.
- **Pairs for Test 2 that come free** (blueprint 8.4): one repository shared by three projects (three pairs, across events), one Hedera ID shared by exactly two projects of two events, and four shared by two projects of the same event. 18 pairs have the same name in two events: a name is a hint, so they need a judge. Far fewer than 50: Test 2 needs other candidates.

## The second grading of Test 1

Done on 13 October 2026, 01:05 to 01:32 UTC, before the owner's grades exist, in the order of the sheet: for each project the page first, then the category and the services, then the card. Read with `python -m evals.test1.sheet --show N` (and `--card`), answers kept in `data/evals/test1/second-grader.txt` and turned into `grades-second.json` by a local tool (`second_grades.py` in the scratchpad of the session). The key of the planted fields was not opened.

- Fingerprints at 01:32 UTC: `grades-second.json` 0c51bc352fee079208cf73e5ae59c4ac774cd51c83d0b69946c31b16f4de22c0, `second-grader.txt` 58f616447b9c77a5bbe7cd8963eb40ec16ac54542ec8c68945f5b1846830d89a, `sheet-data.json` 0ed06179814aa324968d3dca69245037fd3cf5d4fac4cd6dae0d34f4f374cf1f. The grades are not changed after this. A later change of mind goes into a note, not into the file.
- The rules this grader added to the guideline are written at the top of `second-grader.txt`: a list or steps are "stated" when each part is said by a sentence; a category is "inferred" when several categories could fit, "stated" only when the page plainly names the field (both accepted for the AI agents category); a wrong field with no support has a wrong label; the parser check is left to the owner.
- Project 1: the first two fields of its card were seen in the layout check before the answers of project 1 (said in its note).
- **Nothing about these grades goes to the owner before they have graded**, so that their grades stay their own.

## Results of 15 October 2026

- **Test 1** (Gemini 3.1 Pro, card-form-1): the owner graded projects 1 to 10, the assistant all 60. On the assistant's 60 (408 filled fields, 6 planted left out): not wrong 408 of 408, wrong 0, fully right 396 (97.1%, 95.5 to 98.5), kept 100%, labels 408 of 414 (98.6%, 97.3 to 99.5), quote check 414 of 414. Faithful, kept and labels pass. Planted: the assistant caught 6 of 6 (5 wrong, 1 partly); the owner's 10 projects held one (project 7, a category made "Developer tools"), graded right, so the planted mark fails. Agreement on the 10 projects: grades 63 of 69, labels 65 of 69. Categories: the same on 4 of 11, so the list was split once. Parser: 1 of 10 checked by the owner, the same.
- **Test 2** (the search as it is, 826 projects): 34 of 57 known projects in the first 10 (59.7%, 44.4 to 74.1), under the mark of 80%. Repeats of one project: 20 of 24. Different projects with the same idea: 9 of 24, the misses mostly tools for AI agents in crowded themes. The owner's ideas: 5 of 9, each found in first place. Look-alikes shown in 2 of 30. Other setups: meaning only 36, words only 23, merged with windows 20, 30, 50: 35, 37, 34; none above the product's range, so the product keeps its setup. 13 of the 23 misses are in places 11 to 20 by meaning.
- **Gemini 4 Argon against Gemini 3.1 Pro** on the 15 tuning pages (card-form-1): 6.33 against 4.72 cents a card; thinking 4,954 against 2,737 tokens; quotes 261 of 261 against 205 of 207; no field dropped by either.
- **card-form-2** on the 15 tuning pages (3.1 Pro): 5.16 cents a card, quotes 193 of 196, no field dropped; categories: Tools for AI agents 4, Developer tools 4, Payments 2, AI agents 2, others 1 each.
- **Test 1 again with card-form-2** (graded by the assistant alone, on the Phase E branch, `8d746a0`): all four pass marks met, fully right 98.5%, labels 99.5%, planted 6 of 6. Details in [16](16-phase-e-website.md).

## Found on the way

- The two runs of part 1 of Gate B counted their Google calls in their own temporary databases, which were deleted after the proof: about 30 cents of embeddings are missing from the ledger of the costs. Fixed for the next runs in `2cc5ba4`; the 30 cents stay missing.
- A test of the report wrote its invented result into the real `evals/results`: the folder was a default value of the function, fixed when Python read it, so the test's replacement did not reach it. Seen in `git status` before any commit, the file deleted (it held only the invented projects). The function now looks up the folder when it runs. [lessons](lessons.md)
- To check the layout of the real sheet, the assistant took two pictures of project 1 in a headless browser. The second showed the first two fields of the card of project 1 before the assistant's own answers for project 1. Its grades say so; the other 59 projects are graded page first, card after.
- A Python script inside a shell command lost its backslashes again, three times today (a test with a line break, a helper, a test file). Rule 5 of the index was broken each time; the file tool fixed it.
- **A false positive of the people hiding (blueprint 5.4, Q31):** in one page of Test 1 the parser hid "@hashgraph" in "Node.js/@hashgraph/sdk" as if it were a person's handle. The same package name after a space is not hidden. The model read "@[name hidden]/sdk". To fix after Test 1, with a test; a change of the parser changes the text the model reads, so the cache makes those cards again.
- The Windows console of Git Bash turns a lone "/" argument into a folder path (`C:/Program Files/Git/`): a local tool that used "/" as a separator got 25 answers instead of 7. The separator is "+".

## Next

1. Done: the second grading (see above).
2. Test 2, the search test, which ends Phase D. Part 1, pairs of projects with the same idea: the free pairs (one repository shared by three projects, one Hedera ID shared across two events), the 18 pairs with the same name in two events (a hint, to be judged), and the clusters of the same idea that the second grader met in the 60 pages (agent spending limits, document notaries on HCS, tokenized bonds with ATS, agent marketplaces, private swaps, games), judged with a written rule. Not taken from the search itself, which is under test. Part 2: the owner's 15 ideas (`data/evals/test2/ideas.txt`). Then the runner and its result file.
3. The code card and the comparison of code and model (blueprint 13.3), on the 60 pages, with the owner's services and categories of the sheet.
4. Q29, with the measured cost: the cards of all 658 pages after Tests 1 and 2.
