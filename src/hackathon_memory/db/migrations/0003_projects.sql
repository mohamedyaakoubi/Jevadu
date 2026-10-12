-- What the parser reads from a saved project page (design 10): the project, its event, its
-- prizes, its links, its texts and its Hedera ids.
--
-- Nothing here is written by a model, and nothing here is about a person: there is no column
-- for a team member or an author (design rule 11).
--
-- Every row can be made again from the saved pages with one command (design rule 5). So a
-- project keeps the fingerprint of the page that it was read from and the version of the parser
-- that read it. A page is read again only when one of the two has changed.

CREATE TABLE events (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site       text NOT NULL CHECK (site <> ''),
    slug       text NOT NULL CHECK (slug <> ''),
    name       text NOT NULL CHECK (name <> ''),
    -- The start comes from the page of a project. No page gives the end, so it is typed in.
    starts_at  timestamptz,
    ends_on    date,
    UNIQUE (site, slug),
    CHECK (ends_on IS NULL OR starts_at IS NULL OR ends_on >= starts_at::date)
);

CREATE TABLE projects (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site         text NOT NULL CHECK (site <> ''),
    page_url     text NOT NULL UNIQUE CHECK (page_url LIKE 'https://%'),
    site_key     text NOT NULL CHECK (site_key <> ''),
    -- A full card comes from the team's own page. A winner entry comes from an organiser's list
    -- of winners, where the submission pages are no longer public (design 4.6).
    entry_kind   text NOT NULL CHECK (entry_kind IN ('full_card', 'winner_entry')),
    event_id     bigint NOT NULL REFERENCES events (id),
    name         text NOT NULL CHECK (name <> ''),
    short_line   text NOT NULL,
    prize_state  text NOT NULL CHECK (prize_state IN ('hedera_prize', 'other_prize', 'no_prize')),
    has_video    boolean NOT NULL,
    page_sha256  text NOT NULL CHECK (page_sha256 ~ '^[0-9a-f]{64}$'),
    parser       text NOT NULL CHECK (parser <> ''),
    parsed_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX projects_event ON projects (event_id);

CREATE TABLE prizes (
    project_id  bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    position    smallint NOT NULL CHECK (position >= 1),
    sponsor     text NOT NULL CHECK (sponsor <> ''),
    sponsor_id  text,
    track       text NOT NULL,
    award       text NOT NULL,
    kind        text,
    pool        boolean NOT NULL,
    -- The line as the page shows it.
    line        text NOT NULL CHECK (line <> ''),
    PRIMARY KEY (project_id, position)
);

CREATE TABLE links (
    project_id  bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    position    smallint NOT NULL CHECK (position >= 1),
    kind        text NOT NULL CHECK (kind IN ('code', 'demo', 'other')),
    url         text NOT NULL CHECK (url ~* '^https?://'),
    label       text NOT NULL,
    PRIMARY KEY (project_id, position)
);

-- A titled text of the page, copied word for word. "body" has one block on each line, and
-- "blocks" keeps the same words block by block (a paragraph, an item, a title, code).
CREATE TABLE sections (
    project_id  bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    position    smallint NOT NULL CHECK (position >= 1),
    kind        text NOT NULL CHECK (kind <> ''),
    title       text NOT NULL,
    body        text NOT NULL,
    blocks      jsonb NOT NULL CHECK (jsonb_typeof(blocks) = 'array'),
    PRIMARY KEY (project_id, position),
    UNIQUE (project_id, kind)
);

-- An id that a project gives, with what the text around it says. The same number is another
-- thing on each network (design 7.1), so the network is part of the row. It is NULL when the
-- text leaves it open: then both networks are asked.
CREATE TABLE hedera_ids (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id        bigint NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    entity_id         text NOT NULL
                      CHECK (entity_id ~ '^(0\.0\.[1-9][0-9]{0,11}|0x[0-9a-f]{40})$'),
    network           text CHECK (network IN ('mainnet', 'testnet', 'previewnet')),
    said_kind         text CHECK (said_kind IN ('account', 'token', 'topic', 'contract')),
    -- Where it stands: on the page of the project, or in the README of its code.
    found_in          text NOT NULL CHECK (found_in IN ('page', 'readme')),
    words_around      text NOT NULL,
    in_hashscan_link  boolean NOT NULL,
    UNIQUE NULLS NOT DISTINCT (project_id, entity_id, network, found_in)
);

CREATE INDEX hedera_ids_entity ON hedera_ids (entity_id, network);
