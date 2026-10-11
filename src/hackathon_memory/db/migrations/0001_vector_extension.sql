-- Turns on the pgvector add-on, which lets PostgreSQL store and compare embeddings
-- (design sections 8.1 and 11.1). No table yet: the tables of the data model (design
-- section 10) come with Phase B, each in its own numbered file.
CREATE EXTENSION IF NOT EXISTS vector;
