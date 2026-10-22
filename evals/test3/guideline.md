# Test 3: how the Hedera IDs of a page are checked by hand

This guideline says how a person checks, by hand, which Hedera IDs a project page and the README of its code name, and what the ledger says about each one (design 13.4). It was written on 18 October 2026, before any page was checked, and it does not change once the checking starts, with one exception: the addition of 22 October 2026 about schedules, made after the second run (the last section).

## What is measured, and the pass marks

The tool reads each page and each README with a parser (design 6.1), asks the mirror node about each ID it finds (design 7.1), and gives each ID a status by the proof rule (design 7.2). Test 3 compares that work with a check by hand on 50 pages. Three numbers, kept apart:

| Number | What it counts | Pass mark (fixed on 9 October 2026, design 13.6) |
|---|---|---|
| Found | Of the IDs that the hand check finds, the share that the tool found in the same place (the page or the README) | at least 95% |
| Invented | Of the IDs that the tool found, the share that the hand check does not count as an ID of the project | at most 2% |
| Status | Of the IDs that both found, the share whose status by the tool is the status by hand | at least 90% |

Each number comes with its range, computed by project: the pages are drawn again many times, and the range says how far the number moves (design 13.1).

## The pages

50 project pages of ETHGlobal's showcase, drawn at random with a fixed seed from three groups that were fixed before the draw (`evals/sets.py draw-test3`, the set in `evals/sets/test3.json`):

- 15 pages where the tool found an ID on the page itself;
- 20 pages where the tool found an ID in the README only;
- 15 pages where the tool found no ID.

The third group is there for the IDs that the tool missed. The groups come from what differs on this source; the six groups of Test 1 are not used here.

The text that is read is the text that the tool read: the page as it was saved, and the README as it was saved, both with the words about people taken out.

## What counts as a Hedera ID

A Hedera ID here is a thing on the Hedera ledger that the text names as a thing of the project, or as a thing that the project uses:

- an account, a token, a topic or a contract, written `0.0.N`, where N is 1001 or more;
- a transaction, written `0.0.N@seconds.nanoseconds` or `0.0.N-seconds-nanoseconds`. It counts as two IDs: the transaction, and the account that paid for it;
- an address of the EVM kind (`0x` and 40 letters) inside a link to HashScan, which names it on a Hedera network.

These are not IDs of the project:

- a number of 1000 or less, such as `0.0.3`: it belongs to the network itself, or it is a version number;
- an example or a placeholder: a value in a template of settings (`OPERATOR_ID=0.0.12345` under "copy this file and fill in"), a value after "for example", or a value with letters in place of numbers (`0.0.xxxxx`);
- an address of the EVM kind with no link to HashScan: the same address can live on any other chain.

The same ID on the page and in the README counts once in each place. The same ID twice in one place counts once.

**The network** of an ID is the one that a HashScan link names, or the one that the words near the ID name when they name only one network. Otherwise it is open. **The kind** is the word just before the ID on its line ("Topic ID: 0.0.12345"), or the word just after it ("0.0.12345 (topic)"). Otherwise it is open.

## How the status is judged by hand

For each ID of the hand check:

1. Ask the mirror node about it on its network, or on the test network and the main network when the network is open. A small script asks with plain HTTP and keeps the answers next to the sheet; it does not use the tool's code.
2. Write down what the ledger says: the kind of thing, the day it was made, the first and the last activity, and whether it is empty (a topic with no message, a token never issued, a deleted contract, a failed transaction).
3. Give the status by the table of design 7.2, with its additions: the window runs from 30 days before the first day of the event to 14 days after its last day; a word can fit more than one kind (a contract can make a token, and has an account); when the network is open, the better status of the two networks counts.

When the end of the event is not known, the status is "the end of the event is not known yet". When the test network was emptied after the ID was made (1 February 2024), the status is "cannot be checked".

## How the hand check is done, page by page

1. Read the page from top to bottom. A README can hold tens of thousands of letters: read it around each string of the net, and skim the rest for an ID in another form, such as a link to HashScan or an ID broken over two lines. The sheet shows every string with the shape of an ID, with the words around it, to help the eye; it does not decide.
2. For each string, write whether it is an ID of the project by the rules above, with its network and kind.
3. Add any ID that the sheet did not show.
4. After the mirror node's answers, write the status of each ID, with the facts that decided it.

Only then is the tool's work opened, by the script that computes the numbers.

## Planted cases

Three IDs that stand in no text are added to the hand answers of three pages. The tool cannot have found them, so the script must count them as missed. They show that the script counts misses; they are left out of the numbers.

## What the test does not show

It does not show that an ID belongs to the team that names it: a team can paste the ID of somebody else. It does not show that a project is good. The proof rule reads the ledger of today: an ID that was deleted after the event may read otherwise than it did then.

## Added on 22 October 2026, after the second run: schedules

The first check, on 18 October, left out every scheduled transaction, because the list of kinds above does not name it, and its notes called that a limit of this guideline. A scheduled transaction (a "schedule") is a thing on the ledger with its own ID, `0.0.N`: a project makes it so that a transaction runs later, at a time or when enough keys have signed. HashScan shows it at `/schedule/`. The tool learned to read schedules on 22 October 2026, so under the first list, each schedule that it found counted as invented.

On 22 October 2026, after the second run, the maintainer decided that a schedule counts as an ID of the project, by these rules:

- its kind word is "schedule", by the rule of the kind above ("Schedule: 0.0.N"), or a HashScan link with `/schedule/` names it. A "fee schedule" is the list of fees of a token, not a schedule;
- it is empty when it was deleted before it ran, like a deleted contract. The mirror node also says "deleted" of a schedule that ran at its time: that one ran, so it is not empty. A schedule that expired without running was still made, so it is not empty either;
- its dates are the day it was made and the day it ran.

The pass marks did not move. To keep the check fair, all 50 pages were read again for schedules, and not only for the ones that the tool found: every HashScan link with `/schedule/`, and every ID a few words before or after the word "schedule". This found 7 schedules on 4 pages. The report gives the numbers under both lists.
