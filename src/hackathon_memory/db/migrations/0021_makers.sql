-- Who made each Hedera thing that the ledger knows (design 7.5, 29 October 2026): the account that
-- paid for the transaction that created a contract, a topic, a token or a schedule, from the
-- mirror node (check/makers.py, the step "makers"). A thing made long before its project's event,
-- by an account that made none of the project's other things, can be someone else's: OmniShield's
-- README gave the price oracle of Pyth as one of its contracts, made 20 months before its event.
ALTER TABLE ledger_facts
    ADD COLUMN made_by text CHECK (made_by ~ '^0\.0\.[0-9]+$'),
    -- when the mirror node was asked; with made_by NULL, it gave no account
    ADD COLUMN made_by_asked_at timestamptz,
    ADD CHECK (made_by IS NULL OR made_by_asked_at IS NOT NULL);
