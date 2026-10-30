-- What each visitor of the public copy used, one time and for good (design 12.5, 29 October
-- 2026). It replaces the counts of a day of 0023: an allowance is never renewed.
--
-- A visitor is a salted hash of the address that Cloudflare gives and of the name the browser
-- gives itself; the share of an address is counted under a salted hash of the address alone, so
-- that one address holds the allowances of a limited number of visitors. Never a cookie, never an
-- address.
DROP TABLE visitor_counts;

CREATE TABLE visitor_uses (
    scope     text NOT NULL CHECK (scope IN ('visitor', 'address')),
    client    text NOT NULL CHECK (client ~ '^[0-9a-f]{64}$'),
    kind      text NOT NULL CHECK (kind IN ('ai', 'embed', 'check', 'refresh', 'register')),
    count     integer NOT NULL CHECK (count >= 1),
    first_at  timestamptz NOT NULL DEFAULT now(),
    last_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, client, kind)
);

-- Each press of a button of Gemini that a visitor's allowance paid for: the fingerprint of an
-- idea and the button. A press is counted once, however many calls its answer takes, and however
-- often that answer is shown again.
CREATE TABLE visitor_presses (
    client    text NOT NULL CHECK (client ~ '^[0-9a-f]{64}$'),
    press     text NOT NULL CHECK (press ~ '^[0-9a-f]{64}:[a-z0-9:]{1,40}$'),
    at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (client, press)
);
