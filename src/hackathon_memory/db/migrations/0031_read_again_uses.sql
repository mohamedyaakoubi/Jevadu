-- The presses of the button "Read again now" (design 7.3): one press every 3 hours for each
-- repository that is checked and for each project on its card, whoever presses (6 November 2026).
-- `what` is a repository's link, or "project:<id>" for the button of a card. One row for each: only
-- the last press matters. Nothing here says who pressed.
CREATE TABLE read_again_uses (
    what    text        PRIMARY KEY,
    used_at timestamptz NOT NULL
);
