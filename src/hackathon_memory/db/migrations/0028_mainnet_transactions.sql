-- The main network in detail (design 7.6, 1 November 2026): what each transaction of the own IDs
-- of the projects with the tag "Mainnet" cost and moved, read once from the mirror node by its
-- moment of consensus, which names one transaction of the main network. The moments come from the
-- histories of those IDs (ledger_events, migration 0016).
--
-- fee      what the network charged for it (charged_tx_fee), in tinybars: 100,000,000 make 1 HBAR
-- moved    the HBAR that changed hands in it, in tinybars: what the accounts that are not the
--          network's received, apart from the fees and the rewards of staking
-- paid_by  the accounts whose HBAR went out in it, its fee included, without the network's own
-- tokens   how many transfers of a token or an NFT it holds
-- cents, hbars   the exchange rate that the network itself used for its fees at that moment: hbars
--          HBAR were worth cents US cents; NULL when the mirror node did not give it

CREATE TABLE mainnet_transactions (
    stamp     text PRIMARY KEY CHECK (stamp ~ '^[0-9]+\.[0-9]+$'),
    at        timestamptz NOT NULL,
    name      text,
    ok        boolean,
    fee       bigint NOT NULL CHECK (fee >= 0),
    moved     bigint NOT NULL CHECK (moved >= 0),
    paid_by   text[] NOT NULL DEFAULT '{}',
    tokens    integer NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    cents     integer CHECK (cents > 0),
    hbars     integer CHECK (hbars > 0),
    asked_at  timestamptz NOT NULL
);
