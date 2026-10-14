# Test 2: how the search is tested

This guideline says how the search is tested (design 13.3). It was written on 15 October 2026, before the first run, and does not change after it.

## The question

A builder types an idea. If a similar project was already sent to a Hedera hackathon, is it in the first 10 results? A builder reads the first screen, so a project that is only on the second screen counts as not found.

## The cases

**Pairs of the same idea.** Two projects are the same idea when someone who holds one of them would say "this was already built": the same users and the same main action. The chain, the name and the extras do not matter.

- The same idea: two projects that both put the fingerprint of a document on the ledger so that anyone can check it later.
- Not the same idea: a payment gateway for shops and an app that splits a bill between friends. Both move money, but for other people and in another way.

Each pair is searched both ways. The short line of one project, with its own name taken out, is the idea, and the other project must be in the first 10 results. A winner entry has no short line, so the first sentence of its published text is used. The name is taken out because a builder who types an idea does not know the name of a project that already exists.

**Pairs that only look alike.** Two projects that share a name, a Hedera ID or a theme, but not the idea. They are searched both ways too, for information only: the search may show them, and a person then tells them apart. They count in no number.

**The maintainer's ideas.** The maintainer wrote ideas in their own words, each about a project drawn at random, after reading only its name and short line (`evals/test2/ideas.py`). That project, and any project of the same idea as it among the pairs, must be in the first 10. An idea that repeats four words in a row from its project is counted apart, because it measures the copy, not the search.

## Where the pairs come from

None comes from the search under test, which would find its own pairs by design.

- **The same repository** in two projects (design 8.4).
- **The same Hedera ID** in two projects. An ID that several projects share is often a common service, so these pairs were judged one by one.
- **The same name** in two events. A name is a hint and not a proof, so each pair was judged by reading both texts.
- **The 60 pages of Test 1**, which the second grader read in full: projects with the same idea among them.

The second grader judged each candidate with the rule above and wrote the reason in our own words (`evals/test2/cases.py`).

## What is searched

The search of the product (`src/hackathon_memory/search/engine.py`): one list by meaning, from the embeddings of the page texts, and one by words (BM25), merged. All projects in the database are searched: full cards and winner entries. The project that gives the idea is left out of its own results, so 11 results are asked and 10 stay.

## The number

The share of the known projects that are in the first 10 results, over the pairs of the same idea and the maintainer's ideas together, and for each part apart. Its range comes from drawing the cases again, 10,000 times with a fixed seed; the two ways of one pair are drawn together, as one case.

**Pass mark** (design 13.6, fixed on 9 October 2026): at least 80% of the known similar projects in the first 10 results.

## Other setups of the search, on the same cases

Added on 15 October 2026, after the first run had shown that some known projects were in the first 10 by meaning but fell out when the two lists were merged. The search's own code says that its window and its merge are to be compared by this test. Each run now also counts, on the same cases: meaning only, words only, and the merge with a window of 20, 30 and 50 projects from each list. They are for comparison only. The product keeps its setup unless another one finds more than the high end of the product's range.

## What this run does not compare

Design 13.3 also asks to compare the page text with the fields of the model, and one embedding model with another. The fields of the model exist for 75 pages only, and a fair comparison needs them for every project in the search, so that comparison waits for the cards of all pages. A second embedding model is not in use. This run measures the search as it is.

## What is kept, and where

The result file in `evals/results` holds the addresses, the places, the numbers and a fingerprint of each idea. It holds no text of a page and no idea. The ideas stay in `data/evals/test2` on the maintainer's laptop.
