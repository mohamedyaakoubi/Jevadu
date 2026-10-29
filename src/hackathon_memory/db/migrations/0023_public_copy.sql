-- The public copy of the website (design 12.5, 29 October 2026): the same site, served at
-- jevadu.mohamedyaakoubi.com through a Cloudflare tunnel, with the limits of 21 October.
--
-- A switch turns a part of it on: "ai" (the search by meaning, the order and the comparisons of
-- the AI, which cost money) and "register" (a record written on Hedera). With no row, a part is
-- off: nothing costs money and nothing is written until its owner turns it on with a command
-- (python -m hackathon_memory.web.switch).
CREATE TABLE site_switches (
    name        text PRIMARY KEY CHECK (name IN ('ai', 'register')),
    turned_on   boolean NOT NULL,
    changed_at  timestamptz NOT NULL DEFAULT now()
);

-- How many times each visitor used a part that costs something, for each day. A visitor is a
-- salted hash of the address that Cloudflare gives (an IPv6 address by its /64 network), never a
-- cookie and never the address itself. A whole campus can share one address, so the numbers per
-- day are generous, and the meter's caps do the real work for the money.
CREATE TABLE visitor_counts (
    day     date NOT NULL,
    client  text NOT NULL CHECK (client ~ '^[0-9a-f]{64}$'),
    kind    text NOT NULL CHECK (kind IN ('ai', 'check', 'refresh', 'register')),
    count   integer NOT NULL CHECK (count >= 1),
    PRIMARY KEY (day, client, kind)
);
