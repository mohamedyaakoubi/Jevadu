-- A single transaction that a page or a README names (design 7.1, 18 October 2026). Its ID is
-- the account that paid for it and the moment it was sent, written the way the mirror node asks
-- for it: "0.0.12345-1700000000-123456789" (seconds, then nanoseconds). The mirror node refuses
-- the form "0.0.12345@1700000000.123456789", so the parser writes every ID in the first form.

ALTER TABLE hedera_ids DROP CONSTRAINT hedera_ids_entity_id_check;
ALTER TABLE hedera_ids ADD CONSTRAINT hedera_ids_entity_id_check CHECK (
    entity_id ~ '^(0\.0\.[1-9][0-9]{0,11}|0x[0-9a-f]{40}|0\.0\.[1-9][0-9]{0,11}-[0-9]{1,11}-[0-9]{1,9})$'
);
ALTER TABLE hedera_ids DROP CONSTRAINT hedera_ids_said_kind_check;
ALTER TABLE hedera_ids ADD CONSTRAINT hedera_ids_said_kind_check CHECK (
    said_kind IN ('account', 'token', 'topic', 'contract', 'transaction')
);

ALTER TABLE ledger_facts DROP CONSTRAINT ledger_facts_entity_id_check;
ALTER TABLE ledger_facts ADD CONSTRAINT ledger_facts_entity_id_check CHECK (
    entity_id ~ '^(0\.0\.[1-9][0-9]{0,11}|0x[0-9a-f]{40}|0\.0\.[1-9][0-9]{0,11}-[0-9]{1,11}-[0-9]{1,9})$'
);
ALTER TABLE ledger_facts DROP CONSTRAINT ledger_facts_kind_check;
ALTER TABLE ledger_facts ADD CONSTRAINT ledger_facts_kind_check CHECK (
    kind IN ('account', 'token', 'topic', 'contract', 'transaction')
);
