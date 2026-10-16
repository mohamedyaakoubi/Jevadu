# Test 1, run of October 2026: the cards of Gemini 3.1 Pro

This is the short report of Test 1 (design 13.2). It answers one question: when the model writes a card, does the card say what the project page says? The numbers come from `evals/results/20261014T231416Z-test1.json`. The rules of grading are in `guideline.md` and were fixed before anybody graded.

## What was tested

- **The cards:** 60 project pages of ETHGlobal's showcase, drawn at random from six groups (`evals/sets/test1.json`). Gemini 3.1 Pro (preview) wrote one card for each page at the thinking level HIGH, with the instructions `card-form-1`, which were written on 15 other pages. The cards cost 2.98 dollars in all.
- **The fields:** seven for each card: what it does, how it works, for whom, Hedera services, category, problem and solution. 414 fields had content; 6 were empty because the model found nothing on the page.
- **The graders:** a second grader, a model that is not the model under test, graded all 60 projects. The maintainer graded 10 of them. Neither saw the other's grades first.
- **The planted fields:** a program changed 6 fields on purpose, so that they were wrong, to see whether the graders catch them. They are left out of the numbers below.

## The numbers

From the second grader, on the 60 projects (408 filled fields, the 6 planted ones left out). Each range is computed by project, from 10,000 new draws of the 60 projects.

| Number | Result | Range | Pass mark (design 13.6) | Met |
|---|---|---|---|---|
| Faithful: filled fields graded right or partly | 408 of 408 (100%) | 100% to 100% | at most 5% wrong, low end of the range 90% or more | yes |
| Fields graded wrong | 0 of 408 | | | |
| Fields graded fully right | 396 of 408 (97.1%) | 95.5% to 98.5% | none | |
| Kept: the card has what the page gives | 408 of 408 (100%) | 100% to 100% | at least 85% | yes |
| Honest labels | 408 of 414 (98.6%) | 97.3% to 99.5% | at least 90% | yes |
| Inferred fields graded right or partly | 95 of 95 (100%) | | none | |
| Quote check: fields that kept a quote found in the page | 414 of 414 (100%) | | none | |
| Planted fields caught | see below | | each grader catches every planted field in its projects | no |

A range of 100% to 100% only says that no wrong field turned up in this sample. A larger sample can still find some.

## The two graders side by side

On the 10 projects that both graded (69 filled fields, the planted one left out):

| | Maintainer | Second grader |
|---|---|---|
| Graded right or partly | 68 of 69 | 69 of 69 |
| Graded fully right | 65 of 69 | 67 of 69 |
| Labels right | 68 of 69 | 66 of 69 |

The two gave the same grade to 63 of the 69 fields (91.3%) and the same answer about the label to 65 (94.2%).

## The planted fields

The second grader caught all 6: it graded 5 of them wrong and 1 partly. The maintainer's 10 projects held one planted field: a category changed to another category that fits part of the project. It was graded right, so this pass mark is not met. A planted category can be close to a fair choice. The next run should plant categories that clearly do not fit.

## The list of categories

The two graders picked a category of their own on 11 projects, before seeing the card; on 2 of them the maintainer changed the pick after seeing it. They picked the same one on 4 (36%). Neither picked "Other". The rule of design 4.5 accepts the list at 80% or more, so the list is not accepted. Most differences were about tools built for AI agents: one grader put them under "AI agents and automation", the other under what they do, such as payments or identity. As the rule says, the list changes once before the cards of all pages are made. The model's category matched the second grader's pick on 45 of 58 projects.

## The parser

The parser copies the texts of a page word for word. The maintainer compared them with the real page on 1 of the 10 projects marked for that check: they were the same. The other 9 were not checked.

## What was graded partly or wrong

None of these errors comes from nothing: each one reads a true sentence of the page too widely. From the second grader, on the 60 projects:

- **Services named in general words.** The field said what Hedera does in the project but did not name the service, for example "a public network" for the Consensus Service. Graded partly three times.
- **A plan written as a fact.** The team planned to use a device, and the card said that the project uses it.
- **A remark made into the problem.** A remark of the team about how they built the project, or about other demos, became the problem that the project solves. Graded partly three times.
- **A step stretched.** One step said that a good credit score becomes tokens. The page says that receivables become tokens, priced by the score.
- **A category that fits only part of the project.** Graded partly four times.
- **Labels.** Three fields were labelled "inferred" when one sentence of the page says them plainly. Three were labelled "stated" when the page only suggests them.

From the maintainer, on 10 projects:

- **A service left out.** Three times the field of the Hedera services missed one service that the page names. Graded partly.
- **A category that does not fit.** A tool built for AI agents was put under "AI agents and automation", where the maintainer saw developer tools or data. Graded wrong.

## What this test does not show

- That every card of every page is right. It is a sample of 60 pages from one source, ETHGlobal's showcase, whose pages have a clean, fixed shape.
- That a person would grade all 60 the same way. A model graded all 60; a person graded 10, and the two agree on about 9 fields in 10.
- Anything about another model. These are the cards of Gemini 3.1 Pro. Cards made by another model need their own run of this test.
