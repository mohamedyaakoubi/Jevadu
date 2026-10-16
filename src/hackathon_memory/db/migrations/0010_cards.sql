-- The cards that the LLM fills, after the quote check (design 4.1, 6.3, 6.5).
--
-- One card for each project, model and version of the instructions. It is made again only when
-- the text that the model reads changes: the fingerprint of that text is kept here, an exact
-- cache (design 6.5). The text itself is in the tables of the project.
--
-- `fields` holds the fields after the quote check: for each one its label, its value, the quotes
-- that were found, the number of quotes removed, its state (kept, dropped or not_found) and why
-- it was dropped. `answer` is the form as the model returned it, before the check, for the tests
-- (design 13.2). Both stay on this laptop with the rest of the data.
CREATE TABLE cards (
    project_id            bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    model                 text NOT NULL CHECK (model <> ''),
    instructions_version  text NOT NULL CHECK (instructions_version <> ''),
    thinking_level        text NOT NULL CHECK (thinking_level IN ('LOW', 'MEDIUM', 'HIGH')),
    input_sha256          text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    fields                jsonb NOT NULL,
    answer                jsonb NOT NULL,
    quotes_given          integer NOT NULL CHECK (quotes_given >= 0),
    quotes_found          integer NOT NULL CHECK (quotes_found BETWEEN 0 AND quotes_given),
    fields_dropped        integer NOT NULL CHECK (fields_dropped >= 0),
    attempts              integer NOT NULL CHECK (attempts >= 1),
    input_tokens          integer CHECK (input_tokens >= 0),
    output_tokens         integer CHECK (output_tokens >= 0),
    thinking_tokens       integer CHECK (thinking_tokens >= 0),
    cost_usd              numeric(12, 6) CHECK (cost_usd >= 0),
    made_at               timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, model, instructions_version)
);
