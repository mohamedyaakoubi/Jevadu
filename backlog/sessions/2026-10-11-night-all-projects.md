# Session: every Hedera project, the 429 and the cooldown (10 to 11 October 2026, night)

The trace of one working session: what the owner asked or decided, in their own words where it matters, and what the assistant did. The full story is in entry [11](../11-all-hedera-projects-and-the-429.md).

This file stays on the laptop. It is never committed.

## 1. Where it started

The evening session had ended with 92 pages of winners saved, all four proofs of Gate A passed, and five questions for the owner (Q22, Q24 to Q27). They answered them in seven points.

## 2. The seven points

| # | The owner | What was done |
|---|---|---|
| 1 | "We need to get all projects and seperate in card as well as winner or normal submission. I'd say just do it, we need all hedera related submitted projects" | The walk and the run were changed to cover every project of the Hedera list (658). The second walk matched the first. The run then saved 62 more pages before the site answered 429. |
| 2 | "theres no historical submission on their part [...] there's a new source https://hedera-hackathon.hashgraph.swiss/ it has few winning projects it would be worth it to get them too directlly." | Dar Blockchain is dropped. The new site was looked at with two signed requests: one page, the winners of the Africa hackathon, 5 links to DoraHacks, no rules. It becomes winner entries in Phase B. |
| 3 | "your analytics are good and thats why I need all projects and not just winners." | Noted in entry 09: with all projects, "what is mostly built" can stand next to "what won". |
| 4 | "for Q27 no the phase is not done, and no sending another email is unecessary because the answer is the same" | No merge, no tag, no email. |
| 5 | "Q26, don't go too much into details [...] what we need is that in general, ETH gave the consent and it's logged [...] dont log we took 4 projects from here and from there." | The paragraph about the first requests to DoraHacks and the table that came from them went out of the public notes. Launch gate 10 was changed. |
| 6 | "Q25: drop dar blockchain unless you can prove me the opposite that they got any data." | Dropped. Hard constraint 21 is marked. |
| 7 | "tell me how possible is it to wrap the project as a pipeline [...] how autonoumous can it be or is it impossible due to resources dynamacity nature?" | Answered in the chat. In short: everything after the saved pages can run by itself and on a timer. Reading a site needs a person three times: for its yes, for its shape, and when it says no. |

During the work:

| The owner | What was done |
|---|---|
| "why not sending anything anymore? make a strategical cooldown and figure out what was the 429 caused by in the code" | The timeline of all requests was rebuilt from the files on disk: 26 requests in the last minute, against 24 at most before, and lower totals over 5, 10 and 60 minutes. No bug: the pace. A cooldown of one hour and a pace five times slower went into the code. |
| "the stop on refusal is meant as the siteowner to send a stop order" | The code now tells a 429 (a speed limit: wait and go on slower, by itself) from a no (403, a bot check: a person decides) and from a stop order (the switch). |

## 3. What the assistant said that the owner may not have liked

- Once, before starting: that reading all projects goes past the letter of their email, and that it will not write that ETHGlobal's consent covers the other pages. Then it did what they had decided.
- That two commit messages which are already pushed still tell the early requests to DoraHacks, and that only a second rewrite of the history could remove them (Q28).

## 4. What the assistant decided alone, and tells afterwards

- The public sentence about the consent: it names what ETHGlobal was asked and what else is read.
- The limit of 800 requests for ETHGlobal.
- The numbers of the cooldown: one hour, five times slower, a third 429 in one day is a no.
- To stop at the 429 and wait for the owner's word. They corrected this, and the code now goes on by itself after a cooldown.
- To look at the new site with two signed requests and to save nothing.
- To change `CLAUDE.md`: hard constraints 10, 18 and 21, section 3, launch gates 10 and 11, section 7. Each change carries the owner's words and the date.

## 5. The state when this was written

- `phase-a-proofs` at `e0c007d`, in step with GitHub. 655 tests.
- 154 of 658 pages saved. 227 of 800 requests used. A run with `--wait` sleeps until 01:00:11 UTC and then reads the last 504 pages at ten seconds apart.
- Open questions for the owner: Q8, Q11, Q13, Q15, Q16, Q28, Q29.
- The next steps are in the note at the top of [`../INDEX.md`](../INDEX.md).

## 6. The four points (11 October, about 00:40 UTC)

Written while the run was waiting for the end of its cooldown. The full story is in entry [12](../12-caches-cag-redis-and-code-against-model.md).

| # | The owner | What was done |
|---|---|---|
| 1 | "would they need to be as a github actions job? [...] a caching strategy is a must (I dont know if a CAG here plays a valuable role, research it) and ofcourse as long as it doesnt degrade quality [...] would redis be needed?" | The sources were read first: the CAG paper, Google's pages on context caching and batch, Redis's own page on semantic caching, the manual of PostgreSQL, GitHub's pages. The answer: no GitHub Actions job for the pipeline, exact caches in PostgreSQL, no CAG, no Redis. |
| 2 | "Leave the commits dont delete them." | Q28 is answered. No rewrite. |
| 3 | "a sample pool of Gemini rewritten and another pool of perfectly code parsed and thats a chance to show difference of cost and even investigate if we are on the right track to use LLM" | Accepted, with one change: the same pages in both ways, not two pools of different projects. It goes into Phases D and G. |
| 4 | "if any of the my 1-3 points doesnt require to be adderessed in phase A then consider phase A as completed now with the gap of waiting answers from other companies ofcourse." | None of the three belongs to Phase A. The assistant told them that Gate A is a gate and that one proof was still running. It merges and tags when that proof passes. |

What the assistant decided alone, and tells afterwards:

- Not to tag `gate-a` on a state where the README itself says that one proof is open, and to merge as soon as it passes without asking again.
- What is kept of a typed idea: a fingerprint and 24 hours. It told the owner that this one is theirs to change.

## 7. Gate A, the merge, and the first part of Phase B (11 October 2026)

The run ended at about 02:28 UTC with all 658 pages saved. The owner had written "continue". The laptop then slept for about eleven hours during the turn.

| What happened | Where |
|---|---|
| The lists proof passed for the 658 pages. Its result file was committed with `Gate: A`, and the README and `DESIGN.md` said so. | `0c08b3a`, `5a9a01b` |
| Phase A was merged into `main` with a merge commit and tagged `gate-a`, on the owner's word of the four points. CI green. | `115d170` |
| Phase B: the parser, the store, the parse and check steps, the proof rule, the ends of events. 943 tests. | entry [13](../13-phase-b-parser-and-store.md) |

What the assistant decided alone, and tells afterwards:

- The ends of ten events from the days of the judging on the pages. The owner may correct any line, and gives the four others (Q30).
- The rules for Hedera IDs, the two more statuses of the proof rule, the pace of the mirror node.

What the assistant must tell the owner, and did at the end of the turn:

- The password of the local database stood in the log of this session (Q32). It should have said so at once.
- Words about people inside the teams' own texts (Q31).

## 8. The nine points (11 October 2026, afternoon)

| # | The owner | What was done |
|---|---|---|
| 1 | "If the project becomes prod we can talk about jobs as a pipeline right? since we'll mostly need to push db into remote supabase? (just a question, this is too futuristic to build)" | Answered: yes. Nothing is built. |
| 2 | "For the builder idea cache you are right." | The default stays: a fingerprint, and the comparison for 24 hours. |
| 3 | "is the code search semantic or embed/chunk based?" | Explained: search by meaning is done with embeddings, plus a search by words. One embedding for a project, pieces only for the long ones. Not built yet. |
| 4 | "what do you mean I mark the services and themes once on the 60 pages?" | Explained with its context: two more ticks on each of the 60 pages of 17 October. |
| 5 | "did you mark that phase A will return to it once the other companies respond with a yes?" | It was not written clearly. It is now in the index, in Q8 and Q13, and in `CLAUDE.md`. |
| 6 | "Q30: I'm lost here I didn't understand what you want me to do" | Explained again from the start, with four links and an example of the answer. |
| 7 | "Q31 if its people then hide them" | The parser hides handles and addresses of people, and the one address is cut out of its saved file. |
| 8 | "Q32 no need to make a new password we are not prod." | The password stays. |
| 9 | "Can you please whenever give me info or insturctions give me the context of it and explain everything in easy language as am not native english, I literally let you do the job and come back when you finish so am not following with what you do." | A rule in `CLAUDE.md` section 8 and in the assistant's memory. |

