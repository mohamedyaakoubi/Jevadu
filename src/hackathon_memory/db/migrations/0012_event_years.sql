-- The year of an event that no page dates (design 4.6). The events known only from an
-- organiser's list of winners have no start and no end in the tables, so the year in their
-- name was missing from the filters and the overview. A person types the year, from the
-- organiser's own post, into data/by-hand/event-years.txt, and the parse step writes it here.
-- An event with a known start or end keeps the year of its dates.
ALTER TABLE events ADD COLUMN year smallint CHECK (year IS NULL OR year BETWEEN 2015 AND 2100);
