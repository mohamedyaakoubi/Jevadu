-- A scheduled transaction that a page or a README names (design 7.1, 22 October 2026). HashScan
-- shows one at /schedule/<id>, and the mirror node answers about it at /schedules/<id>. Before,
-- such an ID was asked as a token, a topic, a contract and an account, and so was "not found".

ALTER TABLE hedera_ids DROP CONSTRAINT hedera_ids_said_kind_check;
ALTER TABLE hedera_ids ADD CONSTRAINT hedera_ids_said_kind_check CHECK (
    said_kind IN ('account', 'token', 'topic', 'contract', 'transaction', 'schedule')
);

ALTER TABLE ledger_facts DROP CONSTRAINT ledger_facts_kind_check;
ALTER TABLE ledger_facts ADD CONSTRAINT ledger_facts_kind_check CHECK (
    kind IN ('account', 'token', 'topic', 'contract', 'transaction', 'schedule')
);
