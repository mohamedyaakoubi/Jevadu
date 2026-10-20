# 06 · The live proofs, and the owner's answers

- **Dates:** 9 October 2026 (night) and 10 October 2026
- **Status:** in progress. The first run on ETHGlobal is open.
- **Blueprint:** §9 (the topic), §11.3 (the models), §14.2 (Gate A)
- **Follows:** [05-phase-a.md](05-phase-a.md), which holds the build and the table of Gate A.

## Goal

Run the proofs of Gate A on the real services as soon as the owner's values exist. Write down what the real services showed. Settle the decisions and the questions that the owner raised in the same hours.

## What the owner did and decided

| Owner | What came of it |
|---|---|
| They filled `.env` and asked the assistant to check it. | The setup check (no value shown) found the Hedera account and a valid ECDSA key, the Google project, the location `global`, a Google sign-in file, their contact address, and six `GEMINI_` lines. The GitHub token was empty (it is needed from Phase B). The list of ETHGlobal prize pages did not exist yet. |
| They decided: "the first layer of rewriting with Gemini 3.1 Pro and the search with 3.8 Flash". | Done. [`decisions.md`](decisions.md), blueprint §11.3, `CLAUDE.md` hard constraint 7. |
| They allowed other names for the Gemini lines: "first for rewrite and second for search". | `GEMINI_REWRITE_MODEL`, `GEMINI_REWRITE_THINKING_LEVEL`, `GEMINI_SEARCH_MODEL`, `GEMINI_SEARCH_THINKING_LEVEL`. The four lines of `.env` were renamed and the 43 other lines were checked to be unchanged byte for byte. |
| They decided: "HIGH for all and remove those deprecated variables". | Both layers use HIGH. The two `THINKING_BUDGET` lines are removed. Google deprecated the budget for Gemini 3, and sending it with a level is an error. |
| They asked how to get each value, and what the list of prize pages is. | [`docs/setup-guide.md`](../docs/setup-guide.md), one section for each step. |
| They did not understand open questions Q17 and Q19. | Both are now written in plain words in [`open-questions.md`](open-questions.md). |
| They allowed the assistant to adjust the documents if a real defect shows after research and reasoning (Q20). | Done. The wording was measured and corrected: see "The wording of 'as received'" below. Q20 is answered. |
| They said that their vault is out of the assistant's scope. | The pointers to the vault are removed from the project files. The assistant does not read or write it. |
| They allowed the backlog to be organised into folders. | A folder `sessions/` was added. The numbered entries stay where they are, so that no link breaks. |

## Results

### A Google sign-in file in the project folder

The setup check showed an untracked file `application_default_credentials.json` in the project folder. Only its `type` was read: `authorized_user`, a login with a refresh token. It had never been tracked and was in no commit of any branch. But `.gitignore` did not cover it, so a careless `git add .` would have committed it. Now `.gitignore` covers it and similar files, a test checks the patterns, and a second test scans every tracked file for the shape of a real secret on every push (launch gate 8). The setup check also tells where a sign-in file is and whether git ignores it, and it advises to keep the file outside the project.

### Is a secret of `.env` in the git history?

The first scan was a throw-away script. It took every value of `.env` that is 12 characters or longer and searched all 32 commits. It said LEAK for four of them: the Hedera account ID, the two model names and the Google value. A second tool (the file list of `git grep -l`) showed that all four were false alarms. The account ID is public ledger data and is in the two committed Hedera result files. The model names are public and are in 12 committed files each. The Google value is the 36-character NAME of the sign-in file, with no folder in it. It appears in `.gitignore`, in two test files and in two backlog pages, where it must appear, and no commit ever tracked a file with that name. The scan had searched a name that points to a secret, not the secret.

So the scan became a project command, `python -m hackathon_memory.secret_scan` (`src/hackathon_memory/secret_scan.py`, 26 tests in `tests/test_secret_scan.py`). It searches only the settings that the settings class holds as secrets, and for the Google setting it reads the secret fields inside the file (`private_key`, `refresh_token`, `client_secret`) instead of its name. It looks in three places: the files of every commit of every branch and tag, the messages and author fields of those commits, and the working folder including files that git does not track yet but would pick up (files that `.gitignore` covers are skipped, which is why `.env` itself is not a hit). A value goes to git on the standard input, so it is not in a command line. A git error stops the scan: it is never read as "not found". It prints names and never a value, and a test plants a secret in a repository and checks that it is found and not shown.

**Result on 10 October 2026: clean.** 6 secret values (the Hedera key, the Google project, the `refresh_token` and `client_secret` of the sign-in file, the database password, the contact address) in 32 commits, their messages and authors, and the working folder. The contact address is not the git author address either. As a positive control, the same search with ignored files included finds both fields of the sign-in file, so a "not found" from the normal run means something. This is a check of one day. It must run again before the launch (gate 8).

### The Hedera proof

Two runs. The first failed because of a bug of the Hedera library, the second passed. The story and the numbers are in [05-phase-a.md](05-phase-a.md), section "Proof 2 on the real network".

### The Google proof: three runs

All three used the same real text (the longest of the six published descriptions that the owner copied by hand, 81 words).

| Run (UTC) | Gemini 3.1 Pro, HIGH (rewrite) | Gemini 3.8 Flash, HIGH (search) | Embeddings | Result file |
|---|---|---|---|---|
| 22:47 | valid, 23.6 s | **failed: the answer was not valid JSON** | 3 vectors of 3,072 numbers | `20261009T224704Z-google-models.json` |
| 22:53 | **failed: HTTP 500 "Internal error"** from Google | valid, 40.6 s | ok | `20261009T225310Z-google-models.json` |
| 22:55 | valid, 13.8 s | valid, 46.1 s | ok | `20261009T225549Z-google-models.json` |

Two extra calls of Gemini 3.8 Flash on the same text, with HIGH and with LOW, both returned valid JSON (finish reason STOP). So the invalid answer is intermittent. One failure in five calls of 3.8 Flash is too small a sample to give a rate. One failure in three calls of 3.1 Pro (a server error) is the same.

**What the failures led to** (the commits are listed at the end):

- A bad answer is asked for again, up to three calls in all, and every call is billed and counted. The error now says how the answer failed (the finish reason, the kind of JSON error and its position) and never what it said.
- The library `google-genai` **does not retry a failed request unless it is told to** (read in its source, and shown by a test). Without retry options one 500 ended the call. Now the transient codes (408, 429, 500, 502, 503, 504) are retried up to four calls with growing waits, and a request may last up to five minutes.

### What the first real numbers say (one call each, 81 words of text)

| | Gemini 3.1 Pro, HIGH | Gemini 3.8 Flash, HIGH |
|---|---|---|
| Time | 13.8 s | 46.1 s |
| Tokens in | 1,723 | 1,723 |
| Tokens out | 593 | 478 |
| Thinking tokens | 1,187 | 5,748 |
| Cost of the call | 2.5 cents | 2.5 cents |
| Quotes copied, found in the text | 11 of 11 | 13 of 13 |
| Labels | 6 stated, 1 inferred | 5 stated, 1 inferred, 1 not found |

- Of the 1,723 tokens in, about 1,600 are the instructions and the form. They do not depend on the page.
- At the same level, Flash thinks almost five times more than Pro, and takes three times as long. **A search that makes a person wait 45 seconds is slow.** The level of the search layer is a setting of `.env`, and it is the first thing to test again in Phase D, with the real comparison form. It stays at HIGH until then, as the owner decided.
- Every quote that the two models copied was found in the text. That is a good sign for the quote check of blueprint §6.3, but one short text proves little.
- The Gemini calls of these hours (eight calls that returned an answer, plus the one that failed with a 500) cost about 15 cents of the free credit. This is an estimate from the token counts and Google's prices, not a bill.
- The embedding model works in the location `global`: the question about the text was closer to it than the unrelated question (0.77 against 0.53).

### The wording of "as received"

The rule said that raw pages are saved as received, except the team part. The code writes the page again with an HTML parser, because it needs one to cut. The owner allowed the assistant to correct the documents if research showed a real defect (Q20). So it was measured on the two invented project pages: the team block and the author tag were removed by plain string slicing, and the result was compared with what the real cut saves.

| Compared | Result |
|---|---|
| Visible text, spaces made uniform | Identical |
| Links | Identical (3 and 2) |
| Tags, and their order | Identical (20 and 17) |
| Lines of the markup | Different. The doctype is written `<!DOCTYPE html>`, the spaces and line breaks between tags change, and empty tags get a slash (`<meta charset="utf-8"/>`). |
| Size | The saved page is about a tenth smaller than the page cut by hand (1,177 bytes against 1,358, for the larger sample). |

So the rule was not exactly true, and no program that cuts with a parser can make it true. Keeping every byte would need a cut by character positions, and it still could not keep the data blocks, where the keys that hold people must be removed from inside the JSON. The defect is in the wording, and the wording is corrected in `CLAUDE.md` hard constraint 5, blueprint §5.3 and §5.7, and the README. The fingerprint of what the site sent is kept beside the saved page. A test (`test_the_page_is_written_again_but_text_links_and_tags_stay_the_same`) pins the table above. The numbers come from invented pages. The first real pages will show whether they hold.

### A look at ETHGlobal instead of two saved pages

The owner asked why they must save two pages and whether it is needed. It is needed for the first real run, and for three reasons: where the team part is (a promise to ETHGlobal), which links are the projects, and whether plain HTML is enough. But there is a way that asks nothing of them. `python -m hackathon_memory.collect ethglobal --look` sends at most three requests (robots.txt, the first prize page of their list, the first project that it links to) with the tool's name and their address, prints the shape of the two pages with the skeleton printer (no text, no person), and saves nothing. It also shows early whether ETHGlobal accepts an honest request at all. It is built and tested on fake pages (14 tests, `tests/test_look.py`). **It has never run on the site.** It needs their list, `COLLECT_ETHGLOBAL=on` and their yes for these three pages (hard constraint 17).

## What went wrong

1. **A live call failed in a way that tests could not show**, twice (the Hedera receipt, and the Google JSON and 500). Both times the fix was made at once and tested with the library's own objects. A fake network is useful. It is not a replacement for one real call.
2. **My first test for `setup_check` assumed an empty environment** and failed in CI (entry 05, item 9). The same day, a second weakness of the same kind could have hidden in the Google tests, so the fix covers every setting.
3. **A sign-in file sat in the project folder without protection.** It was found by the setup check, before it did harm.
4. **A long inline shell command failed on a quote and did nothing**, twice. Longer patches are now written to a file first.
5. **My first scan for leaked secrets said LEAK four times, and all four were false.** It searched values that are not secrets (an account ID, two model names) and the name of a file instead of its contents. A second tool showed it within minutes, but a wrong word like LEAK would have alarmed the owner for nothing. The first version of the project command also read any git error as "not found". That was caught by reading it before the commit, and a test now covers it.
6. **The commit of the scan (`7de5ba9`) went to GitHub with a red test.** The test that looks for secret shapes in tracked files flagged the fake key header in the new test file. On the laptop it passed, because I ran the whole suite before `git add`, when the new file was still untracked. CI found it in the first run. The fix is the next commit, which builds the header from parts as the scanner's own test does. Pushed history is not rewritten (`CLAUDE.md` 9.5). From now on: stage first, run the whole suite, then commit.

## What this does not prove

- One real text of 81 words, once for each model. How well the form is filled for full pages, and which thinking level is worth its cost, is measured by Test 1 and in Phase D.
- The reliability of the two models. The failures were seen once each.
- That Gemini 3.1 Pro stays available. It is a public preview model.
- The search layer was tested with the card form. Its own form comes in Phase D.
- The secret scan finds an exact copy of a value. It does not find a changed copy (one character different, split over two lines, or encoded). It does not look at a copy of the repository elsewhere, at GitHub's own caches, or at the transcript of a chat. It does not search a value shorter than 8 characters. A clean result is a good sign, not a proof.

## Next

1. The ETHGlobal inputs from the owner (entry 05, and `docs/setup-guide.md` steps 9 and 9b). Then the real page shape, the plan, the owner's yes and the first run.
2. Q17 and Q19, in plain words in `open-questions.md`.
3. When the fourth proof has passed: the owner decides on the merge and the tag `gate-a`.

## Commits

`21a2534` ignore Google sign-in files and scan for secrets. `bc461a9` the Hedera fix (proof 2 passed). `a39f237` the two Gemini layers, the retries and the Google result files (proof 3 passed). `76d7ef5` the Gemini decision in the rules and the blueprint. `8440fc6` the corrected wording of "saved as received", with Q17 and Q19 in plain words. `09e6458` the vault out of scope. `d00d8c5` the setup guide. `2d38522` the look at ETHGlobal. `5644447` the sessions folder and the hand-over note. `7de5ba9` the secret scan. `8fa8aeb` the fix of a red test in it (item 6 of "What went wrong"). The commit that adds this list closes the entry for now.
