-- What the search model answered about a typed idea (design 8.2 and 8.3), kept by the fingerprint
-- of the idea only and for one day, like the embedding of the idea (migration 0008): the order of
-- its closest projects, and what is the same and what differs for each project it was compared
-- with. A reload, the back button or the same search again shows them without a new call. The
-- idea itself is kept nowhere. A row older than a day is deleted by the website.

CREATE TABLE idea_orders (
    idea_sha256     text NOT NULL CHECK (idea_sha256 ~ '^[0-9a-f]{64}$'),
    -- The filters of the search, always written the same way; '' when none is chosen.
    scope           text NOT NULL,
    model           text NOT NULL CHECK (model <> ''),
    thinking_level  text NOT NULL,
    version         text NOT NULL CHECK (version <> ''),
    -- What the model read, the closest in meaning first, and its answer, the closest first.
    pool            bigint[] NOT NULL,
    ordered         bigint[] NOT NULL,
    made_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (idea_sha256, scope, model, thinking_level, version)
);

CREATE TABLE idea_comparisons (
    idea_sha256     text NOT NULL CHECK (idea_sha256 ~ '^[0-9a-f]{64}$'),
    project_id      bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    model           text NOT NULL CHECK (model <> ''),
    thinking_level  text NOT NULL,
    version         text NOT NULL CHECK (version <> ''),
    -- The fingerprint of the texts of the project that the model read: a changed card or page
    -- gives a new row, so an old comparison is never shown for new texts.
    input_sha256    text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    same            text NOT NULL,
    differs         text NOT NULL,
    fields_used     text[] NOT NULL,
    made_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (idea_sha256, project_id, model, thinking_level, version, input_sha256)
);
