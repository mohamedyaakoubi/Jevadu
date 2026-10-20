# The demo video: a script (draft of 18 October 2026)

A working note. About three minutes. Recorded on the laptop, in the browser at a desk width,
light theme. Each scene says what to click and what to say. Say it in your own words; the words here are
only a guide. Every number comes from a dated result file in `evals/results`.

Before recording: Docker Desktop is running, `docker compose up -d --wait db`, then
`python -m hackathon_memory.web`. Open http://127.0.0.1:8000 and clear the search ("Clear the search").
Check the budget once (`python -m hackathon_memory.finops budget`): the Gemini button needs the test budget.

## 1. The problem (20 seconds)

*Screen:* the start page, empty.

*Say:* "Hedera has run many hackathons, on many websites. A builder with an idea cannot see what was built
before, and a judge cannot easily check what a project claims about Hedera. Hackathon Memory keeps the
past projects in one place: what each one claimed, and what the public Hedera ledger says about it."

## 2. Search an idea (40 seconds)

*Click:* the example "limits on what an AI agent may spend".

*Say:* "I type an idea. The quick results come by meaning while I type; no AI model writes anything here.
The collection holds 826 projects from 26 events." *(the overview file of 18 October)*

*Click:* "Order and compare with Gemini".

*Say:* "On this button, and only here, Gemini puts the closest projects in order and writes, for each one,
what is the same as my idea and what differs. It never scores a project, and it never says that a project
is a copy."

## 3. A project card (40 seconds)

*Click:* the first result.

*Say:* "The card keeps three sources apart: the project's own words, a summary written by a model with a
quote for each claim, and the facts that programs read from the Hedera ledger and from GitHub. This green
mark says that a Hedera ID of the project was found on the ledger, with dates that fit the hackathon.
Every fact links to its source, here on HashScan." *(Point at the proof mark, the ledger column, a HashScan link.)*

*Optional:* "Its live demo" and "Its code" buttons at the top.

## 4. Check a submission (40 seconds)

*Type:* a GitHub link of the collection in the box "Check a submission", choose a hackathon in the list,
press "Check this repository".

*Say:* "A judge pastes the GitHub link of a submission. Programs read its README and the dates of its code,
ask the ledger about each Hedera ID, and look for the same code or the same IDs in past hackathons. Here
the proof, the life of the code, 'seen before', and the closest past projects."

*If the register is open (its topic exists):* "A team can also write a fingerprint of its submission to a
public register on Hedera, after it adds a line to its README. Only who can change the repository can add
that line." *(Show the register box and, if one exists, a receipt with its HashScan link.)*

*If the register is not open:* skip the register, or say one sentence: "The register on Hedera is built and
tested; its topic opens for the event."

## 5. The charts (15 seconds)

*Click:* "Charts".

*Say:* "For an organiser: the same list as charts. What was built, with what proof, and what is still alive."

## 6. What the tests measured (25 seconds)

*Click:* "How it works" at the bottom.

*Say:* "Every number here comes from a dated test. Test 2: the search finds the known similar project in the
first ten in 60% of the cases, under our pass mark of 80%, and the page says so. Test 3: on 50 pages checked
by hand, the tool found every Hedera ID that a second reader found, and gave the same status in 95 of 100; it also
counts some IDs that are not the project's, more than our mark allows, and the report says which."

## 7. The limit, and the close (20 seconds)

*Screen:* the start page or the footer.

*Say:* "The tool knows the projects whose pages are still public, and the winners of the other events. A
memory of every Hedera hackathon needs the sites or the organisers to share their data. Hackathon Memory:
past Hedera projects, checked against the public ledger."

## Things to avoid saying

- "Every Hedera hackathon project": the data holds the public pages and the winners of the rest.
- That a project is good, bad or a copy.
- A number that is not in a dated result file.
