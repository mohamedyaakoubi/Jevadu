# Review layer 1: the ledger story and the check that shows its steps, 23 October 2026

Layer 1 of design 12.3 for what changed on 23 October 2026: the ledger story on the card of a project (S2), its words of the page that mark where the page says them, the same story in the check of a submission (S3), and the window that shows the steps of a check while it runs. The tasks T1 (search an idea, with the order and the comparisons of Gemini), T2 (read a project card) and T4 (check a submission) were done on the running site with the real collection, in Chromium, on a wide screen (1440 by 900) and, for the new parts, on a phone (390 by 844), in the light and the dark theme. Four cards were read: one whose page names the Consensus Service while its IDs show only HBAR transfers, one with an EVM setup, one with transactions before its event, and one with transactions after it. Three repositories were checked: one of the collection, one public repository that the tool had read before, and one public repository that it had never read. T3 (register a submission) and T5 (read the charts) did not change and were not done again.

Each finding is marked **sure** or **unsure**, and names the check of design 12.3 that it fails. Layer 2, the maintainer, accepts or rejects each one and adds new ones.

## What held

- A search by meaning came in under a second; the order of Gemini came in 5.6 seconds, and its comparisons filled their places after it, under grey bars while they were written.
- A word of the page marked every place where the page says it, brought the first one into view, and the next one at each press; the line under the sentences said "place 1 of 2".
- The check of a repository that the tool had never read took 11.1 seconds: GitHub about 4 seconds, the code about 3.5 seconds, and the similar projects about 3 seconds. Its window showed each step as it ran, with the usual time of the code under it, and the answer then took the place of the window with its title in focus.
- axe-core 4.14.0 found no problem on four cards, on the waiting window of a check and on its answer with a word pressed, in both themes and at both widths.

## Findings

| # | Screen | Finding | Check | Sure | Done |
|---|---|---|---|---|---|
| 1 | S2 | In the narrow column of the page's words, a long word was centred on two lines, and the comma after it fell onto a line of its own. | 7 | sure | `8cfbab3` |
| 2 | S2 | After a press, the place of the word came into view and the button went out of it, so the next place needed a scroll back up. A marked place now goes on to the next one too. | 1 | sure | `163ac2d` |
| 3 | S2 | In the dark theme, the marks of a word were too faint to find. | 7 | sure | `163ac2d` |
| 4 | S2, S3 | In a sentence of what stands out, the opening bracket could end a line alone while its word went to the next line. | 7 | sure | `fa2b77f` |
| 5 | S3 | The caption said "every transaction" twice when no hackathon was chosen. | 3 | sure | `53d43dc` |
| 6 | S3 | When the first steps of a check came from the tool's tables, the bar jumped near its end and stood still for three seconds while the last step ran. The bar is now the time spent out of the time spent and the time still to come. | 2 | sure | `7d597fa` |
| 7 | S3 | The lines of the README under the table showed the marks of Markdown (stars, the bars of a table, code quotes, the form of a link), and a word inside an address, such as `/hts/`, would count as naming a service. | 3 | sure | `2fefd02` |
| 8 | S3 | A check of code that the tool read before shows its steps for about half a second before the answer: a short flash. A wait of its own would only slow a judge. | 2 | unsure | no |
| 9 | S3 | The lines of the README stay closed under the table until a word is pressed or the line is opened, so a judge may not see them. | 1 | unsure | no |
