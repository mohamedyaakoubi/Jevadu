# 17. The notes public, a calmer dark theme, the words of the website, insights

Started on 20 October 2026 on `phase-e-website`, from `e503303`. The owner's ten points of that day
are quoted in `decisions.md` (20 October 2026).

## Goal

1. Make the working notes public, mistakes included (point 1).
2. A dark theme that is not green and is easier on the eyes, and the reason the text tired the
   owner's eyes (point 2).
3. The words of the website: talk like a normal product, without paraphrases of the usual terms
   (point 3).
4. Light insights over the collection, such as teams that won several times and the categories
   that won most, only where the data carries them (point 7).
5. An answer about a hosted version on a subdomain of the owner's domain (point 8).
6. The owner's Google Cloud credit, about $15: no paid call without their yes (point 10).

Points 4, 5, 6 and 9 (the demo script, the idea of the demo, the consent line in the demo, the logo
and the pitch deck) wait for the owner's word: "redo the demo and its above points when I say so".

## Approach and results

**The notes are in git** (`073aaf4`). `.git/info/exclude` keeps only the vendored git-filter-repo
(its author's address is in it) and the local backups. The guard hook no longer reads the notes for
the words of hard constraint 19; the old exclude file and the old hook are in `.local-backup/`.
Checks before the commit: the secret scan (7 values, 296 commits and the working folder: clean);
the shapes of secrets (none); email addresses (only those of organisations); runs of 8 words shared
with a collected page or a saved README (a regex, an API address, the title of a public Hedera
article and a docs address only); the owner's contact address (not found). "He" became "they" in
the notes. The lint leaves out `backlog/`: its scripts are a record, kept as they ran. The
repository itself is still private (`gh repo view`: PRIVATE), so the notes become visible to others
only when the owner makes it public, which needs the new request to ETHGlobal first (blueprint
5.7).

**Test 3 says who read** (`03d7fe8`). The report, the README and the design said "a person"; the
reader was the assistant, a language model. They now say "a second reader, a language model that
is not part of the tool", as the report of Test 1 says of its second grader, and the report names
two limits: no person checked that reading, and ten READMEs were not read blind (Q45, answered by
point 1).

**The FSS Campus Edition** runs from 10 August to 7 November 2026 in the list of the check
(`b899fa8`), so a check for it judges the dates now.

**The dark theme** (research of 20 October 2026, sources in the commit and in blueprint 12.1):
- Nielsen Norman Group (Budiu, 2020), after Piepenbrock and colleagues (2013, Ergonomics and Human
  Factors): for people with normal vision, dark text on a light page reads better; the light
  advantage grows as the letters get smaller. Dark mode helps some people with cloudy eye media.
  Their advice: offer a dark mode, do not make it the default.
- Halation: light letters on a dark ground seem to spread, more with astigmatism, because the
  pupil opens in a dark page (Level Access and design sources; no clinical paper was found, so the
  size of the effect is not known).
- Material Design's codelab for dark themes: a dark grey ground (#121212), white text at 87%,
  60% and 38%, and lighter, less saturated colours, because saturated ones "vibrate" on a dark
  ground.
- What Tabler did in our dark theme: headings pure white (21:1 at most), text 13.9:1, a mint
  accent (oklch 74% 0.13 165) on buttons, links and chosen switches.
- Now: text oklch(88%) 12.2:1 on the page, 10.6:1 on a card; headings oklch(92%); grey text
  oklch(74%) 7.6:1; one soft blue accent oklch(78% 0.09 262) 8.7:1, also with dark text on it; a
  chosen switch is a tint; 0.01em between letters and line height 1.6 for reading text; charts in
  blue and a soft amber (contrasts from `contrast.py`, the WCAG 2 formula). axe-core: no problem
  in 16 views in each theme, at 1440 and 390 pixels.
- Found on the way: the warning box of Tabler was 2:1 in the light theme (seen only when Google
  did not answer); its text now follows the pills, `e35ecd7`. And the summary of every result
  card stood in a grey box, because the README line of the register (third queue) took the same
  class name `hm-line`; `e77548f`.

**The words of the website.** Hard constraint 13 now splits the website (the usual words of the
field, each explained once in its (i)) from the chat with the owner (easy, full of context). Every
template, the messages of `app.py`, the chart labels, the names of the ways to search and of the
actions of a transaction were rewritten, and the checks of `tests/test_web.py` follow them
(`84e6c25`). Two texts were out of date: "only the projects of the two test sets have a card" (all 658 full pages have one
since 18 October). "How it works" gives Test 3 from its result file.

**Insights** (point 7, measured on the local database, `insights_probe.py`): the data holds two
groups of linked projects. One won a Hedera prize at three events with the same repository
(Yourturn at ETHGlobal Cannes 2026, YourTurn Concierge at ETHGlobal New York 2026, YourTurn 2.0 at
ETHOnline 2026); the other (Froggy and Hands Unchained) won no Hedera prize. So "the most winning
teams" is one sentence, not a ranking. The categories with the most Hedera prizes, among the 658
projects with a category: AI agents and automation 21 of 95, Lending, saving and investing 16 of
55, Tools for AI agents 13 of 224. Still worked on after the event (active or quiet, of those whose
activity is known 90 days after the event): 19 of 64 Hedera prize winners (30%), and 40 of 240
projects without a Hedera prize (17%).
The block "Insights" stands above the charts; each sentence appears only when the list holds
enough projects (`web/insights.py`, tests in `tests/test_web_insights.py`, `d20c714`). Its links
inside a sentence are underlined: axe-core's rule link-in-text-block asks more than a colour.

**Hosting (point 8)** is an answer to the owner, not built: see the session's report and
`decisions.md`.

## What went wrong

- The report of Test 3 said "a person" (lessons.md, 20 October).
- My change of "he" to "they" replaced the text "he marks" without word limits, and five notes read
  "tthey mark" instead of "the marks". A word diff against the backup found it before the commit.
- The first commit of the notes failed the lint: ruff read the old scripts of `backlog/tools/`.
  They are now left out of the lint.
- `commit_guarded.sh` was missing from the session's folder and was written again.
- `stage_hunks.py` put the two lines of the alert rule 18 lines too low, inside the rules of the
  tool's mark (commit `e35ecd7`): git apply places a hunk with no context by its new line number,
  and a left-out hunk above it had added 18 lines. The rule works the same there, but the next
  commit would have moved it back in passing; the chain was stopped, and the move has its own
  commit. The tool now counts the new line numbers again from the kept hunks only, tested in a
  throwaway repository.

## What this does not prove

- The dark theme was checked by contrast numbers, axe-core and pictures, not by the owner's eyes.
- The insight on activity compares counts; it does not say that a prize keeps a project alive.

## Commits

- `03d7fe8` docs(evals): say that a model made the Test 3 reading
- `b899fa8` feat(register): give the FSS Campus Edition its last day
- `073aaf4` docs(notes): add the working notes to the repository
- `e77548f` fix(web): stop boxing the summary line of each result card
- `e35ecd7` fix(web): darken the text of the warning and problem boxes
- `3f99b2c` feat(web): make the dark theme calmer and stop it being green
- `84e6c25` feat(web): use the usual words of the field on every screen
- `f85cfe9` refactor(web): move the alert rule next to the rules of the pills
- `d20c714` feat(web): add insights in sentences above the charts
