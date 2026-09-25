-- Preserve the original WhatsApp user JID (especially @lid) for replies.
ALTER TABLE cc_conversations
ADD COLUMN IF NOT EXISTS wa_jid TEXT;

CREATE INDEX IF NOT EXISTS idx_cc_conversations_wa_jid
ON cc_conversations (wa_jid)
WHERE wa_jid IS NOT NULL;
