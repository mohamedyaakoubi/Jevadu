-- The facts of the code of each repository (design 7.3), for the life rule (design 7.4).
--
-- They come from GitHub's answer about the repository, saved under data/raw with only a fixed
-- list of fields: nothing about the account that owns it (design rule 11). NULL while the facts
-- were not asked for.
ALTER TABLE repositories
    -- "gone": no such repository any more, or a private one. "blocked": GitHub blocked it.
    ADD COLUMN code_status      text CHECK (code_status IN ('found', 'gone', 'blocked')),
    ADD COLUMN code_fetched_at  timestamptz,
    ADD COLUMN made_at          timestamptz,
    -- The last push of code to any branch: the last change that the life rule looks at.
    ADD COLUMN last_push_at     timestamptz,
    ADD COLUMN archived         boolean,
    ADD COLUMN fork             boolean,
    ADD COLUMN language         text,
    -- The link of the repository today, when it was moved or renamed since the page named it.
    ADD COLUMN current_url      text CHECK (current_url ~ '^https://github\.com/[^/]+/[^/]+$'),
    ADD CONSTRAINT repositories_facts_have_a_time
        CHECK ((code_status IS NULL) = (code_fetched_at IS NULL)),
    ADD CONSTRAINT repositories_facts_of_a_found_one
        CHECK (code_status = 'found' OR (made_at IS NULL AND last_push_at IS NULL));
