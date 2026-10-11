# Invented sample pages for the ETHGlobal collector

**Every file here is INVENTED. Nothing was taken from a real page.** The names, the projects and the
text are made up, and the people do not exist. The files only give the collector's tests something to
read that has the shape the collector expects.

Why they are invented: no text taken from a collected page may enter git (design rule 18, and
design 5.7). A test (`tests/test_promises.py`) checks that every file in this folder starts with the
word INVENTED, so a real page cannot be saved here by mistake.

## The shape

`project_winner.html` follows what three real project pages looked like on 10 October 2026: a header
with the name, a short line and two links; a box with the event and the block "Winner of", with one
line for each prize; the sections "Project Description" and "How it's Made"; and the data of the page
as text in a script. The tags "author" and "twitter:creator" hold the name of the site.

| File | What it is for |
|---|---|
| `project_winner.html` | A project that took a Hedera prize. It is kept. |
| `project_other_sponsor.html` | A project that took another sponsor's prize and only talks about Hedera. It is read but not kept. |
| `project_no_prize.html` | A project with no prize. It is read but not kept. |
| `project_profile_link.html` | A page that shows a link to a profile. The site has changed shape, so the run stops. |
| `project_person_in_data.html` | A page whose data holds a list of members. The run stops. |
| `project_zed_widget.html`, `project_mango_ledger.html` | Pages with a team block. No real page shows one to a visitor who is not signed in. They stay because the tests of the team cut need a team to cut. |
| `robots.txt` | The rules of an invented site. |
