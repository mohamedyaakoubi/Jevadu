# Visual review of the page, 18 October 2026

A review of every screen as it looks, on the running site with the real collection, in Chromium at a desk width (1440 by 900), in the light and the dark theme: the start, the quick results and the sentence under them, the order by Gemini while it is asked, the window of a project, a project with links, the charts, the check of a submission with no hackathon, with a hackathon of the list and with a wrong link, its comparison, a project opened from the check and the way back, and the three windows of the bottom of the page. One picture per state; the pictures stay on the laptop, because they show the text of collected pages. The phone width is left out, by the maintainer's decision of 18 October 2026. axe-core 4.14.0 ran on the new states in both themes.

The checks of design 12.3 are the same as in layer 1: the task is done, the words are clear, the states (waiting, empty, error) say what happens, the colours keep their contrast, and nothing is cut or overlaps.

## What held

- The palette keeps one meaning per colour in both themes: green for a proof found and an active life, orange for dates that do not fit, red for a stopped life, grey for what cannot be told, yellow for a Hedera prize and blue for a winners' list.
- The cards of a list keep the same spacing, title size and place of the marks; the windows keep the same head, columns and cards.
- The waiting states say what runs and for how long: the steps of a check, the shapes of the cards while Gemini reads, the line of each comparison.
- axe-core found no problem on the check (with and without a hackathon of the list), on the results with the sentence under them, and on a project of the check in the light theme. After the fixes below, it found none in 20 runs on the real collection: the start, the charts, a search by meaning, a card opened by its address and the window of a project, each in both themes, at a desk width and a phone width.
- The comparison of a check filled the five places in about 6 seconds, and the way back gave the check as it was.

## Findings

| # | Screen | Finding | Check | Sure | Done |
|---|---|---|---|---|---|
| 1 | S3 | A wrong link left the steps of the check on screen; the answer "This is not the link of a repository" never came. A refused registration showed nothing either. The page let an answer of 400 or 503 take its place only for the element that asked, but htmx 2 names the target of the swap in that event. | 3 | sure | `fd8a6f6` |
| 2 | S3, S2 | "Back to the check" had light text on light grey in the dark theme: 2.41 to 1 for axe, where 4.5 is needed. | 4 | sure | `2b931bf` |
| 3 | S4 | The box of the line for the README failed axe's contrast. | 4 | sure | `2b931bf` |
| 4 | S2 | A card opened from a shared address (/?open=N) did not show its linked projects. | 1 | sure | `92190e2` |
| 5 | S5 | In the chart of the themes, the label "Sustainability, energy and climate" was cut at the left edge: Chart.js gives the labels at most half of the width of a chart. | 5 | sure | `128a816` |
| 6 | S5 | The second row of charts left an empty cell: two charts in a grid of three columns. | 5 | sure | `128a816` |
| 7 | S6 | In the window "How it works", the narrow table of the ways to search broke short values over two lines ("about 2.0" and "s"). | 2 | sure | `fd5eaf1` |
| 8 | S3 | For a hackathon of the list whose days are not announced, the proof said "end of the event not typed in", which reads like a mistake of the person who checks. It now says "not known yet". | 2 | sure | `451c0a2` |
| 9 | S3 | The list of the check cut the long name of the FSS Campus Edition. | 5 | sure | `217d361` |
| 10 | S3 | After the comparison, two grey lines under the title say nearly the same thing ("Compared by Gemini [...] Not a judgment" and "By the meaning of the README [...]"). | 2 | unsure | no |
| 11 | S1 | During the review, the quick results took 7.6 seconds, and the order by Gemini failed once with an error of Google's service; the page fell back to the quick results. The laptop ran the test suite at the same time. Measured again with one run of the suite only: a whole page of quick results in 0.5 to 1.9 seconds, the longest for an idea whose embedding was not kept yet. | 1 | unsure | nothing to change |
| 12 | All | A reference mark such as [8] stands a little apart from the word before it and the comma after it. | 5 | unsure | no |
