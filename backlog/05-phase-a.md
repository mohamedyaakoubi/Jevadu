# 05 · Phase A: setup and the four small proofs

- **Dates:** 9 October 2026, from the evening
- **Status:** in progress. Gate A is open: one proof passed, three wait for the owner.
- **Branch:** `phase-a-proofs`
- **Blueprint:** §14.2 (Gate A), §11 (tech stack), §5.7 (promises to the sites), §9 (the topic)

## Goal

Set up the project, then run the four small proofs of Gate A (blueprint §14.2):

| Proof | It passes when |
|---|---|
| Lists | The ETHGlobal collector is written, keeps every promise of §5.7, and passes its tests on saved sample files. The live run comes after the owner's yes and their hand-checked list of prize pages. |
| Hedera write | A topic is created on the test network with no admin key and one submit key. A small message is posted and the mirror node returns it. |
| Google models | One call to each Gemini layer (3.1 Pro to read, 3.8 Flash to search) returns a valid form. One embedding call returns a list of the expected size. |
| Database | PostgreSQL with pgvector runs in Docker and answers one vector query. |

## Approach

- Verify before building (`CLAUDE.md`, section 1). Every library shape below was read from the installed package, and every Google fact from Google's own page, on the day the code was written.
- Build in small commits on this branch. Every commit passes its tests.
- Build everything that needs no secret first. The Hedera and Google proofs need values that only the owner can create (blueprint §15), so their code is written and tested with fakes, and the real run waits for `.env`.

## Method

Commands to repeat the setup, from the project folder, on Windows:

```text
python -m venv .venv                        # Python 3.11.9 at C:\Users\MSI\AppData\Local\Programs\Python\Python311\python.exe
.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env                      # then fill in your own values
docker compose up -d --wait db              # needs Docker Desktop to be running
.venv\Scripts\python -m hackathon_memory.db migrate
.venv\Scripts\python -m pytest
.venv\Scripts\python -m hackathon_memory.setup_check   # which setup steps are done; prints no value
.venv\Scripts\python -m proofs.database                # Gate A proof 4, a result file in proofs\results
.venv\Scripts\python -m proofs.hedera_write            # proof 2, needs HEDERA_OPERATOR_ID and _KEY
.venv\Scripts\python -m proofs.google_models           # proof 3, needs the Google values
.venv\Scripts\python -m hackathon_memory.collect ethglobal --plan   # proof 1, no request is sent
```

`setup_check` answers the first question of `backlog/INDEX.md` ("which setup steps of blueprint §15 are done?") without asking: it reads `.env`, says "set" or "empty" for each value, tells whether a key has a valid form, tries the local database, lists the latest result file of each proof, and names what blocks each proof.

On this laptop the tool shells do not see the programs. Docker also needs its own folder on `PATH`, because the `docker` program calls a helper (`docker-credential-desktop`) that sits next to it. The commands that worked:

```text
$env:PATH = 'C:\Program Files\Docker\Docker\resources\bin;C:\Windows\System32;C:\Windows;' + $env:PATH
```

## Results

### Gate A, state of the four proofs

Update this table in every commit that changes a proof.

| Proof | State | Evidence |
|---|---|---|
| Database | **Passed** on 9 October 2026 | `proofs/results/20261009T175503Z-database.json` |
| Lists (ETHGlobal) | **Written and tested on invented pages. The live run is open.** | Tests that never touch a site ([below](#proof-1-the-collectors)). The live run waits for five things from the owner, listed in that section. |
| Hedera write | **Passed** on 9 October 2026 (22:39 UTC) | `proofs/results/20261009T223958Z-hedera-write.json`. The first run, 20 minutes earlier (`20261009T223818Z-hedera-write.json`), failed because of a bug in the library: see "Proof 2 on the real network" below. |
| Google models | **Passed** on 9 October 2026 (22:55 UTC), for both layers | `proofs/results/20261009T225549Z-google-models.json`. Two earlier runs failed, on a bad answer and on an HTTP 500: see [06](06-live-proofs.md). |

### Proof 4, the database (9 October 2026)

Run with `python -m proofs.database`. It plants 3 known neighbours among 3,000 random vectors of 3,072 numbers, and asks the real server for the 10 nearest.

| Check | Result |
|---|---|
| Server and add-on | PostgreSQL 17.11, pgvector 0.8.7, inside Docker |
| 3,072-number vectors stored | 3,000 rows in 0.31 seconds |
| The planted neighbours come first, in the right order | Yes: ids 1, 2, 3 |
| The database distance against an independent computation in Python | The largest difference is 0.00000013 |
| An exact search with no index | Median 27 ms, slowest 30 ms, over 20 runs |
| Blueprint §11.6, claim 1: the normal index stops at 2,000 numbers | **Confirmed.** The server said: "column cannot have more than 2000 dimensions for hnsw index". |
| Blueprint §11.6, claim 2: the half-size type gives an index that works | **Confirmed.** The index was created and the planner used it. |

So the blueprint's claim "at our size the exact search needs no index" now has a measurement behind it, and so does its fallback.

### Proof 1, the collectors

No collector runs against a live site before the owner says yes for that site (hard constraint 17). The code is written and tested on invented pages. Nothing in this entry sent a request to any site.

**The polite request layer** (`src/hackathon_memory/collect/polite.py`). Blueprint §5.7 lists the promises that were made to ETHGlobal and to the other sites. Each promise is now code, and each has a test (`tests/test_polite.py`):

| The promise | The code | The test |
|---|---|---|
| Only the pages we named | `allow` is checked before every request and on every redirect. A redirect to a page outside the list stops the run. | An address outside the list is never requested. A redirect to a login page is not followed. |
| A limit of 300 requests | `max_requests`, counted for every request and every redirect | The run stops at exactly the limit. The default is 300. |
| One request at a time, two seconds apart | A lock, and a pause that is measured from the end of the last request | Two seconds between three requests. Three threads never overlap. |
| The tool's name and the owner's address in each request | `CollectorIdentity`: `User-Agent` and `From` headers. The run refuses to start when one is empty or wrong. | Every request carries both. The address is not printed by `repr()`. It is not in the saved meta files. |
| A stop switch for each site | `is_enabled`, read again before every request | A switch turned off during a run stops it before the next request. |
| Stop after repeated errors | Five errors in a row stop the run. A good answer resets the count. | Tested with a count of five and of three. |
| Never work around a block | The answers 401, 403, 429 and 451, or a bot-challenge header, stop the run at once, with no second try | One test for each answer. |
| Never sign in | No cookie is kept, `~/.netrc` and the proxy of the environment are ignored, no login | Tested on the client |

Two more things the layer does that nobody asked for, because a polite collector needs them: it reads `robots.txt` with a reader of our own (`robots.py`, RFC 9309) and obeys it, including `Crawl-delay`. Python's own reader does not understand the wildcards `*` and `$`, so a rule such as `Disallow: /*?draft=` would be missed. And it refuses an answer larger than 5 MB.

**The raw store** (`rawstore.py`). A saved page is two files in `data/raw/<site>/`: the page, and a small meta file with its address, the date, its status, two fingerprints (of what was saved and of what the site sent), the cut that was applied, and the name of the collector. The name of a page is the fingerprint of its address, so the same page always gets the same name. A page is written once. A second save of the same address is an error, and a half-written page (a crash) does not count as saved. The meta file holds no address of a person. A test checks the exact list of its fields.

**The team cut** (`teamcut.py`). The sites were promised that no names, photos or profiles of team members are collected, so the part of a page that shows the team is removed before the page is saved. I could not look at a real ETHGlobal page (hard constraint 18), so the cut cannot rely on knowing the page. It fails closed, with three guards:

1. A rule marked `required` must find its element. If the team block is not where we expect it, the page is not saved and the run stops (`TeamShapeChanged`).
2. In data blocks (JSON in script tags) the keys that hold people are removed by name, for example `members`.
3. A self-check. Before the cut, the texts and the link, image and label values of the team block are collected in memory. After the cut, the page must contain none of them. A text that also stands somewhere else as visible text on the page (a menu word, the heading "Team") counts as generic and is not searched. A name that was copied into a script block is not generic, so it is found, and the page is refused (`TeamTextRemains`). That one page is skipped and the run goes on. Three skipped pages in a row stop the run, because that means the shape is wrong.

The list of what was found is never printed, saved or put in an error message. An error says only how many.

**The ETHGlobal collector** (`ethglobal.py`, run with `python -m hackathon_memory.collect ethglobal`). What a live run does, in this order:

1. It checks the switch `COLLECT_ETHGLOBAL`, the tool's name and the owner's address, the owner's hand-checked list of Hedera prize pages (`data/by-hand/ethglobal.com/prize-pages.txt`), and that the page shape has been checked against a real page. If one is missing it refuses and sends nothing.
2. If any page is missing from the store, it reads `robots.txt` first (one request), keeps the copy, and obeys it.
3. It reads each prize page on the list, then only the `/showcase/<project>` pages that those prize pages link to. Any other address is refused by the allow-list, also after a redirect.
4. Each page goes through the team cut before it is saved. A record of the run, with counts and addresses and no page text, is written to `data/runs/`.
5. A second run skips every page that is saved. When nothing is missing it sends no request at all (a test checks this).

`python -m hackathon_memory.collect ethglobal --plan` shows all of this for the real settings without sending a request. It never prints the owner's address.

**The skeleton printer** (`skeleton.py`). To write the real page shape someone must read a real page, and a real page shows names of people. The tool prints the shape of a saved page and none of its text: every text is shown as its length, a heading only if it is one of a few plain section words ("Team", "Project Description"), a link as its host and the shape of its path (`/hackers/{x}`), a data block as keys and kinds of values, a map from handles to records as "map of N records", and a meta tag by its name. Tests check on the invented pages that no name and no page text comes out. What it can still show is the class name or id of an element, the host name of a link, and the keys of a data block. If a class name held a person's name, it would show.

**Why the live run is still closed.** `CLAUDE.md` section 1 says to look at a real page before writing a collector, and hard constraint 18 says that only a tool carrying the owner's address may read ETHGlobal. So the page shape in the code (`ETHGLOBAL_SHAPE`) is a guess, marked `verified_on=None`, and the collector refuses to run live with it. A test checks that it refuses.

**What the owner must give before the first live run** (the order does not matter):

1. Their hand-checked list of Hedera prize pages (blueprint §15, step 9), one address per line, in `data/by-hand/ethglobal.com/prize-pages.txt`. The first list from a web search is in entry 04.
2. Their contact address in `.env` (`COLLECTOR_CONTACT_EMAIL`). The tool's name is already set.
3. Two pages saved by hand from their browser (Save page as, "Webpage, HTML only"): one Hedera prize page and one project page that it links to, into `data/by-hand/ethglobal.com/samples/`. The assistant reads them only with `python -m hackathon_memory.collect.skeleton <file>`, writes the real shape, and sets `verified_on`.
4. Their answer to open question Q19: did they change the email to ETHGlobal before they sent it? The promises in §5.7 come from the draft.
5. Their yes, one more time, when the assistant tells them exactly which pages the first run will read (`--plan`). The yes of 9 October is recorded in `decisions.md`; hard constraint 17 asks to name the pages before the first live run.

Then they set `COLLECT_ETHGLOBAL=on` in `.env`, and the run starts.

### What the cut does not prove (the honest limits)

- It was tested on invented pages only. Whether it works on a real ETHGlobal page is not known. `ETHGLOBAL_SHAPE.verified_on` is `None`, and the collector refuses a live run until the owner has saved a real prize page and a real project page by hand and the shape is written from them.
- A name that stands as a whole visible text elsewhere on the page is treated as generic and is not searched. For example, "Winner: Alice" next to a team block that lists Alice. The first live pages must be read by the owner before the others are kept.
- The saved page is the page after the HTML parser has written it again, so spaces and quotes in the markup are normalized. The text, the links and the data are the same. The fingerprint of what the site sent is kept in the meta file. This is a small step away from "as received" (hard constraint 5), and it is needed to remove the team part.
- Photos: an avatar image inside the team block is removed with the block. A person's photo elsewhere (for example a page image that is a team photo) is not known to the cut.

### Proof 2, the Hedera write

**Read before writing code (9 October 2026).**

| Question | Answer | Source |
|---|---|---|
| What does the mirror node return for a topic? | `topic_id`, `admin_key` (null or `{_type, key}`), `submit_key`, `memo`, `deleted`, `created_timestamp`, `auto_renew_account`, `timestamp`. So the keys of blueprint §9.5 can be proved from the ledger. | A real read of the test network |
| For a topic message? | `sequence_number`, `message` (base64), `consensus_timestamp`, `payer_account_id`, `running_hash`, `topic_id`, `chunk_info`. | A real read of the test network |
| For an account? | `key` is `{_type: "ED25519" or "ECDSA_SECP256K1", key: hex}`. A public key is 64 letters for Ed25519 and 66 for ECDSA (the compressed form). The library gives the same forms. | A real read, and the installed library |
| Does a topic without an admin key work? | "If no Admin Key is specified, the topic is immutable." The tutorial of Hedera sets an admin key, ours must not. | `docs.hedera.com/native/consensus/create-topic` |
| Auto-renew account | The library gives the payer as auto-renew account when none is set. Hedera's page says that since network version 0.60 an auto-renew account needs no admin key, and "rent is not enforced for topics so no auto-renew payments will be made". Older protocol notes say the opposite (`AUTORENEW_ACCOUNT_NOT_ALLOWED`). | The same page, and a search of the Hedera documentation |
| Hedera-style private keys | Both wrappers that the portal prints (`302e…` for Ed25519, `3030…` for ECDSA) load with `from_string_der`. A raw 64-letter key is read as Ed25519 by the generic loader, also when it is ECDSA. | The installed library, tested |

**What was built.** `hedera/keys.py` loads the operator key and checks it against the account's public key on the ledger, before anything is sent. `hedera/mirror.py` is the read-only client. `hedera/register.py` creates the topic (no admin key, one submit key) and posts a record, and refuses any network other than the test network. `proofs/hedera_write.py` is the proof.

**What the proof does**, in order: the account exists and has a balance; the key in `.env` is the key of that account; a topic is created; the mirror node shows no admin key and our submit key; a record of the fixed form of blueprint §9.3 (version 0, event, fingerprint, 110 bytes) is posted and the mirror node returns the same bytes from our account; and a negative control, a second topic whose submit key belongs to a stranger, must refuse our message. If the network answers `AUTORENEW_ACCOUNT_NOT_ALLOWED`, the topic is created again without an auto-renew account, and the result file says which of the two worked.

**What the offline tests show** (`tests/test_register.py`, `test_hedera_keys.py`, `test_mirror.py`, `test_proof_hedera.py`, 63 tests): the transaction body that would be sent has no `adminKey` and has a `submitKey`; the library's default auto-renew account is there, and the careful path removes it; a record of 1,025 bytes is refused and one of 2,000 would be cut in two by the library; a key never appears in the printed lines or in the result file, also when the library repeats it in an error and also when the cut of a long message would split it; a wrong key, an admin key on the ledger, an altered message and a stranger who can post each make the proof fail. Two tests are marked as traps: they go red if the library fixes its habit of printing keys, and then the guard can be relaxed.

**What the owner does to run it** (about five minutes, blueprint §15 step 1): create a free test account at `portal.hedera.com`, put the account id in `HEDERA_OPERATOR_ID` and the DER encoded private key in `HEDERA_OPERATOR_KEY` in `.env`, and run `python -m proofs.hedera_write`. The test money is free. The key never goes into a chat.

### Proof 2 on the real network (9 October 2026, 22:38 and 22:39 UTC)

The owner created a test account and filled `.env`. `setup_check` said that nothing blocked the proof, and it ran.

**The first run failed, and the failure was a bug of the Hedera library, not of the network.** The topic was created and checked, and the message was posted. Then the library raised `ValueError: Field proto.TransactionReceipt.topicRunningHash does not have presence` when my code read `receipt.topic_running_hash`. The library asks the protobuf whether a bytes field is "present", and a bytes field has no presence, so this property fails every time in hiero-sdk-python 0.2.10. A read of the ledger showed that the message was there: topic `0.0.10961137`, one message of 102 bytes, from the owner's account. My offline tests had used a hand-made receipt, and it had hidden the bug. The tests now build the library's own receipt from protobuf, which raises the same error, and a test pins it. The code reads the running hash from the protobuf directly.

**The second run passed.** Everything in the table below is from the result file.

| Check | Result |
|---|---|
| The key in `.env` belongs to the account | Yes, compared with the public key on the ledger (type ECDSA_SECP256K1) |
| The topic `0.0.10961154` has no admin key | Confirmed by the mirror node: `admin_key` is null |
| Our key is the only submit key | Confirmed |
| The auto-renew account (the library default) | **The network accepted it.** The old rule `AUTORENEW_ACCOUNT_NOT_ALLOWED` does not apply on the test network today, so the documents of Hedera that disagreed are settled for now. The fallback stays in the code. |
| The record | 102 bytes, version 0, in the fixed form of blueprint §9.3 |
| The mirror node returns the same bytes, from our account | Yes. The topic appeared after 6.3 seconds and the message after 2.2 seconds. |
| A topic whose submit key is a stranger's | Refused our message with `INVALID_SIGNATURE` |
| Cost on the test network | About 0.22 test HBAR for two topics and two messages (one refused). Test money is free. |

The links to open in a browser are in the result file: `topic_link` and `message_link` (HashScan). Launch gate 3 needs one such link for the real register, in Phase F.

### Proof 3, the Google models

**Read before writing code (9 October 2026).** The facts are in the table "Facts read from the installed source". The requests were then captured: the real library, with only the network replaced, builds `POST …/locations/global/publishers/google/models/gemini-3.8-flash:generateContent` with the system instruction, the converted form (all seven fields), thinking level LOW, a limit of 8,192 output tokens and no temperature, and `POST …/gemini-embedding-001:predict` with the task type and 3,072 as the size. Tests pin all of this.

**What was built.** `llm/card_form.py` is the form that the LLM fills (blueprint §4.1, §4.3, §4.5): seven fields, each with a label and quotes, and a category from the fixed list of 16. It is the one place that says what an LLM field is, and Phase D builds the quote check on it. `llm/client.py` makes the client from the settings (it reads a service account key or a user login file, and nothing else). `llm/gemini.py` fills the form with checks on the answer. `llm/embeddings.py` makes the embeddings, with the two modes. `proofs/google_models.py` is the proof.

**What the proof does.** It sends the longest of the six published descriptions that the owner copied by hand (`data/by-hand/hol.org/`) to Gemini, checks the answer against the form, then makes three embeddings: the text as a document, a question about it, and an unrelated question. It checks that each has 3,072 numbers and that the related question is closer. It records the tokens and the cost. The result file holds counts, labels and prices, and no text.

**What the offline tests show** (`tests/test_llm.py`, `test_llm_client.py`, `test_proof_google.py`, 39 tests): the requests above; a valid answer becomes a card and its cost is computed with Google's price (0.0026 dollars for 1,000 tokens in and 500 out); an answer that breaks the form (a wrong label, a category outside the list, seven steps, text in a field labelled not found, a missing field, text that is not JSON) is refused, and the error never repeats the page or the answer; a location that Gemini 3.8 Flash is not offered in is reported before any request; a vector of the wrong size or the wrong number of vectors is refused; and a Google error that names the project is scrubbed from the result file.

**What the owner does to run it** (blueprint §15 step 3): make the Vertex AI project ready, sign in with `gcloud auth application-default login` (or put the path of a key file in `GOOGLE_APPLICATION_CREDENTIALS`), set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION=global` in `.env`, and run `python -m proofs.google_models`. The location must be `global`, `us` or `eu`. The cost is a fraction of a cent.

**One thing the live run can still show.** The embedding model might not be offered in the location `global`. The code does not guess: the proof reports the error, and a separate setting for the embedding location is added only if that happens.

### The start (9 October 2026)

| Step | Result |
|---|---|
| Branch | `phase-a-proofs` created from `main` before the first line of code. |
| `.env` | Did not exist, so none of the owner's setup steps (blueprint §15) were recorded yet. The assistant created `.env` from `.env.example` with a random password for the local database. Every other value is empty and is the owner's to fill in. The file is ignored by git (checked with `git check-ignore`). |
| Docker Desktop | Installed (29.2.1) but not running. The assistant started it. |
| Python packages | Versions read from PyPI on 9 October 2026 and installed together. `pip check` found no conflict. |
| The database image | `pgvector/pgvector` has the tags `pg17` and `pg18` (Docker Hub, updated 1 October 2026). The project uses `pg17`: it is supported until 2029, most hosts offer it, and version 18 changed the layout of the data folder. The running server is PostgreSQL 17.11 with pgvector 0.8.7. |

### Packages (checked on PyPI, 9 October 2026)

| Package | Version | Why it is here |
|---|---|---|
| hiero-sdk-python | 0.2.10 (pinned exactly: the authors label it pre-alpha) | The Hedera write (blueprint §11.1) |
| google-genai | 2.29.0 | Gemini 3.8 Flash and the embedding model |
| psycopg, pgvector | 3.3.6, 0.5.1 | The database |
| pydantic, pydantic-settings | 2.14.0, 2.15.0 | Typed records and settings (blueprint §11.6: "bad data is stopped at the door") |
| requests, beautifulsoup4, lxml | 2.34.2, 4.15.0, 6.1.3 | The collectors (blueprint §11.1) |
| pytest, ruff | 9.1.1, 0.16.10 | Tests, and a linter that also checks for secrets in code |

Playwright is not installed. The only allowed source today is ETHGlobal, and nothing shows yet that it needs a real browser. It is added with the first collector that needs it.

### Facts read from the installed source (9 October 2026)

`CLAUDE.md` section 1: never write a library's shape from memory. These facts come from the files inside `.venv\Lib\site-packages`.

**hiero-sdk-python 0.2.10** (the files `consensus/topic_create_transaction.py`, `consensus/topic_message_submit_transaction.py`, `transaction/transaction.py`, `crypto/private_key.py`, `client/client.py`)

| Question | What the source says |
|---|---|
| Does a topic get an admin key by default? | No. `TopicCreateTransaction(admin_key=None, submit_key=None)`. A topic has an admin key only if `set_admin_key` is called. A test must still check that ours has none. |
| How is the submit key set? | `set_submit_key(key)`. It takes a private key or a public key. |
| Who signs? | `execute(client)` signs with the operator key by itself. If the submit key is the operator's own key, no second signature is needed. |
| How big is a message? | `TopicMessageSubmitTransaction` cuts a message into chunks of 1,024 bytes (the default), up to 20 chunks. Our record must fit in one chunk. |
| Auto-renew | `freeze_with(client)` sets the auto-renew account to the operator when none is given. Whether the network accepts this for a topic with no admin key is shown only by the live proof. |
| Which settings names does it read? | Only `Client.from_env()` reads `OPERATOR_ID`, `OPERATOR_KEY` and `NETWORK`. We do not use it. We build the client from our own settings, so our names need no change. |
| Receipt fields | `topic_id`, `topic_sequence_number`, `topic_running_hash`, `transaction_id`. |

Three traps for secrets, found in the same files:

1. `PrivateKey.__repr__` prints the whole private key (`<PrivateKey (Ed25519) hex=...>`). A print, a log line, a failed assertion or a traceback that shows the object would leak it.
2. `PrivateKey.from_string` puts the key text into its error message when the text is not valid hex.
3. A key of 32 bytes (64 hex letters) is read as Ed25519 first, even if it is an ECDSA key. The signature is then wrong and the network refuses the transaction. So `.env` asks for the DER form of the key, which says which type it is. The register code will also compare the public key with the one that the mirror node shows for the account.

**google-genai 2.29.0** (the files `client.py`, `models.py`, `types.py`, `_transformers.py`)

| Question | What the source says |
|---|---|
| Name of the platform | Google now says "Gemini Enterprise Agent Platform" for what was Vertex AI. `Client(enterprise=True, project=..., location=...)` is the current form. `vertexai=True` is kept as a legacy flag. |
| Which names does it read? | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GOOGLE_GENAI_USE_ENTERPRISE`, `GOOGLE_GENAI_USE_VERTEXAI`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`. Our names match the first two. The code passes every value in, so no other name is needed. |
| How is the embedding call routed? | For `gemini-embedding-001` the library uses the batch route (`predict`). For every other Gemini embedding model it uses `embedContent`, which takes one text at a time. |
| Thinking level | `ThinkingConfig(thinking_level=...)` with `LOW`, `MEDIUM`, `HIGH`. The enum also holds `MINIMAL`, but Google's guide says Gemini 3.8 Flash refuses it. |
| Structured output | `GenerateContentConfig(response_mime_type=..., response_schema=... or response_json_schema=...)` |
| Token counts | `usage_metadata.prompt_token_count`, `candidates_token_count`, `thoughts_token_count`, `total_token_count` |
| Embedding result | `response.embeddings[i].values` is a list of floats. |

**Google's own pages, read on 9 October 2026**

| Fact | Where |
|---|---|
| Model ID `gemini-3.8-flash`. Generally available since 2 September 2026. Context 1,048,576 tokens in, 65,536 out. Offered in the locations `global`, `us` and `eu`. Structured output is supported. | Model page on `docs.cloud.google.com` |
| `temperature`, `top_k` and `top_p` are ignored by the backend, and Google says to remove them. The Python example uses `Client(enterprise=True, project=..., location="global")`. Thinking levels: `LOW`, `MEDIUM` (the default), `HIGH`. `MINIMAL` returns an error. | Developer guide, last updated 7 October 2026 |
| Price of Gemini 3.8 Flash: 0.75 dollars per million tokens in and 3.75 out until 31 December 2026, then 1.50 and 7.50. Thinking tokens are counted as output. | Gemini API price page on `ai.google.dev` (the Agent Platform price page could not be read by the reader because JavaScript builds it) |
| `gemini-embedding-001`: 3,072 numbers by default. Each text is cut at 2,048 tokens, silently. Up to 250 texts and 20,000 tokens per request. Use `RETRIEVAL_DOCUMENT` for stored texts and `RETRIEVAL_QUERY` for questions. The page still calls it "our large model designed to provide the highest performance". | Embeddings page and task types page |
| `gemini-embedding-2` exists: 8,192 tokens, one text per request, no task type. It costs 0.20 dollars per million text tokens. | Embeddings page and the Gemini API price page |

Not read: the price of `gemini-embedding-001` (the Gemini API price page has no row for it). The blueprint's estimate of 20 to 30 cents for all embeddings stays an estimate until the first run counts the tokens.

## What went wrong

Each row is also in [`lessons.md`](lessons.md) when it gives a rule.

1. **A database connection hung for ever.** The first test run did not finish in 5 minutes. A stack dump (Python's `faulthandler`) showed the wait: opening a connection to `localhost`. On this laptop Docker Desktop answers on the IPv6 address and never replies. The fix: connect to `127.0.0.1`, which is also the only address that the compose file opens, and set a connect timeout of 10 seconds. A test now checks both.
2. **The hang was invisible.** The run was piped into a "last lines" filter, which shows nothing until the program ends. Long runs now write to a file that is read while they run.
3. **The first settings class would have printed the owner's contact address.** Plain text fields show their value in `repr()`. Every setting that is not public is now a `SecretStr`, and a test fails if a new private setting is added as plain text.
4. **Docker could not start the database.** `docker compose up` failed with "docker-credential-desktop not found". The `docker` program was called by its full path, but the helper that it calls sits in the same folder, and that folder was not on the `PATH` of the tool shell. The fix is to put the folder on the `PATH` for the call.
5. **A test of mine expected the wrong thing.** I wrote that a name in a project's own description is "kept on purpose". The cut refused that page, which is safer. The test was wrong and the cut was right. It led to a better design: a page whose shape is wrong stops the run, and a page that has team text elsewhere in it is skipped, and three skipped pages in a row stop the run.
6. **Two numbers were written from memory and were wrong.** A commit message said that 14 tests used the real database (the number is 5), and this entry said 72 and 38 tests (the numbers are 63 and 39). I corrected both before anything was pushed that depended on them.
7. **A note in `.env.example` claimed a check before it was made.** The check came a few minutes later and the claim was true, but the order was wrong.
8. **A combined shell command failed on a quote and did nothing.** Nothing was changed. The steps were done again one at a time.
9. **A new test failed in CI and passed on the laptop.** It assumed that `POSTGRES_PASSWORD` is empty. CI sets it in the environment, so the test connected to a real service. The fix (`4cdfac7`): every test starts with no setting in the environment, and I checked it by running the tests with hostile values set. CI found it because it is a second, different machine.

## What this does not prove

- **Gate A is not passed.** One proof of four has run on its real service. The other three have never touched their real service.
- The settings, the migration runner and the tests run on two machines: this laptop (Windows, Docker Desktop) and one GitHub runner (Ubuntu 24.04). A stranger starting from a clean copy with the commands of the README is launch gate 1, and has not been tried by a person.
- The database proof uses random vectors. It shows that the database stores and compares 3,072 numbers correctly. It does not show how well real embeddings find similar projects. That is Test 2.
- The timings come from one laptop and 3,000 rows. They are not a promise for a server.
- The Hedera code is tested against the library's own transactions and an in-memory ledger. The real network may behave differently: the question of the auto-renew account is exactly such a case, and Hedera's documents disagree with each other.
- The Google code is tested through the real library with a fake network. The model may refuse the location, the schema or the thinking level in ways that the pages of Google do not say. The live run shows.
- The collector was never run against a site. Its page shape is a guess until a real page is read. Its team cut was tested on invented pages only.
- No number of this entry about the quality of the AI fields, the search or the proof rule exists. Those come in Phases D and G.

## Next

1. The owner gives the values in the table at the top of `backlog/INDEX.md`. Then the assistant runs `setup_check` and the proofs, and writes each result here with its date.
2. The ETHGlobal page shape, from two pages that the owner saves by hand. Then the plan, the owner's yes, and the first run.
3. When the four proofs have passed: the owner decides on the merge into `main` and on the tag `gate-a`. Then Phase B.

## Commits of this step

`4c43d2c` project, settings, database and migrations. `43cf692` database proof. `c011dc9` polite request layer. `ab7689c` raw store and team cut. `e3d12e4` ETHGlobal collector and skeleton printer. `de10509` Hedera write. `2af2434` Gemini and embedding calls. `58a3991` pinned versions. `a29c76d` setup check. `e309498` and `472c386` CI. `3e5d31f` README and handover. `fb1c215` the hint for a wrong database password. `4cdfac7` tests start without settings in the environment. Later commits that fix or document this step are in `git log phase-a-proofs`.

## 10 October 2026, evening: the fourth proof passed

The lists proof, the last open one of Gate A, passed on the real site. The story is in [entry 10](10-ethglobal-walk-and-first-run.md).

| Proof of Gate A | Result file | Passed on |
|---|---|---|
| Database | `proofs/results/20261009T175503Z-database.json` | 9 October 2026 |
| Hedera write | `proofs/results/20261009T223958Z-hedera-write.json` | 9 October 2026 |
| Google models | `proofs/results/20261010T155247Z-google-models.json` (the newest of four) | 9 and 10 October 2026 |
| Lists | `proofs/results/20261010T194925Z-lists.json` | 10 October 2026 |

So every proof of Gate A works on the real service (blueprint §14.2). **The gate itself is the owner's word:** the merge of `phase-a-proofs` into `main` and the tag `gate-a` wait for their yes (Q27, `CLAUDE.md` section 9.7).

The three lines that end a phase (`CLAUDE.md`, section 8):

- **What changed:** from an empty folder to a tested base: settings that cannot print a secret, a database with migrations, a polite collector that keeps each promise to a site in code, a write to a Hedera topic with no admin key, two Gemini layers with every call counted, and 92 real pages on disk. 614 tests, four proof results.
- **What could not be verified:** that the showcase list of ETHGlobal is complete, and that it stood still during the walk (one page end was compared by hand). That our count of the model costs equals Google's bill. That the parser can read the 92 pages: nothing has parsed them yet.
- **What to clean up next:** `collect/ethglobal.py` has grown to about 650 lines and does four jobs (the page check, the run, the paths, the plan). Split it when Phase B adds the parser next to it. The look (`--look`) has no use any more now that the walk and the run are done: keep it only if a second site needs it.
