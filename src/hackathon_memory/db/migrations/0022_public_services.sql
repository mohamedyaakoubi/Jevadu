-- Public services that many projects use (design 8.4, 29 October 2026): a contract, a topic or a
-- token that its owner runs for everyone, such as a price oracle. A project that names one does not
-- own it, so its transactions are not the project's (the strip, the time before and after, the
-- depth of use), and the card says what it is. Each row comes from its owner's own published list,
-- with the day it was read; nothing goes in on a guess.
--
-- The first: OmniShield's README gave the price oracle of Pyth as one of its contracts, and its card
-- drew 20 months of Pyth's calls as the project's. Pyth's list gives one EVM address for its price
-- feed contract on 40 chains, "hedera_testnet" and "hedera" among them; the mirror node gives its
-- 0.0 ID on each network (read on 29 October 2026). Then USDC, the dollar token of Circle, which
-- the step "makers" showed among the own things of a project: Circle's page of USDC addresses gives
-- 0.0.456858 for Hedera and 0.0.429274 for Hedera Testnet (read on 29 October 2026).
CREATE TABLE public_services (
    network      text NOT NULL CHECK (network IN ('mainnet', 'testnet', 'previewnet')),
    ledger_id    text NOT NULL CHECK (ledger_id ~ '^0\.0\.[0-9]+$'),
    evm_address  text CHECK (evm_address ~ '^0x[0-9a-f]{40}$'),
    name         text NOT NULL CHECK (name <> ''),
    source       text NOT NULL CHECK (source ~ '^https://'),
    read_on      date NOT NULL,
    PRIMARY KEY (network, ledger_id)
);

INSERT INTO public_services (network, ledger_id, evm_address, name, source, read_on) VALUES
    ('testnet', '0.0.3042133', '0xa2aa501b19aff244d90cc15a4cf739d2725b5729', 'the price oracle of Pyth',
     'https://github.com/pyth-network/pyth-crosschain/blob/main/contract_manager/src/store/contracts/EvmPriceFeedContracts.json',
     '2026-10-29'),
    ('mainnet', '0.0.4622850', '0xa2aa501b19aff244d90cc15a4cf739d2725b5729', 'the price oracle of Pyth',
     'https://github.com/pyth-network/pyth-crosschain/blob/main/contract_manager/src/store/contracts/EvmPriceFeedContracts.json',
     '2026-10-29'),
    ('mainnet', '0.0.456858', NULL, 'USDC, the dollar token of Circle',
     'https://developers.circle.com/stablecoins/usdc-contract-addresses', '2026-10-29'),
    ('testnet', '0.0.429274', NULL, 'USDC, the dollar token of Circle',
     'https://developers.circle.com/stablecoins/usdc-contract-addresses', '2026-10-29');
