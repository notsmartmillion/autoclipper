CREATE TABLE creators (
  id SERIAL PRIMARY KEY,
  handle TEXT NOT NULL,
  platform TEXT NOT NULL,            -- youtube|twitch|kick
  source_url TEXT NOT NULL,
  license_type TEXT NOT NULL,        -- contract|cc-by|campaign
  post_channel_id TEXT NOT NULL,     -- destination YT channel
  brand_preset TEXT NOT NULL DEFAULT 'default',
  max_daily INT NOT NULL DEFAULT 8,
  shorts_only BOOLEAN NOT NULL DEFAULT TRUE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  unique (platform, handle)
);

CREATE TABLE videos (
  id BIGSERIAL PRIMARY KEY,
  creator_id INT REFERENCES creators(id),
  source_id TEXT NOT NULL,           -- YT video ID, Twitch VOD ID, etc.
  duration_s INT,
  transcript_url TEXT,
  status TEXT NOT NULL DEFAULT 'queued',  -- queued|fetched|analyzed|failed
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE clips (
  id BIGSERIAL PRIMARY KEY,
  video_id BIGINT REFERENCES videos(id),
  start_s INT NOT NULL,
  end_s INT NOT NULL,
  transcript_snippet TEXT,
  local_path TEXT,
  s3_key TEXT,
  status TEXT NOT NULL DEFAULT 'rendered', -- rendered|uploaded|published|failed
  claim_status TEXT DEFAULT 'unknown',     -- unknown|clean|claimed|struck
  public_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE uploads (
  id BIGSERIAL PRIMARY KEY,
  clip_id BIGINT REFERENCES clips(id),
  platform TEXT NOT NULL DEFAULT 'youtube',
  remote_video_id TEXT,
  visibility TEXT NOT NULL DEFAULT 'unlisted', -- unlisted|public|private
  scheduled_for TIMESTAMPTZ,
  error TEXT
);
