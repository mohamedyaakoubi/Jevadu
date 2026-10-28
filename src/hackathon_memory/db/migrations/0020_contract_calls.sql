-- What the calls of the projects' own contracts reached among Hedera's system contracts (design
-- 7.5, 28 October 2026), for each contract on its network and each time that was read: the time
-- of the ledger story of a project that names it.
--
-- read     the calls whose actions were read, at most the limit of check/system_calls.py
-- cut      the contract had more calls in that time than the limit
-- reached  a system contract (0.0.359 for the Token Service) -> the calls that reached it
--
-- A reading made before the end of its time is read again by the next run of the step.

CREATE TABLE contract_calls (
    entity_id  text NOT NULL CHECK (entity_id <> ''),
    network    text NOT NULL CHECK (network IN ('testnet', 'mainnet', 'previewnet')),
    starts_at  timestamptz NOT NULL,
    ends_at    timestamptz NOT NULL CHECK (ends_at > starts_at),
    read       integer NOT NULL CHECK (read >= 0),
    cut        boolean NOT NULL,
    reached    jsonb NOT NULL DEFAULT '{}'::jsonb,
    asked_at   timestamptz NOT NULL,
    PRIMARY KEY (entity_id, network, starts_at, ends_at)
);
