# Review layer 1: the fourth version of the page, 16 October 2026

Layer 1 of design 12.3 for the fourth version of the page: the search (S1), the project card (S2), the check of a submission (S3), the register (S4) and the charts (S5). The tasks T1 (search an idea), T2 (read a project card), T4 (check a submission) and T5 (read the charts of an event and of a search) were done on the running site with the real collection, in Chromium, on a wide screen (1440 by 900) and on a phone (390 by 844), in the light and the dark theme. A search was typed letter by letter, a filter was chosen, the charts were opened and closed, a card was opened and closed with Escape, an (i) was opened with the pointer and with a tap, and two repositories were checked: one of the collection and one public repository that the collection does not hold, with typed days. T3 (register a submission) was done in the test suite only: the register's topic on the test network is not created yet, and the page says so.

Each finding is marked **sure** or **unsure**, and names the check of design 12.3 that it fails. Layer 2, the maintainer, accepts or rejects each one and adds new ones.

## What held

- Quick results by meaning came in 0.1 to 0.9 seconds after the typing stopped.
- The check of a repository of the collection took 0.5 to 2.8 seconds with no request to GitHub, because its answers were saved; a new repository took 4.8 seconds with two requests to GitHub.
- axe-core 4.14.0 found no problem on the real collection in seven views (the start, a later page of the list, the charts of the collection, a search by meaning, a search by words, the charts of a search, a filter), in both themes and at both widths, nor in the window of a project. The test suite runs it on the check and on the receipt of the register too.
- The phone page does not scroll sideways: 390 of 390 pixels. The filter row scrolls sideways on its own, as intended.
- Closing a window gives the focus back to the card that opened it.
- Each (i) text lists its statuses one per line; it opens on hover or focus at a desk and on a tap on a phone, and closes with Escape.
- On a phone, the check shows "Seen before" first, then the ledger and the code, and the closest past projects last; a long repository name wraps.

## Findings

| # | Screen | Finding | Check | Sure |
|---|---|---|---|---|
| 1 | S1 | With an idea typed, the year filter offered "2025 (16)": 16 of the 50 closest projects are from 2025. Choosing it gave a list of 50, because the filter searched again among all the projects of 2025. The number and the list did not agree. | 1, 3 | sure |
| 2 | S3 | The check wrote "the README calls it a account". | 3 | sure |
| 3 | S3 | For a repository that GitHub marks as a fork, the check wrote "A copy (fork) of another repository". The tool never calls a project a copy. | 3 | sure |
| 4 | S3, phone | A long repository name in the title ran past the right edge of the screen. | 7 | sure |
| 5 | S3 | The window of a check showed the buttons "Previous" and "Next" of the list of projects, which lead nowhere there. | 5 | sure |
| 6 | S2 | Under "Links on the page", a link of no known kind was followed by the word "other". | 3 | sure |
| 7 | S1 | In results by meaning, common words of the idea such as "app", "lets" and "without" are marked in the cards, next to the useful ones such as "payment". | 3 | unsure |
| 8 | S1, phone | The filter row scrolls sideways, and only the start of the second filter shows; nothing else tells that three more filters wait to the right. | 7 | unsure |
| 9 | S1 | For the idea of a street vendor who takes card payments without a bank account, the first results are projects known only from the organisers' lists of winners, with no Hedera ID and no code to check. This is the data and the search (Test 2), more than the screen. | 1 | unsure |

## What is changed after this review

Findings 1 to 6 are fixed in the code. Findings 7 to 9 wait for layer 2.
