# Review layer 1: the depth of use, reading again, and a rehearsal, 28 October 2026

Layer 1 of design 12.3 for what changed on 25 October 2026: the part "Depth of use" of a card (S2) with its strip of days, the line at the head of a card that says when GitHub and the mirror node were read, with its button "Read again now", the same depth of use in the check of a submission (S3), and the band and the register of a rehearsal (S4). The task T2 (read a project card) was done on six cards of the real collection, chosen for what their depth of use shows: a project active on two days, a contract never called, tokens held by other accounts, a project active on eleven days, a Hedera package with no call, and a project whose IDs other projects name too; "Read again now" was pressed on one of them. The task T4 (check a submission) was done on the repository of a project of the collection, for its hackathon. The rehearsal was opened, and nothing was pressed that writes to the ledger. Chromium, on a wide screen (1440 by 900), in the light and the dark theme. The website is no longer reviewed on a phone (the maintainer's decision of 24 October 2026).

Each finding is marked **sure** or **unsure**, and names the check of design 12.3 that it fails. Layer 2, the maintainer, accepts or rejects each one and adds new ones.

## What held

- axe-core 4.14.0 found no problem on the six cards, on a card read again, on the answer of a check, and on a page of the rehearsal, in both themes for the cards and the rehearsal.
- The keyboard reaches every square of a strip, and the line under the strip then names its day and its number, as it does under the pointer; the table under the strip holds the same numbers under three column heads.
- The text of the strip has a contrast of 4.8 to 1 in the light theme and 6.6 to 1 in the dark one, over the 4.5 to 1 of WCAG AA. It was measured, since axe-core does not judge the colour of text inside an SVG drawing.
- The kinds of transaction read as sentences, such as "201 messages to a topic, 155 transfers, 55 mints of tokens or NFTs", and the kinds that a card does not name are counted as "and 14 more of 2 other kinds".
- "Read again now" said at once that it was reading GitHub and the mirror node again, and the card came back by itself 17 seconds later; GitHub answered "not modified" for the facts and the README of the repository. The line at the head of the card then gave the day of that reading, and so did the ledger story.
- The check of a repository that the tool had read before answered in 1.5 seconds, with the depth of use of the IDs of its README after the ledger story.
- With the rehearsal, the band stands at the top of every page, and the first press of Tab still reaches "Skip to the results".

## Findings

| # | Screen | Finding | Check | Sure | Done |
|---|---|---|---|---|---|
| 1 | S2, S3 | The names of the rows and the dates under the strip of days were drawn at about 10 pixels, smaller than the smallest text elsewhere on a card (13 pixels). At 13 units of the drawing they are about 12 pixels, and the longest name still ends before the first day. | 7 | sure | `2be669b` |
| 2 | S4 | In a rehearsal, the box of the register said that its button writes to the public register, and the band that says otherwise had scrolled out of view by then; its receipt was titled "Registered on Hedera". The box now names the practice topic above the button, and the receipt is titled "Registered on the practice topic". | 3 | sure | `bdd71fb` |
| 3 | S3 | In a check, the README's own words about Hedera kept the mark of a Markdown quote (">") and the stars around a phrase. | 3 | sure | `faf6a13` |
| 4 | S2 | A team that sent the same code to several hackathons names the same Hedera IDs in each of its entries. Each entry then says, among the signs that stay on paper, that every ID it names is named by other projects too and that it has no ID of its own: a fact, but the other projects are its own entries, which the card links as the same code. One card of the collection shows it. A sentence about a team is the maintainer's to choose. | 1 | unsure | no |
| 5 | S2 | In the table of days, a date breaks onto two lines in its narrow column ("17 July" over "2026"). | 7 | unsure | no |
| 6 | S2 | The head of a card gives the day of the oldest answer of the mirror node about its IDs, and the ledger story the day its histories were read, which can be later: two days of the ledger on one card, each right for what it says. | 3 | unsure | no |
