# Session: the owner's six points, and the first collection (10 October 2026, afternoon and evening)

The trace of one working session: what the owner asked or decided, in their own words where it matters, and what the assistant did. The full story is in entry [10](../10-ethglobal-walk-and-first-run.md).

This file stays on the laptop. It is never committed.

## 1. Where it started

The session of the eleven points ([2026-10-10-eleven-points.md](2026-10-10-eleven-points.md)) ended with Gate A at three proofs of four. The fourth waited for a list of ETHGlobal project pages that the owner would make by hand. The clean-up note had two items: count the calls of the Google proof in the cost ledger, and write a design document for readers.

## 2. The six points, and one more message

| # | The owner | What was done |
|---|---|---|
| 1 | "no need to backup the project folder, no worries." | Noted. The notes still exist once, on this laptop. |
| 2 | "I found it, it's https://ethglobal.com/showcase/?partners=hedera&page=2 it has all previous hedera related projects". Their browser was checked by Cloudflare and got 429 answers. "What can we do? and just to clarify, the ETH email consent what they meant by honoring is the pulled data, they basically gave consent on whatever way I'd pull data." | The honest request was tried first, and it was never refused. A walk through that list found the winners, and a run saved their 92 pages. Entry 10. |
| 3 | "Q17: yeah why not." | The yes for GitHub's API. The token works: 5,000 requests per hour. |
| 4 | "I don't get what adress do you need? [...] they told me do whatever you want the data is yours, just dont mention it since there's no physical written stuff" | "Address" meant a web link. Today nothing of Dar Blockchain can be read by a program (Q22). A yes that may not be named cannot pass launch gate 10 (Q25). |
| 5 | "Q23: I dont know you tell me, how'd people benefit analytically from all historical projects, like what project themes mostly win and what ismostly done etc." | The assistant decided: six blocks on the event overview screen. Entry 09. |
| 6 | "address these and continue what's left in your clean up note" | Both items of the note are done: the proof counts its calls, and `DESIGN.md` exists. |
| Later | "if my credentials i posted can help in getting the data in a safe way please be my guest [...] Also avoid warning me about what am pasting to you, am aware of what am putting [...] let me know if there's an approach either authed requests or playwright" | The pasted login and cookie were not used, and not repeated or stored. Neither a login nor a browser robot was needed. The instruction about warnings is saved in the assistant's memory. |

## 3. What the assistant decided alone, and tells afterwards

- **Not to use the pasted login and cookie.** The email to ETHGlobal says "Not collected: [...] anything that needs an account".
- **To read the Hedera list at all.** The owner named it and asked for it. The email named only the pages of the winners, so the list pages are named in the next email (the draft is in entry 10, Q24).
- **To make the first run on the same evening,** in two parts: three pages, a look at what was saved, then the other 89. The owner's yes for the site is recorded since 9 October, and they had written that a day was lost.
- **Not to turn the switch on in `.env`.** It stayed `off`. Each command got the switch for itself.
- **To add four guards before the first page was saved:** the count of requests on disk, the stop after three pages with no Hedera prize, a run in parts, and no second request for a page that was not kept.
- **Not to read the other 566 projects of the list.** That is outside the yes of ETHGlobal. It is the owner's question to ask (Q24).
- **To correct the README** where it said that every site was asked first, and to say the early mistake with DoraHacks plainly in `DESIGN.md` (Q26).
- **To read one fact from this session's own log file,** which is outside the project folder: the order of the projects on page 1. It showed that two pages of the list share one row.
- **To update `CLAUDE.md` and the blueprint** (version 0.13) with what the day showed: seven new lines in section 3 of `CLAUDE.md`, and the new way of finding the winners.

## 4. The state at the end

- `phase-a-proofs` at `fdbd791`, in step with GitHub. 614 tests. CI was green on `4053969`.
- **Gate A: all four proofs passed,** each with a result file. The merge and the tag wait for the owner (Q27).
- 92 pages of winners of a Hedera prize are in `data/raw/ethglobal.com/`. 140 of 300 requests are used. Nothing more is to be read from ETHGlobal.
- Open questions for the owner: Q8, Q11, Q13, Q15, Q16, Q22, Q24, Q25, Q26, Q27.
- The next steps are in the note at the top of [`../INDEX.md`](../INDEX.md).
