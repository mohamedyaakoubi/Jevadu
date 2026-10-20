# 17. The notes public, a calmer dark theme, the words of the website, insights

Started on 20 October 2026 on `phase-e-website`, from `e503303`. The owner's ten points of that day
(quoted in full in `decisions.md`, 20 October 2026). This entry grows during the session.

## Goal

1. Make the working notes public, mistakes included (point 1).
2. A dark theme that is not green and is easier on the eyes, and the reason the text tired the
   owner's eyes (point 2).
3. The words of the website: talk like a normal product, without paraphrases of the usual terms
   (point 3).
4. Light insights over the collection, such as teams that won several times and the themes that
   won most, only where the data carries them (point 7).
5. An answer about a hosted version on a subdomain of the owner's domain (point 8).
6. The owner's Google Cloud credit, about $15: no paid call without their yes (point 10).

Points 4, 5, 6 and 9 (the demo script, the idea of the demo, the consent line in the demo, the logo
and the pitch deck) wait for the owner's word: "redo the demo and its above points when I say so".

## Done so far

- **The notes are in git.** `.git/info/exclude` keeps only the vendored git-filter-repo (its
  author's address is in it) and the local backups. The guard hook does not read the notes for the
  words of hard constraint 19; the backups of the old exclude file and of the old hook are in
  `.local-backup/`. Checks before the first commit of the notes: the secret scan (7 values, 296
  commits and the working folder, clean); the shapes of secrets (none); email addresses (only those
  of organisations); runs of 8 words shared with a collected page or a saved README (only a regex,
  an API address, the title of a public Hedera article and a docs address); the owner's contact
  address (not found).
- **"He" became "they"** in the notes, about the owner and about a builder.
- **Test 3 says who read.** The report, the README and the design said "a person"; the reader was
  the assistant, a language model. They now say "a second reader, a language model that is not part
  of the tool", as the report of Test 1 does, and the report names two limits: no person checked
  that reading, and ten READMEs were not read blind (Q45). `03d7fe8`.
- **The FSS Campus Edition** runs from 10 August to 7 November 2026 in the list of the check.

## What went wrong

- The report of Test 3 said "a person" (lessons.md, 20 October).
- My change of "he" to "they" replaced the text "he marks" without word limits, and five notes read
  "tthey mark" instead of "the marks". A word diff against the backup found it before the commit.
