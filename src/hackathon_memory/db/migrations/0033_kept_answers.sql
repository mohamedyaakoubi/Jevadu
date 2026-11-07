-- The answers of GitHub that the checks of the public copy saved (design 12.5, 7 November 2026).
-- Each copy of the site on Vercel has its own data folder, and a request may land on any copy, so a
-- check that one copy made was asked of GitHub again on another (web/kept_answers.py). A copy now
-- keeps here the files that a check wrote, under the repository it checked, and another copy writes
-- them back into its own folder before it checks the same repository. A saved file is never changed
-- (collect/rawstore.py), so a row is never changed either. `path` is relative to the data folder.
CREATE TABLE kept_answers (
    path        text        PRIMARY KEY CHECK (path <> '' AND path NOT LIKE '/%' AND path NOT LIKE '%..%'),
    repository  text        NOT NULL,
    body        bytea       NOT NULL,
    saved_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX kept_answers_by_repository ON kept_answers (repository);
