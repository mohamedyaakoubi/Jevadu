-- A token that a transaction moved on the main network is named by its symbol and its ID since
-- 3 November 2026 (design 7.6): a symbol is only the name that a token's maker chose, and two
-- tokens can share one. The explanations that named the symbol alone are read again by the step
-- `mainnet_what`, which explains only what has no explanation.
UPDATE mainnet_transactions SET what = NULL, explained_at = NULL
WHERE what LIKE 'moved %' AND what !~ '\(0\.0\.[0-9]+\)';

-- SAUCE, the token of SaucerSwap, an exchange on Hedera, is a public service as USDC is: a token
-- that its owner runs for everyone. SaucerSwap's page "SAUCE tokenomics" gives its token ID
-- 0.0.731861 and its EVM address (read on 3 November 2026). No project of the collection names it.
INSERT INTO public_services (network, ledger_id, evm_address, name, source, read_on) VALUES
    ('mainnet', '0.0.731861', '0x00000000000000000000000000000000000b2ad5',
     'SAUCE, the token of SaucerSwap', 'https://docs.saucerswap.finance/tokenomics/overview',
     '2026-11-03')
ON CONFLICT (network, ledger_id) DO NOTHING;
