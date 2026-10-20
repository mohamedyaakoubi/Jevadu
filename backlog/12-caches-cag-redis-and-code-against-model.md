# 12. Where the automatic steps run, the caches, CAG, Redis, and code against model

- **Date:** 11 October 2026, at night
- **Who:** the owner (Mohamed Yaakoubi), with Claude Code
- **Status:** research done, decisions written. Nothing is built. The work belongs to Phases D and G.

This file stays on the laptop (`CLAUDE.md`, hard constraint 20). It is never committed.

## Goal

The owner sent four points after the answer about the pipeline:

1. "For the pipeline for the full ones, would they need to be as a github actions job? The search is obviously full but honestly a caching strategy is a must (I dont know if a CAG here plays a valuable role, research it) and ofcourse as long as it doesnt degrade quality, and this brings a technology into light, would redis be needed?"
2. "Leave the commits dont delete them."
3. "can make a seperate pool? a sample pool of Gemini rewritten and another pool of perfectly code parsed and thats a chance to show difference of cost and even investigate if we are on the right track to use LLM (well it is yes mostly for messed up descriptions) but let me know what you think."
4. "if any of the my 1-3 points doesnt require to be adderessed in phase A then consider phase A as completed now with the gap of waiting answers from other companies ofcourse."

## What was read, and when

Everything below was read on 11 October 2026. The pages were read through a tool that fetches a page and quotes from it, so each line gives the exact words that came back.

| Source | What it says |
|---|---|
| Chan, Chen, Cheng, Huang: "Don't Do RAG: When Cache-Augmented Generation is All You Need for Knowledge Tasks", arXiv 2412.15605, version 2 of 23 February 2025 (the summary page and the full text) | The method: "preloading all relevant resources, especially when the documents or knowledge for retrieval are of a limited and manageable size, into the LLM's extended context and caching its runtime parameters". The tests used Llama 3.1 8B. The largest knowledge was about 85,000 tokens (64 documents of HotPotQA). Limits in the authors' words: "this approach becomes impractical for significantly larger datasets", and "long-context LLMs may experience degradation when handling very long contexts". The paper says nothing about knowledge that changes. |
| Google, "Context caching overview" for Vertex AI, last updated 10 October 2026 | "All Google Cloud projects have implicit caching enabled by default." "Implicit caching provides a 90% discount on cached tokens compared to standard input tokens." Minimum: "Gemini 3 family models: 4,096 tokens", and "Gemini 3.0 Flash Preview, 3.1 Pro Preview, 3.7 Flash, and 3.8 Flash (implicit caching only): 6,144 tokens". To raise the chance of a hit: "Place large and common contents at the beginning of your prompt." A hit is not promised for implicit caching. An explicit cache lives 60 minutes by default and has "storage costs based on how long caches are stored". Both of our models are on both lists. |
| Google, "Batch inference with Gemini" for Vertex AI, last updated 10 October 2026 | "Gemini 3.1 Pro preview" and "Gemini 3.8 Flash" are on the list. "Batch processing is offered at a 50% discounted rate compared to real-time inference". "The job remains in queue for up to 72 hours before it expires." "Most jobs complete within 24 hours after it starts running (not counting the queue time)." "the discounts for cache and batch don't stack. The 90% cache hit discount takes precedence over the batch discount." |
| Redis, "LangCache concepts" (its own documentation) | "Semantic caching gives up the guarantee that a cache hit is always correct, in exchange for the ability to match paraphrased or related questions." In its table: "A false-positive match can return a wrong answer". In its questions: "Could I get back a response for a different question than the one I asked? Yes." The default threshold is 0.85. |
| Schroeder and others, "vCache: Verified Semantic Prompt Caching", arXiv 2502.03771, at ICLR 2026 (through a search summary only) | Caches that use one fixed similarity threshold give no guarantee of correctness. Not read in full. |
| PostgreSQL 17 manual, SELECT, the locking clause | "With SKIP LOCKED, any selected rows that cannot be immediately locked are skipped. [...] can be used to avoid lock contention with multiple consumers accessing a queue-like table." |
| GitHub documentation, "Events that trigger workflows", `schedule` | "The schedule event can be delayed during periods of high loads of GitHub Actions workflow runs." "If the load is sufficiently high enough, some queued jobs may be dropped." "Scheduled workflows will only run on the default branch." "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." |
| GitHub documentation, secure use of Actions | Self-hosted runners should "almost never be used for public repositories". For private repositories: "be cautious". |
| GitHub documentation, billing of Actions | GitHub Free: 2,000 minutes a month for private repositories. Free for self-hosted runners. |

## What we already measured ourselves

From the dated result file `proofs/results/20261010T155247Z-google-models.json` (one call for each layer, on a text of 81 words):

| | First layer (Gemini 3.1 Pro, HIGH) | Search layer (Gemini 3.8 Flash, HIGH) |
|---|---|---|
| Time | 21.4 seconds | 16.5 seconds |
| Tokens in | 1,723 | 1,723 |
| Tokens out, and thinking tokens | 658 and 1,620 | 706 and 2,022 |
| Cost | 3.08 cents | 1.15 cents |
| Share of the cost that is input | 11% | 11% |

So nine tenths of the cost of a call, and almost all of its time, is the thinking and the writing of the model. The input is the small part. This decides most of what follows.

From a script count on the 92 saved winner pages (planning only, not a test): the two titled texts of a page have a median of about 2,700 characters together. With the rule of thumb of four characters for a token that is about 700 tokens for a project, and 0.4 to 0.5 million tokens for 658 projects. This is an estimate.

## Findings and decisions

### 1. The automatic steps do not need a GitHub Actions job

The automatic steps are ordinary commands that are safe to run again. What starts a command is a different question from what the command is.

- **Now:** by hand on the laptop. If a timer is wanted, the timer of Windows.
- **After the event, on a server:** a timer on the machine that holds the database. The list of jobs inside PostgreSQL keeps the state, so any timer will do.
- **GitHub Actions keeps the job it has:** the lint and the tests on every push.

Why not GitHub Actions for the pipeline:

1. A job of GitHub starts on an empty machine of GitHub. Our saved pages and our database are on the laptop. No page text goes into git, and nothing goes online before a new request to the site (design 5.7). So the job would have nothing to work on.
2. A collector there would lose the count of requests, the cooldown and the memory of a refusal, which are files on disk.
3. The timer of GitHub is not exact, and its own documentation says that a run can be dropped.
4. A runner of our own on the laptop would work, and it adds nothing to the timer of Windows. GitHub advises against it for a repository that may become public.
5. The Google sign-in and the database password would have to be stored in one more place.

When it becomes a good choice: the data lives in a hosted database, and the sites give their data themselves. Then a job of a few minutes on a timer fits the free minutes. The commands stay the same.

### 2. The caching strategy

Three rules.

**Rule one: the same input is never paid for twice.** An exact cache gives back the stored answer only for exactly the same input. It cannot change an answer.

| # | What is kept | The key | Can it show something wrong? |
|---|---|---|---|
| 1 | The saved page | Its address | No. A page is asked for one time (design 5.7). |
| 2 | The card fields of the first model layer | Model, version of the instructions, fingerprint of the input (blueprint §6.5) | No |
| 3 | The embedding of each card | Embedding model, fingerprint of the text | No |
| 4 | The facts from the ledger and from GitHub | The ID or the repository, with the time of the reading | It can be old. So the card shows the date of the reading, and a timed command reads again. |
| 5 | The embedding of a typed idea | Embedding model, the idea with spaces and capitals made the same | No |
| 6 | The comparison that the search model writes | Model, thinking level, version of the instructions, fingerprint of the idea, and the fingerprints of the cards that were shown | No. A new project among the first results, or a changed card, gives a new key. |

All six live in PostgreSQL, next to the ledger of the costs. So the cost report can say what the cache saved.

**Rule two: a fact is never inside a cached text.** The model does not write IDs, dates or statuses (design rule 2). They are read from the tables when the page is drawn. So a cached comparison cannot carry an old fact.

**Rule three: the list of results never waits for the model.** The closest projects come from the embedding of the idea and one query in the database. They are shown at once, with their facts. The comparison appears when the model has finished. Blueprint §8.3 already says that the page shows the cards if that call fails.

**Not built: an answer for a similar question.** A "semantic cache" gives the stored answer of one question to another question that looks close. Redis's own documentation says that this "gives up the guarantee that a cache hit is always correct". Here the comparison speaks about the idea that was typed. A hit for a close idea would tell a builder something about an idea that is not theirs. This is the one kind of cache that lowers quality, so it is left out.

**What a cache does not do.** It does not make a new search faster. A new idea has no stored answer, and the model still thinks for about 16 seconds at the level HIGH. The setting that changes this is the thinking level of the search. Blueprint §11.3 already names it as the first setting to test in Phase D, with Test 2 as the judge.

**Google's own cache does not reach us today.** It gives 90% off for the repeated beginning of a prompt, from 6,144 tokens on for our two models. Our instructions and form are about 1,600 tokens. The input is also only 11% of the cost of a call. Making the prompt longer to reach the cache would save about one dollar on the whole first run. Not done. The meter already counts cached tokens (`cached_content_token_count`), so a hit would show in the ledger.

**What does save money: batch mode for the first layer.** The first layer does not answer a person, so it can wait. Google's batch mode costs half, and both models are on its list. A job can stay in the queue up to 72 hours, and most finish within 24 hours of the start. So it must be started early. It is decided in Phase D, with the measured cost of the sample (Q29).

**What is kept of a typed idea.** The search cache holds a text that speaks about a builder's idea. A builder may not want their idea kept. The assistant's default, which the owner can change because it is about trust and not about technique: the idea is stored only as a fingerprint, the cached comparison is deleted after 24 hours, no log holds the text of an idea, and the method screen says so in one sentence. It matters only when the tool is online. On the laptop it has a useful side: a rehearsal of the demo does not warm the cache for the video of the next day.

**For the demo video.** A stored answer appears at once, and a new idea takes about 16 seconds. The video must not show the first as the normal speed.

### 3. CAG has no role as the search

CAG means: put the whole knowledge into the prompt of the model once, keep the model's inner state, and answer every question from it with no search step.

Why not here:

1. **The size.** The authors tested up to about 85,000 tokens and say that it "becomes impractical for significantly larger datasets". The ETHGlobal projects alone are an estimated 0.4 to 0.5 million tokens, half of the window of the model. A second source would not fit.
2. **The cost.** At the cached price, half a million tokens cost about 3.4 cents of input for every search. A whole search call cost 1.15 cents when measured. From January 2027 the prices of Gemini 3.8 Flash double.
3. **Who picks the closest projects.** Today the embedding search and the word search pick them. The same idea gives the same list, the order can be explained, and Test 2 measures it. With CAG the model would pick from a very long prompt. Two runs can give two lists, a project in the middle can be missed, and the model could name a project that is not there. That goes against design rules 1 and 2.
4. **The data changes.** Each new project and each new reading of the ledger would mean a new cache.

The good idea in CAG is to do the heavy work one time, before the question comes. The design already does that: the cards and the embeddings are made one time and stored.

### 4. Redis is not needed

| What Redis is used for | What does it here |
|---|---|
| A cache of answers by exact key | A table in PostgreSQL. A lookup by key is far shorter than the 16 seconds that it saves. The table survives a restart, has the same backup and the same migrations, and stands next to the cost ledger. |
| A cache by similar meaning | Not wanted (finding 2). If it ever is, pgvector already searches by meaning. |
| A list of jobs | PostgreSQL, with SKIP LOCKED, which its manual names for this use. Already in blueprint §11.6. |
| Counters and sessions that several servers share | There is one process on one laptop. |

What would bring Redis back: several web servers under real traffic, and a measurement that shows the database is the slow part. Until then it would be one more service to start, to back up and to explain to a stranger (launch gate 1).

### 5. Code against model: yes, on the same pages

The owner's idea is right, and half of it is already planned. Test 2 already compares "the page as it is against the LLM fields" for the search (blueprint §13.3). Test 1 already grades the parser in the same sheet (blueprint §13.2).

One change: not two pools of different projects. The same pages are processed in both ways. With different projects, a difference could come from the projects and not from the method.

- **The code card is made for all 658 pages.** It costs nothing, and the parser is built in Phase B anyway: name, short line, the two texts word for word, the links, the event, the prize state, the Hedera IDs. It is the base of every card and the fallback when a model call fails.
- **The model reads a sample first.** The 15 pages for tuning give the first real cost of a page. Then the instructions are frozen, and the 60 pages of Test 1 are read one time. The 60 are drawn by a program with a fixed seed, over the groups of this source, before any result is seen.
- **What is compared, each with a dated result file:**

| # | Question | Code alone | With the model | Judge |
|---|---|---|---|---|
| a | Does the search find the known projects? | Embeddings of the two texts | Embeddings of the model's fields | Test 2, the same pairs |
| b | Which Hedera services does a project name? | A fixed list of words | The model's field | The owner's labels on the 60 pages |
| c | Which theme is it? | Words for each of the 16 categories | The model's field | The owner's labels on the 60 pages |
| d | What is the problem, what is the solution? | Nothing: no title on the page says it | The model's field, with label and quotes | Test 1, as planned |
| e | What does a page cost, and how long does it take? | Nothing | From the ledger of the costs | The ledger |

- **The owner labels once.** For b and c they mark on each of the 60 pages which services it names and which theme fits. Then code scores every method against their labels. A third method later costs them nothing more. This adds about half an hour to their grading on 17 October (an estimate).
- **The rule for "better" is written before the run,** in `evals/`, as blueprint §13.1 asks. The comparison is by page, on the same pages.
- **What the assistant expects, said before the result:** the pages of ETHGlobal are clean, with the same two titled texts on every page. So the search on the two texts may be as good as the search on the model's fields. Code cannot say what the problem is when no title says it, and cannot tell "we plan to use" from "we use". A list of words may do well for the services and badly for the themes. If so, the model stays for the themes and the untitled fields, and it is not paid where code does as well.
- **A result holds for one source.** The value of the model grows with the mess of the pages. ETHGlobal is the cleanest source. The test is run again for each new source.
- **Where it shows:** one table on the method screen: what code alone gives, what the model adds, what it costs.

It costs about two dollars (60 pages at about three cents, an estimate from one measured call).

### 6. The commits stay

The owner: "Leave the commits dont delete them." Q28 is answered: no second rewrite of the history. The two messages `7148944` and `fdbd791` stay as they are.

### 7. Phase A

None of points 1 to 3 belongs to Phase A. So the owner's condition holds, and they say that Phase A is done.

One proof of Gate A was open when they wrote this: the lists proof under the scope that they widened on 10 October. 154 of 658 pages were saved, and the run was waiting for the end of its cooldown. Gate A is a gate (`CLAUDE.md` section 4). The assistant told them so, and merges and tags when the proof passes, on their word of this message.

## What went wrong

Nothing new in the code. One thing in the way of working: the answer to four questions took more than twenty minutes, because every source was read first.

## What this does not prove

- That a lookup in a PostgreSQL table is fast enough here. It was not measured. It will be, when the cache is built.
- That the batch mode of Vertex AI starts quickly for a preview model. Google's page gives the limits, not the usual wait.
- That the estimate of 0.4 to 0.5 million tokens is right. It comes from 92 winner pages and a rule of thumb. The other pages may be shorter.
- That the model will lose or win against code. That is what the test is for.
- The two papers: the CAG paper was read in its summary and through quotes of its text. The vCache paper was read through a search summary only. Read them in full before they are named in a pitch.

## Next

- Phase B: the parser makes the code card for every saved page.
- Phase D: the exact caches 2, 3, 5 and 6 as tables with migrations. The sample before the full run. The decision about batch mode.
- Phase G: the table "code alone, with the model, the cost" on the method screen.
- Blueprint version 0.14 takes these decisions into §6.5, §8.3, §11.2, §11.4 and §13.

## Commits

None. This entry is research and decisions.
