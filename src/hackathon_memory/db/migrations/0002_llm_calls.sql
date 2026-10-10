-- One line for every call to a model: which model, how many tokens, how long, what it cost.
-- It holds numbers only. The text that was sent and the text that came back are never stored
-- here, so the table can be shown and exported without showing a page or an idea of a user.
--
-- "environment" keeps the test work apart from the running tool: each has its own budget.
-- "cost_usd" is our own count (tokens that Google reported, times the price that Google
-- published on the day of the call). It is NULL when the price of the model is not known.
CREATE TABLE llm_calls (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    called_at       timestamptz NOT NULL DEFAULT now(),
    environment     text NOT NULL CHECK (environment IN ('test', 'prod')),
    purpose         text NOT NULL CHECK (purpose ~ '^[a-z][a-z0-9_]{1,39}$'),
    model           text NOT NULL CHECK (model <> ''),
    thinking_level  text,
    location        text,
    batch           boolean NOT NULL DEFAULT false,
    input_tokens    integer NOT NULL CHECK (input_tokens >= 0),
    output_tokens   integer NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    thinking_tokens integer NOT NULL DEFAULT 0 CHECK (thinking_tokens >= 0),
    cached_tokens   integer NOT NULL DEFAULT 0 CHECK (cached_tokens >= 0),
    latency_ms      integer CHECK (latency_ms >= 0),
    ok              boolean NOT NULL,
    error_kind      text,
    cost_usd        numeric(14, 8) CHECK (cost_usd >= 0),
    price_read_on   date,
    run_id          text,
    item_ref        text
);

-- The budget guard asks "how much was spent in this environment since that moment" before
-- every call, and the report reads one environment over a range of days.
CREATE INDEX llm_calls_environment_time ON llm_calls (environment, called_at);
