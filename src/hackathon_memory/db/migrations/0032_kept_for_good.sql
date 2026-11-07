-- What a check of a submission learns is kept for good (7 November 2026, his words: "cached forever
-- and not 24hours"): the embedding of its README's words, for its closest projects, and its
-- comparisons by the search model. They are marked `kept`, so that nothing deletes them after a day.
-- A README that changed has a new fingerprint, so its old rows never speak for the new text. What is
-- kept of an idea typed in the box does not change: its fingerprint and its answers, for one day
-- (11 October 2026).
ALTER TABLE idea_embeddings ADD COLUMN kept boolean NOT NULL DEFAULT false;
ALTER TABLE idea_comparisons ADD COLUMN kept boolean NOT NULL DEFAULT false;
