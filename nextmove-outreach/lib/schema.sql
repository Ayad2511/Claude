-- Next Move Marketing — Database Schema
-- Draai via: npx ts-node scripts/migrate.ts

CREATE TABLE IF NOT EXISTS leads (
  id                SERIAL PRIMARY KEY,
  first_name        TEXT,
  last_name         TEXT,
  email             TEXT UNIQUE,
  company_name      TEXT,
  instagram_handle  TEXT,
  linkedin_url      TEXT,
  niche             TEXT,
  source            TEXT NOT NULL DEFAULT 'clay',
  status            TEXT NOT NULL DEFAULT 'te_contacteren',
  -- 'te_contacteren' → 'email_1' → 'followup_1/2/3' → 'geantwoord' / 'niet_geinteresseerd'
  heygen_video_url  TEXT,
  heygen_video_id   TEXT,
  clay_row_id       TEXT UNIQUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outreach_log (
  id              SERIAL PRIMARY KEY,
  lead_id         INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  channel         TEXT NOT NULL,  -- 'email' | 'linkedin' | 'instagram'
  template_key    TEXT,
  sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  success         BOOLEAN NOT NULL DEFAULT FALSE,
  error_message   TEXT,
  external_id     TEXT   -- Lemlist/Phantombuster campaign or message ID
);

CREATE TABLE IF NOT EXISTS inbox_messages (
  id              SERIAL PRIMARY KEY,
  lead_id         INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  channel         TEXT NOT NULL,     -- 'email' | 'linkedin' | 'instagram'
  direction       TEXT NOT NULL,     -- 'inbound' | 'outbound'
  subject         TEXT,
  content         TEXT,
  sender_email    TEXT,
  external_id     TEXT UNIQUE,       -- Lemlist reply ID / LinkedIn message ID
  received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  read            BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS daily_limits (
  id          SERIAL PRIMARY KEY,
  date        DATE NOT NULL DEFAULT CURRENT_DATE,
  channel     TEXT NOT NULL,   -- 'email' | 'linkedin' | 'instagram' | 'video'
  count       INTEGER NOT NULL DEFAULT 0,
  UNIQUE(date, channel)
);

-- Automatisch updated_at bijwerken bij wijzigingen
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS leads_updated_at ON leads;
CREATE TRIGGER leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Index voor snelle lookups
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_outreach_lead_id ON outreach_log(lead_id);
CREATE INDEX IF NOT EXISTS idx_outreach_channel ON outreach_log(channel, sent_at);
CREATE INDEX IF NOT EXISTS idx_inbox_lead_id ON inbox_messages(lead_id);
CREATE INDEX IF NOT EXISTS idx_inbox_unread ON inbox_messages(read, received_at DESC);
