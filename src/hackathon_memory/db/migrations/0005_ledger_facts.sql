-- What the mirror node said about an id on one network (design 7.1), with the time of the
-- question. There is one row for each id and network. Asking again replaces the row, so the
-- table always holds the newest answer.
--
-- An id that is nothing on a network has a row too, with found = false: "not found" is an
-- answer, and it must not be asked again every time.
CREATE TABLE ledger_facts (
    entity_id          text NOT NULL
                       CHECK (entity_id ~ '^(0\.0\.[1-9][0-9]{0,11}|0x[0-9a-f]{40})$'),
    network            text NOT NULL CHECK (network IN ('mainnet', 'testnet', 'previewnet')),
    asked_at           timestamptz NOT NULL,
    found              boolean NOT NULL,
    kind               text CHECK (kind IN ('account', 'token', 'topic', 'contract')),
    -- The id that the ledger gives the thing. It differs from entity_id for an EVM address.
    ledger_id          text,
    created_at         timestamptz,
    deleted            boolean NOT NULL DEFAULT false,
    first_activity_at  timestamptz,
    last_activity_at   timestamptz,
    -- The messages of a topic. The other kinds are not counted.
    activity_count     bigint CHECK (activity_count >= 0),
    -- A topic with no message, a token of which no unit exists.
    is_empty           boolean,
    details            jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    PRIMARY KEY (entity_id, network),
    CHECK (found = (kind IS NOT NULL)),
    CHECK (found OR (ledger_id IS NULL AND created_at IS NULL AND NOT deleted)),
    CHECK (
        first_activity_at IS NULL OR last_activity_at IS NULL
        OR first_activity_at <= last_activity_at
    )
);

-- The one more question of the proof rule (design 7.2): was the thing used inside this time?
-- It is asked only for a thing that was used both before and after the window of an event.
CREATE TABLE ledger_use (
    entity_id  text NOT NULL,
    network    text NOT NULL,
    since      timestamptz NOT NULL,
    until      timestamptz NOT NULL,
    used       boolean NOT NULL,
    asked_at   timestamptz NOT NULL,
    PRIMARY KEY (entity_id, network, since, until),
    FOREIGN KEY (entity_id, network) REFERENCES ledger_facts (entity_id, network)
        ON DELETE CASCADE,
    CHECK (since < until)
);

-- What the proof rule says about each id of a project on each network that was asked
-- (design 7.2). It is computed from the facts and never typed in. It is kept in a table so that
-- a list of projects can be filtered by it.
CREATE TABLE id_checks (
    hedera_id   bigint NOT NULL REFERENCES hedera_ids (id) ON DELETE CASCADE,
    network     text NOT NULL CHECK (network IN ('mainnet', 'testnet', 'previewnet')),
    status      text NOT NULL CHECK (status IN (
                    'proof_found', 'window_not_known', 'dates_do_not_fit', 'found_but_empty',
                    'another_kind', 'cannot_be_checked', 'not_found')),
    judged_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (hedera_id, network)
);

-- The best status over the ids of a project. A project with no id says so. NULL means that the
-- check has not looked at the project yet, or not since its page was read again.
ALTER TABLE projects
    ADD COLUMN proof_status text
    CHECK (proof_status IN (
        'proof_found', 'window_not_known', 'dates_do_not_fit', 'found_but_empty',
        'another_kind', 'cannot_be_checked', 'not_found', 'no_id_given'));
