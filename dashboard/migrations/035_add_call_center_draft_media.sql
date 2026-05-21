-- Migration 035: Store optional media metadata for Call Center message drafts

ALTER TABLE cc_message_drafts
ADD COLUMN IF NOT EXISTS media_path TEXT,
ADD COLUMN IF NOT EXISTS media_mime_type TEXT,
ADD COLUMN IF NOT EXISTS media_filename TEXT,
ADD COLUMN IF NOT EXISTS media_size INTEGER;
