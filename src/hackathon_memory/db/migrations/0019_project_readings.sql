-- What each reading of a project found (design 7.3, 28 October 2026): a reading by the button of
-- its card ("button"), by a round of the website ("round") or by the step `refresh` ("refresh")
-- compares what the tool holds about the project before and after it.
--
-- changes  what changed, each a sentence in plain words, such as "README changed"; empty when
--          nothing did. A round or the step keeps a row only when something changed; the button
--          keeps one in every case, so that its card can say that nothing changed.

CREATE TABLE project_readings (
    project_id  bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    read_at     timestamptz NOT NULL,
    source      text NOT NULL CHECK (source IN ('button', 'round', 'refresh')),
    changes     text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (project_id, read_at)
);
