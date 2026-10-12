-- The embeddings of the search (design 8.1, 11.6).
--
-- One embedding for each project, each kind of text and each model. It is made again only when
-- its text or its model changes: the fingerprint of the text that was embedded is kept here, and
-- the text itself is in the tables of the project. "page" is the page as it is: the name, the
-- short line and the two texts. The fields of the card come later, as another kind.
--
-- The search compares a question with every row. At this size an exact search needs no index,
-- and the usual index of pgvector stops at 2,000 numbers (design 11.6).
CREATE TABLE project_embeddings (
    project_id   bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    text_kind    text NOT NULL CHECK (text_kind IN ('page')),
    model        text NOT NULL CHECK (model <> ''),
    text_sha256  text NOT NULL CHECK (text_sha256 ~ '^[0-9a-f]{64}$'),
    embedding    vector(3072) NOT NULL,
    tokens       integer CHECK (tokens >= 0),
    -- True when the text was longer than the model reads, and its end was cut.
    truncated    boolean,
    made_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, text_kind, model)
);

-- The embedding of an idea that a builder typed, kept by the fingerprint of the idea only, so
-- that the same idea is not paid for twice in a day. The idea itself is kept nowhere. A row
-- older than a day is deleted by the search (a decision of 11 October 2026: what is kept
-- of a typed idea is a fingerprint, for 24 hours).
CREATE TABLE idea_embeddings (
    idea_sha256  text NOT NULL CHECK (idea_sha256 ~ '^[0-9a-f]{64}$'),
    model        text NOT NULL CHECK (model <> ''),
    embedding    vector(3072) NOT NULL,
    made_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (idea_sha256, model)
);
