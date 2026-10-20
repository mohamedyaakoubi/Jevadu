# Setup guide: how to get each value of `.env`

Written for the owner, who is not a software engineer. Every step says where to click, what to copy, and where to put it. The steps are numbered like the lines of `python -m hackathon_memory.setup_check` and like section 15 of the blueprint.

**The rules for every value**

- The values go into the file `.env` in the project folder, and nowhere else. Open it in VS Code. One value per line: `NAME=value`. No quotes, no spaces around the `=`.
- Never paste a key, a token or a password into a chat. If you did by mistake, make a new one and delete the old one.
- `.env` is never committed to git. The file `.env.example` shows the names, with no values.
- To see what is still missing, run `.venv\Scripts\python -m hackathon_memory.setup_check`. It prints "set" or "empty" and never prints a value.
- To check that none of your secrets ever went into git, run `.venv\Scripts\python -m hackathon_memory.secret_scan`. It looks for the value of each secret in every commit, in the commit messages and in the files git would pick up. It prints the name of each setting and "not found" or "FOUND", and never a value. If it says FOUND, tell the assistant before you do anything else: a secret that reached git must be replaced with a new one.

| Step | Names in `.env` | Needed for |
|---|---|---|
| 1 | `HEDERA_OPERATOR_ID`, `HEDERA_OPERATOR_KEY` | The Hedera proof, and the register |
| 2 | `GITHUB_TOKEN` | The facts about code (from Phase B). Not needed for Gate A |
| 3 | `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, the sign-in | The two Gemini models and the embeddings |
| 4 | `POSTGRES_PASSWORD` | The local database |
| 8 | `COLLECTOR_NAME`, `COLLECTOR_CONTACT_EMAIL` | Every request to a site |
| 9 | A list file, and two saved pages (not in `.env`) | The first run on ETHGlobal |

---

## Step 1. A Hedera test account

Test money is free. Never use a key of the main network.

1. Open `https://portal.hedera.com/register`, register and log in.
2. In the network menu choose **Testnet** and create an account.
3. The portal shows an **Account ID** (it looks like `0.0.12345678`) and several keys. Copy the **DER Encoded Private Key**. It is a long text that starts with `30`. Do not use the short "HEX Encoded Private Key" of 64 letters: it does not say if it is an ED25519 or an ECDSA key, and the Hedera library guesses wrong for ECDSA.
4. In `.env`:
   ```text
   HEDERA_OPERATOR_ID=0.0.12345678
   HEDERA_OPERATOR_KEY=30...the long text...
   ```
5. Check: the setup check should say `set, a valid ECDSA key` (or ED25519). Then run `.venv\Scripts\python -m proofs.hedera_write`.

Notes: the portal gives 1,000 test HBAR to a new account (Hedera's page). When Hedera resets the test network, the account id changes and the key stays. If the proof says that the account does not exist, look up the new id in the portal.

## Step 2. A GitHub token

**Which kind:** a **fine-grained personal access token**. Not the "classic" one, which GitHub calls less secure. A fine-grained token that reads only public things needs **no permission at all**: GitHub says that every fine-grained token includes read-only access to all public repositories.

1. On github.com click your picture (top right), then **Settings**.
2. In the left menu, at the bottom, click **Developer settings**.
3. Click **Personal access tokens**, then **Fine-grained tokens**, then **Generate new token**.
4. **Token name:** `hackathon-memory-read`.
5. **Expiration:** 60 days. The event ends on 20 October. You can make a new token later.
6. **Resource owner:** your own account.
7. **Repository access:** choose **Public repositories (read-only)**. If you do not see these words, choose "Only select repositories" and select none.
8. **Permissions:** add none. Leave everything at "No access".
9. Click **Generate token**. Copy the text that starts with `github_pat_` at once and put it in `.env`: `GITHUB_TOKEN=github_pat_...`. If you lose it, delete the token on the same page and make a new one.

What it gives: 5,000 requests per hour, instead of 60 without a token (GitHub's page on rate limits). The tool sends one request at a time. It can only read public things.

The tool does not read GitHub until you say yes (open question Q17 in `backlog/open-questions.md`).

If the fine-grained form gives you trouble, a **classic** token with **no box ticked** also works: GitHub says a token with no scopes can only access public information. It is the second choice.

## Step 3. Google Cloud

You already have a project that works. This is the list of what each value is.

1. **`GOOGLE_CLOUD_PROJECT`** is the **Project ID**, not the project name. Open `console.cloud.google.com`, click the project menu at the top, and copy the ID (it looks like `my-project-123456`).
2. **`GOOGLE_CLOUD_LOCATION=global`**. Gemini 3.1 Pro is offered only in `global` (Google's model page). Gemini 3.8 Flash and the embedding model work there too.
3. **The sign-in.** Choose one way.
   - **Best:** install the Google Cloud CLI (`gcloud`), then run `gcloud auth application-default login` and sign in in the browser. Leave `GOOGLE_APPLICATION_CREDENTIALS` empty. The sign-in file stays in your user folder, outside the project. To find it, run `gcloud info`. To remove the sign-in later, run `gcloud auth application-default revoke`.
   - **A file named in `.env`:** put its path in `GOOGLE_APPLICATION_CREDENTIALS`. It must be a service account key or the file that the command above writes. **Keep it outside the project folder.** If it is inside, `.gitignore` keeps it out of git (checked by a test), but a file in the project folder is one careless command away from a commit.
   - **Warning:** that file holds a refresh token. It is a long-lived login to your Google account. Anyone who has the file can spend your credit. Never send it.
4. **The two Gemini lines.** They are your choice of 9 October 2026:
   ```text
   GEMINI_REWRITE_MODEL=gemini-3.1-pro-preview
   GEMINI_REWRITE_THINKING_LEVEL=HIGH
   GEMINI_SEARCH_MODEL=gemini-3.8-flash
   GEMINI_SEARCH_THINKING_LEVEL=HIGH
   ```
   The level is `LOW`, `MEDIUM` or `HIGH`. There is no "thinking budget" line: Google deprecated it for Gemini 3, and sending it with a level is an error.
5. If a call fails with a permission error (403), the message names the role that is missing. The usual one is "Vertex AI User" on the project. Your account did not need it, so this is only a note.
6. Check: the setup check shows the project, the location, the sign-in and the two layers. Then run `.venv\Scripts\python -m proofs.google_models`. It costs a few cents.

## Step 4. Docker and the local database

1. Start **Docker Desktop** and wait until it says it is running.
2. In `.env` put any password you like: `POSTGRES_PASSWORD=...`. It only protects the copy of the database on your laptop. The project made one for you.
3. In the project folder: `docker compose up -d --wait db`. The first time it downloads the database image (about 450 MB).
4. Then: `.venv\Scripts\python -m hackathon_memory.db migrate`.
5. The database keeps the password it was first created with. If you change `POSTGRES_PASSWORD` later, run `docker compose down -v` once (this deletes the local database) and start it again.

## Step 8. Your contact address for the collector

You promised ETHGlobal that every request carries the name of your tool and your email address.

```text
COLLECTOR_NAME=HackathonMemory-research
COLLECTOR_CONTACT_EMAIL=your address
```

The address goes to the sites you asked, and only in the requests of the collector. The tool never prints it.

## Step 9. One or two ETHGlobal project pages that you saw yourself

**Done on 10 October 2026. You have nothing to do here.**

**What changed, twice in one day.** First: the Hedera prize pages list no winners, so the plan became a list of project pages made by hand (backlog entry 07). Then you found a filter in your browser: `https://ethglobal.com/showcase/?partners=hedera`. That list says, for each project, which sponsors gave it a prize. So the tool now finds the winners itself (backlog entry 10).

**What your file is for now.** The list names a sponsor by a short id, not by its name. The tool must not guess which id is Hedera. So it needs one or two pages that a person saw with a Hedera prize: open the page, look on the left for "Winner of", and under it for a line that starts with "Hedera". Their addresses are in `data/by-hand/ethglobal.com/project-pages.txt`, one for each line:

```text
https://ethglobal.com/showcase/contragent-8x0c9
https://ethglobal.com/showcase/hedera-agent-trust-mur21
```

These two were enough: both took a prize of one sponsor only, the same one. The lines that start with `#` in that file are no longer needed. You can leave them.

## Step 9b. A look (optional)

`.venv\Scripts\python -m hackathon_memory.collect ethglobal --look` sends **two requests**: robots.txt, and the first page of your file. It prints the shape of the page (no text, no person), says whether the team cut passes and whether the page shows a Hedera prize, and **saves no page**. It ran once on 10 October 2026 and passed. There is no reason to run it again.

## Step 10. The walk and the run

**Done on 10 October 2026. Do not start them again:** ETHGlobal was promised that its pages are read one time. Both commands know that they are finished and send no request, but there is no reason to try.

What ran, for the record:

```text
.venv\Scripts\python -m hackathon_memory.collect ethglobal --plan      shows what would be read, no request
.venv\Scripts\python -m hackathon_memory.collect ethglobal --find      the walk: 21 pages of the list, no page saved
.venv\Scripts\python -m hackathon_memory.collect ethglobal --pages 3   the first three winner pages
.venv\Scripts\python -m hackathon_memory.collect ethglobal             the other 89
```

The result: 92 pages of projects that took a Hedera prize, from 14 events, in `data/raw/ethglobal.com/`. 140 requests were sent to the site that day, out of the 300 that are the limit. The count is in `data/requests/ethglobal.com.json`.

**The switch.** `COLLECT_ETHGLOBAL` is still `off` in your `.env`, and it should stay off. The assistant turned it on only for its own commands, one at a time. With the switch off, no collector can start by accident.

**To check what is on your disk,** at any time and with no request:

```text
.venv\Scripts\python -m proofs.lists
```

It says whether every promise to ETHGlobal was kept: only winners saved, no page edited, no person in a page, two seconds between pages, the limit not passed.

**What is yours to do next** is not setup. It is in `backlog/open-questions.md`: the second email to ETHGlobal (Q24), and whether Phase A is done (Q27).
