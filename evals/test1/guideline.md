# Test 1: how the fields of the model are graded

This guideline says how a person grades the fields that a language model writes on a project card (design 13.2). It was written before anybody graded, and it does not change after the grading starts. Every example below is invented.

## What is graded, and why

Test 1 has 60 project pages. A program drew them at random from six groups (`evals/sets.py`), and they are listed in `evals/sets/test1.json`. For each page, the model wrote a card with seven fields (design 4.1):

| Field | What it says |
|---|---|
| What it does | One plain sentence on what the project does. |
| How it works | Three to six short steps. |
| For whom | Who uses it. |
| Hedera services | Which Hedera services the page says the project uses, and for what. |
| Category | One field of life, from a fixed list of 16 (design 4.5). |
| Problem | The problem that the project solves. |
| Solution | How the project solves it. |

Each field has a label (stated, inferred or not found) and the sentences of the page that support it, called quotes. A program has already checked that every quote stands in the page, and it removed every field with no quote left (design 6.3). That check catches invention. It cannot see a true sentence that the model read wrongly. A person can, and that is what this test measures.

Two graders grade the cards, each alone: the maintainer, and a second grader, a model that is not the model under test (design 13.2). The second grader grades before it sees any grade of the maintainer. The model under test never grades its own work. In the run of October 2026, the second grader graded all 60 projects and the maintainer graded 10 of them.

## The order of work for each project

1. **Read the page.** The sheet shows the text that the model read: the name, the short line, and the texts of the page with their titles.
2. **Answer two questions about the page, before you see the card:**
   - Category: which one category fits the project best?
   - Hedera services: which Hedera services does the page say the project uses?
   - For 10 of the 60 projects there is a third question: are the texts the same as on the real page?
3. **Open the card and grade each field.**

The order matters. A person who sees the model's category first tends to agree with it. An answer given before the card is a fair measure for the list of categories (design 4.5) and for the comparison of code and model (design 13.3).

## Grades for a filled field

Compare the field with the page only. What you know about the project or about Hedera from elsewhere does not count.

| Grade | When |
|---|---|
| **Right** | The page supports everything in the field. |
| **Partly** | The main point is supported, but a detail is not, or an important part is missing. |
| **Wrong** | The page does not support the main point, or says the opposite. |

The examples use one invented page: *"Farmers scan a code on each sack of coffee. The app writes where the sack goes to the Hedera Consensus Service. Buyers in Europe check this record before they pay."*

| Field | Grade | Why |
|---|---|---|
| What it does: "It records where coffee sacks go, so that buyers can check them." | Right | Everything is on the page. |
| What it does: "It records where coffee sacks go, and pays the farmers in HBAR." | Partly | The record is on the page; the payment is not. |
| What it does: "It lends money to coffee farmers." | Wrong | The page says nothing like it. |
| For whom: "Coffee farmers and buyers in Europe." | Right | Both are named. |
| For whom: "Coffee shops." | Wrong | The page names farmers and buyers, not shops. |
| Hedera services: "It uses the Token Service to record each sack." | Wrong | The page names the Consensus Service. |
| How it works: "1. A farmer scans the sack. 2. The app writes the place on Hedera. 3. A buyer checks the record." | Right | Every step is on the page. |
| The same steps, and "4. The buyer pays with a stablecoin." | Partly | One step is not on the page. |

More rules:

- A field is graded as a whole. "How it works" is one field, with all its steps.
- A field that is right but hard to read is still right. This test measures what is true, not the style. Write a note if the style bothers you.
- A small general fact (for example "HBAR is the coin of Hedera") does not make a field partly. A claim about this project that the page does not support does.

## Labels

| Label | It is right when |
|---|---|
| Stated | One sentence of the page says it. |
| Inferred, shown as "less sure" | No single sentence says it: it follows from several sentences, or the page only suggests it. |
| Not found | The page gives nothing about it. |

For each filled field, answer: **is the label right?**

- The page says "Buyers in Europe check this record before they pay." The field "For whom: buyers in Europe" is labelled stated. The label is **right**.
- The page never says who uses the app, and the field "For whom: coffee buyers" is labelled stated. The label is **wrong**: the page only suggests it, so it is inferred.
- A field labelled inferred, when one sentence of the page says it plainly: the label is **wrong**. It is a small error, but the label tells the reader how far to trust the field.

The grade and the label are two separate questions. A field graded wrong can have the right label, and a field graded right can have the wrong one.

## Empty fields

A field is empty for one of two reasons: the model said that the page gives nothing about it ("not found"), or the program removed it because none of its quotes was found in the page. For an empty field, answer: **does the page give this information?**

- **Yes**, when the page says it anywhere, with or without a title, in one sentence or spread over several. Example: the page has no title "Problem", but it says "Today a buyer cannot know where a sack has been." The problem is given.
- **No**, when the page gives nothing about it.

An empty field is right only when the page gives nothing (design 4.3).

## Category

Pick the one category that fits the project best. Choose it by who the project serves, not by the technology inside. "AI agents and automation" and "Developer tools" fit only when the agent or the tool is itself the product (design 4.5).

The 16 categories: Payments and remittance. Lending, saving and investing. Real-world assets and tokens. Identity and credentials. Supply chain and provenance. Sustainability, energy and climate. Health. Education. Agriculture. Gaming and entertainment. Social and community. AI agents and automation. Developer tools. Data and devices. Public services. Other.

**From 15 October 2026, 17 categories.** The first run did not accept the list (see "Pass marks"), so it was split once, as design 4.5 says. "Tools for AI agents" came out of "AI agents and automation", and the rule for the three categories of agents and tools became:

- **AI agents and automation:** an agent or an automation is what people run or get. Example: a trading agent that anyone can start.
- **Tools for AI agents:** the project is built for AI agents to use. Examples: limits on what an agent may spend, an identity or a reputation for agents, a market where agents buy services.
- **Developer tools:** a tool for people who build software. Example: a kit of code for building on Hedera.

The runs from that day on use the 17 categories.

- A wallet that lets street vendors take payments: **Payments and remittance**, not Developer tools.
- A kit of code that helps other developers build on Hedera: **Developer tools**.
- An AI agent that books farm machines for farmers: **Agriculture**, because the agent serves farmers.
- A trading agent that any user can run as the product itself: **AI agents and automation**.

Pick "Other" only when no category fits. When two fit, pick the one closer to the people who use the project, and write the second one in the note.

The card's own category is graded like any field. **Right**: it is the best fit, or as good as the best. **Partly**: it fits a part of the project, but another category fits clearly better. **Wrong**: it does not fit.

## Hedera services

Tick each Hedera service that the page says the project uses. The services are the ones that Hedera's own library names (hiero-sdk-python 0.2.10, read on 13 October 2026), with the mirror node and the Agent Kit added, because pages name them often.

| Box | Words that a page may use |
|---|---|
| Accounts and HBAR transfers | accounts, HBAR payments, crypto transfers |
| Consensus Service | HCS, topics, consensus messages |
| Token Service | HTS, Hedera tokens, NFTs made with the token service |
| Smart contracts | Solidity contracts on Hedera, the EVM of Hedera |
| File Service | HFS, files stored on Hedera |
| Scheduled transactions | the Schedule Service, scheduled transactions |
| Mirror node | the mirror node, its REST API |
| Agent Kit | the Hedera Agent Kit |
| None | the page names no Hedera service as used |

- Tick a service when the page says that the project uses it: it is built, or it is in the demo.
- Do not tick a service that the page only plans ("next, we want to mint NFTs") or names for another reason.
- A token made as a Solidity contract (ERC-20, ERC-721) counts as Smart contracts. A token made on Hedera without saying how counts as Token Service.

Two examples: "We store every vote as a message on an HCS topic" ticks the Consensus Service. "In the future we will give NFT badges" ticks nothing.

## The parser check, on 10 projects

For 10 projects the sheet asks whether the texts on the left are the same as on the real page. Open the real page with its link. Compare the title, the start and the end of each text. Answer "the same" or "different", and write what differs in the note. A program picked the 10 at random, with a fixed seed.

## Planted fields

A program changed a few fields of the sheet on purpose, so that they are wrong. It picked them at random and wrote them in a key that neither grader opens before both have graded. A planted field is **caught** when it is graded partly or wrong. The test passes this point only if each grader catches every planted field in the projects it graded, and every planted field is graded by at least one of them (design 13.6). The planted fields are not counted in the four numbers.

## Notes

Every project has a box for a note: a doubt, the second category, what differs on the real page. The notes stay on the maintainer's laptop, like the texts of the pages. They never go into a result file.

## The numbers

`evals/test1/report.py` computes four numbers (design 13.2). A grader's numbers come from the projects that it graded in full, every question of every field answered. The numbers that meet the pass marks come from a grader who graded every project: the maintainer when the maintainer did, otherwise the second grader. On the projects that both graded, the report puts the two graders' numbers side by side and says how often they give the same answer, so that a reader sees how far a number depends on its grader.

These rules for a grading that does not cover every project were added on 15 October 2026, after the grading and before the key of the planted fields was opened. Before, the rule was that the numbers come from the maintainer's grades.

1. **Faithful.** Of the filled fields, the share graded right or partly ("not wrong"). The share graded wrong is given too.
2. **Kept.** Of the fields where the page gives the information, the share that the card has. The page gives the information when a filled field is graded right or partly, or when the grader answered yes for an empty field. A filled field graded wrong is left out of this number: it already counts against "faithful".
3. **Honest labels.** The share of labels that are right. For a filled field, the grader's answer. For a field labelled "not found", the label is right when the grader answered no. A field that the program removed shows no label on the card, so it is not counted here. The share of "inferred" fields graded right or partly is given too.
4. **Quote check.** Of the fields that the model filled, the share that kept at least one quote found in the page. The program gives this number, not a grader.

Each number comes with a range, computed by project, not by field (design 13.1). The fields of one page tend to be right or wrong together. So the program draws 60 projects again from the 60, with replacement, 10,000 times, with a fixed seed. The range holds the middle 95 of every 100 results.

Also given, with no pass mark: the share of filled fields graded right, how often the two graders give the same grade, and how often they pick the same category.

### Pass marks

These marks were fixed on 9 October 2026 (design 13.6). They are not moved after the grading.

| Number | Pass mark |
|---|---|
| Faithful | At most 5% of the filled fields graded wrong, and the low end of the range of "not wrong" at 90% or more. |
| Honest labels | At least 90% of the labels right. |
| Kept | At least 85%. |
| Planted fields | Each grader catches every planted field in the projects it graded, and every planted field is graded. |

The list of categories is accepted when the two graders' own picks agree on at least 80% of the projects where both picked one, and at most 15% of each grader's picks are "Other" (design 4.5). If not, categories are merged or split once, before the cards of all pages are made.

## What is kept, and where

The texts of the pages, the cards, the grades and the notes stay in `data/evals/test1` on the maintainer's laptop. The result file in `evals/results` holds the address of each page, the name of each field, its grades and the numbers. It holds no text from a page (design 13.1).
