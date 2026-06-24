-- business_card_agent schema (Postgres + pgvector replacement for the original
-- Supabase project). Run once against the business_card_agent database.
-- text-embedding-3-small produces 1536-dim vectors.

CREATE TABLE IF NOT EXISTS contacts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT,
    designation      TEXT,
    company          TEXT,
    email            TEXT,
    mobile           TEXT,
    telephone        TEXT,
    website          TEXT,
    address          TEXT,
    contact_type     TEXT,
    category         TEXT,
    subcategory      TEXT,
    company_summary  TEXT,
    ai_tags          JSONB DEFAULT '[]'::jsonb,
    keywords         JSONB DEFAULT '[]'::jsonb,
    embedding        VECTOR(1536),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contacts_created_at_idx ON contacts (created_at DESC);
CREATE INDEX IF NOT EXISTS contacts_contact_type_idx ON contacts (contact_type);
CREATE INDEX IF NOT EXISTS contacts_category_idx ON contacts (category);

-- Approximate nearest-neighbor index for semantic search (cosine distance).
-- Safe to create even with few rows; ivfflat just won't be selective until
-- the table grows, but the planner can still use a seq scan until then.
CREATE INDEX IF NOT EXISTS contacts_embedding_idx
    ON contacts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Replaces the Supabase RPC `match_contacts(query_embedding, match_count)`.
CREATE OR REPLACE FUNCTION match_contacts(query_embedding VECTOR(1536), match_count INT DEFAULT 5)
RETURNS SETOF contacts
LANGUAGE sql STABLE
AS $$
    SELECT *
    FROM contacts
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;
