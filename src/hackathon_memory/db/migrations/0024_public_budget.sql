-- The public copy of the website has a budget of its own (design 12.5, 29 October 2026): its
-- calls to a model are counted under the environment "public", apart from the test work and from
-- the tool in use, so that it never spends their money, nor they its.
ALTER TABLE llm_calls DROP CONSTRAINT llm_calls_environment_check;
ALTER TABLE llm_calls ADD CONSTRAINT llm_calls_environment_check
    CHECK (environment IN ('test', 'prod', 'public'));
