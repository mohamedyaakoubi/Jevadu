-- The visitors of the public copy whom Cloudflare's Turnstile found to be a person (design 12.5,
-- 30 October 2026). A visitor is the same salted hash as in visitor_uses; the pass holds for a
-- day from its last confirmation (web/public.py), and a new one only moves the time.
CREATE TABLE visitor_passes (
    client     text PRIMARY KEY CHECK (client ~ '^[0-9a-f]{64}$'),
    passed_at  timestamptz NOT NULL DEFAULT now()
);
