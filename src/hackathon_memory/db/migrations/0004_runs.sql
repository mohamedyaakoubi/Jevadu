-- One row for every run of a step of the path: what ran, when, and what came out (design 11.6).
--
-- "counts" holds numbers only. "problems" names what could not be done: an address of a page
-- and the rule that failed. It never holds text of a page.
CREATE TABLE runs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    step         text NOT NULL CHECK (step ~ '^[a-z][a-z0-9_]{1,39}$'),
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    -- NULL while the step runs. A row that stays NULL is a run that was cut off.
    ok           boolean,
    counts       jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(counts) = 'object'),
    problems     jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(problems) = 'array'),
    CHECK ((finished_at IS NULL) = (ok IS NULL)),
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX runs_step_time ON runs (step, started_at);
