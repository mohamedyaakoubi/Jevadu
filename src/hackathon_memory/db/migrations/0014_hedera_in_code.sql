-- What the code of each repository says about Hedera (design 7.3, 21 October 2026).
--
-- The archive of the default branch is read as a stream and not kept. What plain text matching
-- found in it is saved under data/raw, and written here: no AI writes any of it (design rule 2).
-- The columns are NULL while the archive was not read.
ALTER TABLE repositories
    -- "read": the whole archive was read. "partial": the reading stopped before the end, and
    -- archive_partial says why. "gone": no such repository any more, or a private one.
    -- "blocked": GitHub blocked it.
    ADD COLUMN archive_status   text CHECK (archive_status IN ('read', 'partial', 'gone', 'blocked')),
    ADD COLUMN archive_read_at  timestamptz,
    -- The commit that the archive was made from: a link to a file opens what was read.
    ADD COLUMN archive_commit   text CHECK (archive_commit ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'),
    -- The files of the project's own code that were read.
    ADD COLUMN archive_files    integer CHECK (archive_files >= 0),
    ADD COLUMN archive_partial  text,
    ADD CONSTRAINT repositories_archive_has_a_time
        CHECK ((archive_status IS NULL) = (archive_read_at IS NULL)),
    ADD CONSTRAINT repositories_archive_partial_says_why
        CHECK ((archive_status = 'partial') = (archive_partial IS NOT NULL));

-- What was found, one row for each thing: a Hedera package that a package file names
-- ("package"), a Hedera service that the code calls ("feature"), a sign of Hedera such as its
-- JSON-RPC relay, a chain ID, a network of an EVM tool, a system contract or the mirror node
-- ("sign"), the files that import a Hedera library ("import", one row), and the files that name
-- Hedera at all ("mention", one row).
CREATE TABLE hedera_in_code (
    repository_id  bigint NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    kind           text NOT NULL
                   CHECK (kind IN ('package', 'feature', 'sign', 'import', 'mention')),
    name           text NOT NULL CHECK (length(name) BETWEEN 1 AND 300),
    files          integer NOT NULL CHECK (files >= 1),
    -- The paths of the first files where it was found, inside the repository (at most ten).
    examples       text[] NOT NULL CHECK (cardinality(examples) BETWEEN 1 AND 10),
    PRIMARY KEY (repository_id, kind, name)
);
