-- What the transactions on the main network were, and the things there (design 7.6, 1 November
-- 2026): read by the step `mainnet_what` from the mirror node and from the project's own code.
--
-- In mainnet_transactions, for each transaction of an own ID:
-- what       what it did, in the ledger's or the code's own words: the function of a contract that
--            it called ("createMeme"), the kind that a JSON message gives itself ("paid"), or a
--            word of the tool ("deployed the contract"); NULL when the kind of the transaction
--            says it all (an HBAR transfer). Who sent it is the payer of its event (ledger_events)
-- networks   the networks that a message of a topic names, as CAIP-2 ("eip155:8453")
-- explained_at   when the step read it; NULL until then
--
-- mainnet_things holds the own IDs on the main network and the things that the accounts which
-- made them also made there, each read once:
-- made_by    the account that paid for its creation
-- name       a token's name and symbol, or the memo of a topic, a schedule or a contract
-- fields     the keys of the JSON messages of a topic, the most common set
-- names_from where the names of a contract's functions come from: its project's own files, or a
--            common library
-- scheduled  what a scheduled transaction holds, in words; executed_at, when it ran
-- held_by_others   the accounts that hold a token now, its treasury apart
-- messages   the messages of a topic so far
-- followed   for an account that made an own ID: "read" when what it made was read, "service"
--            when it made too many accounts to be a team's, so what it made is not followed

ALTER TABLE mainnet_transactions
    ADD COLUMN what text CHECK (length(what) <= 120),
    ADD COLUMN networks text[] NOT NULL DEFAULT '{}',
    ADD COLUMN explained_at timestamptz;

CREATE TABLE mainnet_things (
    entity_id       text PRIMARY KEY CHECK (entity_id ~ '^0\.0\.[0-9]+$'),
    kind            text NOT NULL,
    made_at         timestamptz,
    made_by         text,
    name            text CHECK (length(name) <= 160),
    fields          text[] NOT NULL DEFAULT '{}',
    names_from      text,
    scheduled       text,
    executed_at     timestamptz,
    held_by_others  integer CHECK (held_by_others >= 0),
    messages        bigint CHECK (messages >= 0),
    followed        text CHECK (followed IN ('read', 'service')),
    asked_at        timestamptz NOT NULL
);

CREATE INDEX mainnet_things_made_by ON mainnet_things (made_by);
