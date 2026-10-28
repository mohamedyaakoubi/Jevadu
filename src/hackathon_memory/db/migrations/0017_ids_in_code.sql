-- The Hedera IDs that the code of each repository names (design 7.3, 24 October 2026).
--
-- ids_in_code holds every ID that the reading of a repository's code found, with the files where
-- it stands: a candidate. Most prove nothing, because code also names things that many teams use,
-- such as a public token. The check (pipeline/code_ids.py) gives a project the candidates of its
-- code that pass the strict rule, as rows of hedera_ids with found_in = 'code' and the file where
-- each one stands. No words around an ID are kept for the code: in a file of example settings
-- the next line can hold a key.

CREATE TABLE ids_in_code (
    repository_id  bigint NOT NULL REFERENCES repositories (id) ON DELETE CASCADE,
    entity_id      text NOT NULL CHECK (
        entity_id ~ '^(0\.0\.[1-9][0-9]{0,11}|0x[0-9a-f]{40}|0\.0\.[1-9][0-9]{0,11}-[0-9]{1,11}-[0-9]{1,9})$'
    ),
    -- NULL when the code leaves the network open: then both networks are asked.
    network        text CHECK (network IN ('mainnet', 'testnet', 'previewnet')),
    files          integer NOT NULL CHECK (files >= 1),
    -- The paths of the first files where it stands, inside the repository (at most ten).
    examples       text[] NOT NULL CHECK (cardinality(examples) BETWEEN 1 AND 10),
    UNIQUE NULLS NOT DISTINCT (repository_id, entity_id, network)
);

CREATE INDEX ids_in_code_entity ON ids_in_code (entity_id);

ALTER TABLE hedera_ids DROP CONSTRAINT hedera_ids_found_in_check;
ALTER TABLE hedera_ids ADD CONSTRAINT hedera_ids_found_in_check CHECK (
    found_in IN ('page', 'readme', 'code')
);
-- The file of the code where an ID of the code stands; only an ID of the code has one.
ALTER TABLE hedera_ids ADD COLUMN found_at text;
ALTER TABLE hedera_ids ADD CONSTRAINT hedera_ids_code_has_its_file CHECK (
    (found_in = 'code') = (found_at IS NOT NULL)
);
