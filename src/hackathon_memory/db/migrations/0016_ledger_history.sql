-- The history of each own Hedera ID on the ledger, for the ledger story (evals/ledger_story):
-- every event of the ID, read once from the mirror node, with the Hedera service that it belongs
-- to. An event is one moment of consensus. ledger_histories says which IDs were read, when, how
-- many events they gave, and whether the limit cut the history (check/history.py).

CREATE TABLE ledger_histories (
    entity_id   text NOT NULL,
    network     text NOT NULL CHECK (network IN ('mainnet', 'testnet', 'previewnet')),
    kind        text NOT NULL CHECK (kind IN ('account', 'topic', 'token', 'contract', 'schedule',
                                              'transaction')),
    asked_at    timestamptz NOT NULL,
    events      integer NOT NULL CHECK (events >= 0),
    cut         boolean NOT NULL,
    PRIMARY KEY (entity_id, network)
);

CREATE TABLE ledger_events (
    entity_id   text NOT NULL,
    network     text NOT NULL,
    -- The moment of consensus as the mirror node writes it: seconds.nanoseconds.
    stamp       text NOT NULL CHECK (stamp ~ '^[0-9]+\.[0-9]+$'),
    at          timestamptz NOT NULL,
    service     text NOT NULL CHECK (service IN ('consensus', 'tokens', 'contracts', 'scheduled',
                                                 'files', 'hbar')),
    PRIMARY KEY (entity_id, network, stamp),
    FOREIGN KEY (entity_id, network) REFERENCES ledger_histories (entity_id, network)
        ON DELETE CASCADE
);
