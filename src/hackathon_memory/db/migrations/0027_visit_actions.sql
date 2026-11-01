-- What the visitors of the public copy do (design 12.5, screen S9, 1 November 2026): one row for
-- each action, under the visitor's salted code (the key of web/public.py, its first 12
-- characters), never an address or a name; with the place that Vercel finds for the address, the
-- other site the visitor came from, and the browser and the system in two words. The copy's owner
-- is left out, reads the rows on /owner/visits, and deletes them when the event is over.
CREATE TABLE visit_actions (
    id        bigserial PRIMARY KEY,
    at        timestamptz NOT NULL DEFAULT now(),
    visitor   text NOT NULL,
    action    text NOT NULL,
    detail    jsonb NOT NULL DEFAULT '{}'::jsonb,
    path      text NOT NULL,
    country   text,
    region    text,
    city      text,
    referrer  text,
    device    text
);
CREATE INDEX visit_actions_by_visitor ON visit_actions (visitor, at);
