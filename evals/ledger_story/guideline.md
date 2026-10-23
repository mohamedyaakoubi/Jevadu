# The ledger story, first measure: does the ledger show what the card hides?

This guideline was written on 23 October 2026, before any history was read. It does not change once the reading starts.

## The question

The ledger story is a planned view of each project: its activity on the Hedera ledger over time, by Hedera service, next to what its page names and what its code calls. Before it is built, this measure asks one question: would it show a judge something that the card of today does not show, often enough to be worth building?

## What the card shows today

For each Hedera ID: its kind and one status of the proof rule (design 7.2), such as "proof found" or "the dates do not fit". For the project: one proof status, one life status (design 7.4), the card's sentence about Hedera services, and what the code calls (design 7.3). The card never compares these sources, and it never shows when the activity happened.

## The projects

Every project with at least one own Hedera ID on the ledger whose kind fits what the page says: the status "proof found", "the dates do not fit" or "found, but empty". An own ID is named by one project only, because an ID that several projects name is often a shared service (design 8.4). A project whose event has no known last day is left out.

## The history of an ID

For each own ID, on its network, the mirror node gives:

- an account: its transactions;
- a topic: its messages;
- a contract: its calls;
- a token: the moment it was made, and the moment of each NFT minted;
- a schedule: the moment it was made, and the moment it ran;
- a transaction: its own moment.

One ID gives at most 2,000 events. An ID that reaches this limit is counted as cut, and the number of cut IDs is reported. An event that several IDs of one project share, such as a message that an account sends to a topic, counts once.

Each event gets one Hedera service, from the kind of the ID and the type of the transaction: Consensus, Tokens, Contracts, Scheduled, Files, or HBAR and accounts.

## What the page names

The page's own words: its short line and the two texts that the parser copied word for word, not the card that the model wrote. A service is named when one of these words appears, in any case:

| Service | Words |
|---|---|
| Consensus | consensus service, HCS, Hedera topic, HCS topic, consensus topic, topic ID |
| Tokens | token service, HTS, Hedera token |
| Contracts | smart contract, Solidity |
| Scheduled | scheduled transaction, schedule service, HSS |
| Files | file service, HFS |

The words are strict on purpose. A token or an NFT can also live in a smart contract, so "token" alone does not count. HBAR is left out of the comparison: nearly every project moves HBAR to set itself up.

## The signals

Each signal is a fact about a project that the card of today does not show.

- **S1, active before.** One of the project's IDs has the status "proof found", and its own IDs were active earlier than 30 days before the first day of the event, where the window of the proof rule begins (design 7.2).
- **S2, mostly before.** More than half of the project's events happened earlier than that.
- **S3, named but not done.** The page names a service, and the ledger holds no event of that service.
- **S4, done but not named.** The ledger holds at least 3 events of a service, and the page does not name it.
- **S5, came back.** The ledger holds events later than 30 days after the last day of the event, the line of the life rule (design 7.4). The card already shows a life status, so S5 is reported but does not count for the decision.

## The decision, fixed before the reading

The ledger story is worth building if at least 20% of the projects show at least one of S1, S3 and S4. Under 20%, it is not built, and the report says so. Each share comes with its range, computed by project as in the other tests (design 13.1). The words of the table and the limit of 20% are a first choice. They are fixed now and are not moved after the reading.

## What this measure does not show

- That these facts help a person decide. That is the second step: a test with people.
- That a signal is a fault. Activity before a hackathon can be allowed by its rules, and a page does not have to name every service. The signals are facts.
- What a project did with IDs that it never names.
