-- The depth of use of each own Hedera ID (design 7.5, 25 October 2026): what each transaction of
-- its history was, as check/history.py reads it, and the accounts that hold a token now.
--
-- name     its kind as the mirror node names it, such as CRYPTOTRANSFER or TOKENMINT
-- ok       it succeeded; NULL when the mirror node does not say
-- payer    the account that paid for it, or the EVM address of a contract's caller
-- parties  the accounts that took part, without the network's own (its node, its fee accounts)
--
-- A history read before this has none of it (depth 0). The step `history --again` reads such a
-- history again, whole, once; the step `refresh` then reads only its new transactions.

ALTER TABLE ledger_events
    ADD COLUMN name    text,
    ADD COLUMN ok      boolean,
    ADD COLUMN payer   text,
    ADD COLUMN parties text[] NOT NULL DEFAULT '{}';

ALTER TABLE ledger_histories
    ADD COLUMN depth       smallint NOT NULL DEFAULT 0 CHECK (depth >= 0),
    -- a token: the accounts that hold it now (the first 500), and whether more do
    ADD COLUMN holders     text[],
    ADD COLUMN holders_cut boolean NOT NULL DEFAULT false;
