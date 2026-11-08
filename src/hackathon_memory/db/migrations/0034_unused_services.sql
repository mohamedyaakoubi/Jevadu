-- The services that only files that nothing uses name (design 7.3, 8 November 2026): no other file
-- imports those files and no program starts there, so their services are not counted as calls
-- (parse/hedera_code.py, format 4). They are kept under a kind of their own, so that a card and a
-- check show them apart from the calls, and every reader of the calls (kind 'feature') stays as it
-- was.
ALTER TABLE hedera_in_code DROP CONSTRAINT hedera_in_code_kind_check;
ALTER TABLE hedera_in_code ADD CONSTRAINT hedera_in_code_kind_check
    CHECK (kind IN ('package', 'feature', 'unused', 'sign', 'import', 'mention'));
