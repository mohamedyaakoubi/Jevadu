-- The repositories of the projects' code on GitHub, and what their README gave (design 7.3).
--
-- A repository is kept by its link only, in one spelling (small letters). The name of its owner
-- is a part of that link and is kept nowhere else (design rule 11). The README itself is a saved
-- page under data/raw. This table holds what GitHub answered about it, and what was taken out of
-- it before it was saved, in numbers. The Hedera ids of a README are in hedera_ids, with
-- found_in = 'readme', for each project of the repository.
CREATE TABLE repositories (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    url                  text NOT NULL UNIQUE
                         CHECK (url ~ '^https://github\.com/[a-z0-9_.-]+/[a-z0-9_.-]+$'),
    -- NULL while the README was not asked for. "none": no README in the repository, or no
    -- repository any more. "blocked": GitHub blocked the repository. "not_text": the README
    -- could not be read as text.
    readme_status        text CHECK (readme_status IN ('found', 'none', 'blocked', 'not_text')),
    readme_name          text,
    readme_sha256        text CHECK (readme_sha256 ~ '^[0-9a-f]{64}$'),
    readme_fetched_at    timestamptz,
    people_words_hidden  integer NOT NULL DEFAULT 0 CHECK (people_words_hidden >= 0),
    team_lines_cut       integer NOT NULL DEFAULT 0 CHECK (team_lines_cut >= 0),
    -- Hedera ids that stood in a part about the team that was cut out. Counted, so that a
    -- person sees whether the cut ever takes something that the check needs.
    ids_in_the_cut       integer NOT NULL DEFAULT 0 CHECK (ids_in_the_cut >= 0),
    CHECK ((readme_status IS NULL) = (readme_fetched_at IS NULL)),
    CHECK ((readme_status IS NULL) = (readme_sha256 IS NULL))
);

-- The repository that the link to the code of a project names.
ALTER TABLE projects ADD COLUMN repository_id bigint REFERENCES repositories (id);
CREATE INDEX projects_repository ON projects (repository_id);
