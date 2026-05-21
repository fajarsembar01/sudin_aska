#!/usr/bin/env node

/**
 * WhatsApp Bridge — Call Center
 *
 * Separate from the ASKA AI bridge. Uses its own WA session/number.
 * Forwards incoming messages to the dashboard backend and exposes an
 * Express HTTP API so the dashboard can send outbound replies.
 *
 * Environment variables (prefix ASKA_CC_*):
 *   ASKA_CC_WHATSAPP_INTERNAL_TOKEN  — shared secret (required)
 *   ASKA_CC_WHATSAPP_INTERNAL_URL    — backend inbound URL
 *   ASKA_CC_WHATSAPP_SESSION_PATH    — local auth persistence
 *   ASKA_CC_WHATSAPP_CLIENT_ID       — whatsapp-web.js clientId
 *   ASKA_CC_WHATSAPP_STATUS_PATH     — runtime status JSON
 *   ASKA_CC_HTTP_PORT                — Express port (default 3100)
 */

const fs = require("fs");
const path = require("path");

const axios = require("axios");
const express = require("express");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");

// ── helpers ──────────────────────────────────────────────────────────────────

function loadDotEnvFile(filePath) {
    try {
        if (!fs.existsSync(filePath)) return;
        const raw = fs.readFileSync(filePath, "utf8");
        for (const line of raw.split(/\r?\n/)) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith("#")) continue;
            const eqIdx = trimmed.indexOf("=");
            if (eqIdx <= 0) continue;
            const key = trimmed.slice(0, eqIdx).trim();
            const value = trimmed.slice(eqIdx + 1).trim();
            if (key && !(key in process.env)) process.env[key] = value;
        }
    } catch (err) {
        console.warn("[CC] Gagal membaca .env:", (err && err.message) || err);
    }
}

loadDotEnvFile(path.resolve(process.cwd(), ".env"));

// ── config ───────────────────────────────────────────────────────────────────

const INTERNAL_URL = (
    process.env.ASKA_CC_WHATSAPP_INTERNAL_URL ||
    "http://127.0.0.1:5002/api/callcenter/inbound"
).trim();
const IMPORT_URL = (
    process.env.ASKA_CC_WHATSAPP_IMPORT_URL ||
    INTERNAL_URL.replace(/\/inbound\/?$/, "/import-history")
).trim();
const INTERNAL_TOKEN = (process.env.ASKA_CC_WHATSAPP_INTERNAL_TOKEN || "").trim();
const SESSION_PATH = path.resolve(
    process.env.ASKA_CC_WHATSAPP_SESSION_PATH || ".wa_cc_session"
);
const CLIENT_ID = (process.env.ASKA_CC_WHATSAPP_CLIENT_ID || "cc-main").trim();
const STATUS_PATH = path.resolve(
    process.env.ASKA_CC_WHATSAPP_STATUS_PATH || "runtime/whatsapp_cc_status.json"
);
const HTTP_PORT = parseInt(process.env.ASKA_CC_HTTP_PORT || "3100", 10);
const MAX_MEDIA_BYTES = parseInt(process.env.ASKA_CC_MEDIA_MAX_BYTES || "20971520", 10);
const MAX_PDF_RAW_BYTES = parseInt(process.env.ASKA_CC_PDF_RAW_MAX_BYTES || String(MAX_MEDIA_BYTES), 10);
const MAX_PDF_BYTES = parseInt(process.env.ASKA_CC_PDF_MAX_BYTES || "307200", 10);
const MAX_FILE_BYTES = parseInt(process.env.ASKA_CC_FILE_MAX_BYTES || "307200", 10);
const MAX_OUTBOUND_MEDIA_BYTES = parseInt(
    process.env.ASKA_CC_OUTBOUND_MEDIA_MAX_BYTES ||
    process.env.ASKA_CC_DRAFT_MEDIA_MAX_BYTES ||
    "1048576",
    10
);

if (!INTERNAL_TOKEN) {
    console.error("[CC] ASKA_CC_WHATSAPP_INTERNAL_TOKEN belum diset. Worker dihentikan.");
    process.exit(1);
}

// ── status file ──────────────────────────────────────────────────────────────

function writeStatus(patch) {
    try {
        const dir = path.dirname(STATUS_PATH);
        fs.mkdirSync(dir, { recursive: true });
        let base = {};
        if (fs.existsSync(STATUS_PATH)) {
            try { base = JSON.parse(fs.readFileSync(STATUS_PATH, "utf8")) || {}; }
            catch (_) { base = {}; }
        }
        fs.writeFileSync(
            STATUS_PATH,
            JSON.stringify({ ...base, ...patch, updatedAt: new Date().toISOString() }, null, 2),
            "utf8"
        );
    } catch (err) {
        console.error("[CC] Gagal menulis status:", (err && err.message) || err);
    }
}

// ── utilities ────────────────────────────────────────────────────────────────

function normalizeNumber(jid) {
    return (String(jid || "").split("@")[0] || "").replace(/\D/g, "") || "";
}

function estimateBase64Bytes(data) {
    const clean = String(data || "").replace(/\s+/g, "");
    if (!clean) return 0;
    const padding = clean.endsWith("==") ? 2 : (clean.endsWith("=") ? 1 : 0);
    return Math.max(0, Math.floor((clean.length * 3) / 4) - padding);
}

function mediaFallbackText(mimeType) {
    const clean = String(mimeType || "").toLowerCase();
    if (clean.startsWith("image/")) return "[Gambar]";
    if (clean === "application/pdf") return "[PDF]";
    return "[Media]";
}

function isAllowedMediaMime(mimeType) {
    const clean = String(mimeType || "").toLowerCase();
    return clean.startsWith("image/") || [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
    ].includes(clean);
}

function mediaSizeLimit(mimeType) {
    const clean = String(mimeType || "").toLowerCase();
    if (clean.startsWith("image/")) return MAX_MEDIA_BYTES;
    if (clean === "application/pdf") return MAX_PDF_BYTES;
    return MAX_FILE_BYTES;
}

function inboundMediaSizeLimit(mimeType) {
    const clean = String(mimeType || "").toLowerCase();
    if (clean === "application/pdf") return MAX_PDF_RAW_BYTES;
    return mediaSizeLimit(clean);
}

function outboundMediaSizeLimit() {
    return MAX_OUTBOUND_MEDIA_BYTES;
}

async function buildMediaPayload(msg) {
    if (!msg || !msg.hasMedia) return null;
    const msgType = String(msg.type || "").toLowerCase();
    if (msgType && !["image", "document"].includes(msgType)) return null;
    try {
        const media = await msg.downloadMedia();
        if (!media || !media.data || !media.mimetype) return null;
        if (!isAllowedMediaMime(media.mimetype)) return null;

        const size = estimateBase64Bytes(media.data);
        const limit = inboundMediaSizeLimit(media.mimetype);
        if (Number.isFinite(limit) && limit > 0 && size > limit) {
            console.warn(`[CC] media skipped: size=${size} limit=${limit} mimetype=${media.mimetype}`);
            return null;
        }

        return {
            mimetype: media.mimetype,
            filename: media.filename || (msg._data && msg._data.filename) || "",
            data: media.data,
            size,
        };
    } catch (err) {
        console.error("[CC] downloadMedia error:", (err && err.message) || err);
        return null;
    }
}

const processedIds = new Set();
const ignoredIds = new Set();
let clientReady = false;
let lastHeartbeat = Date.now(); // untuk watchdog deteksi Chromium crash

// ── WhatsApp client ──────────────────────────────────────────────────────────

const client = new Client({
    authStrategy: new LocalAuth({ clientId: CLIENT_ID, dataPath: SESSION_PATH }),
    puppeteer: {
        headless: true,
        protocolTimeout: 300000,
        args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
    },
    webVersionCache: { type: "remote", remotePath: "https://raw.githubusercontent.com/nicholasdai/nicholasdai/refs/heads/master/nicholasdai" },
});

client.on("qr", (qrText) => {
    writeStatus({ state: "qr", qrText, message: "Scan QR dari WhatsApp Linked Devices." });
    console.log("\n[CC] Scan QR berikut di WhatsApp Linked Devices:\n");
    qrcode.generate(qrText, { small: true });
});

client.on("authenticated", () => {
    writeStatus({ state: "authenticated", qrText: "", message: "Authenticated." });
    console.log("[CC] Authenticated.");
});

client.on("ready", () => {
    clientReady = true;
    lastHeartbeat = Date.now();
    writeStatus({ state: "ready", qrText: "", message: "Call Center bridge siap." });
    console.log("[CC] Bridge siap menerima chat.");
    startWatchdog();
});

client.on("auth_failure", (msg) => {
    clientReady = false;
    writeStatus({ state: "auth_failure", qrText: "", message: String(msg) });
    console.error("[CC] Auth failure:", msg);
});

client.on("disconnected", (reason) => {
    clientReady = false;
    writeStatus({ state: "disconnected", qrText: "", message: String(reason) });
    console.warn("[CC] Disconnected:", reason);
    setTimeout(() => {
        client.initialize().catch((e) =>
            console.error("[CC] Reinit error:", (e && e.message) || e)
        );
    }, 3000);
});

// ── Watchdog: deteksi Chromium crash tanpa event disconnected ───────────────
// Jika bridge mengklaim ready tapi Chromium tidak responsif selama
// WATCHDOG_TIMEOUT_MS, reinitialize otomatis (tanpa hapus session = tanpa QR).

const WATCHDOG_INTERVAL_MS = 2 * 60 * 1000;  // cek setiap 2 menit
const WATCHDOG_TIMEOUT_MS  = 5 * 60 * 1000;  // anggap crash jika > 5 menit tak responsif
let watchdogTimer = null;
let watchdogRunning = false;

async function pingClient() {
    try {
        // getState() akan throw jika Chromium sudah mati
        const state = await client.getState();
        if (state) lastHeartbeat = Date.now();
    } catch (_) {
        // Chromium tidak responsif — biarkan watchdog menangani
    }
}

function startWatchdog() {
    if (watchdogRunning) return;
    watchdogRunning = true;
    console.log("[CC] Watchdog aktif — cek Chromium setiap 2 menit.");

    watchdogTimer = setInterval(async () => {
        if (!clientReady) return; // biarkan flow normal yang tangani non-ready
        await pingClient();
        const elapsed = Date.now() - lastHeartbeat;
        if (elapsed > WATCHDOG_TIMEOUT_MS) {
            console.warn(`[CC] Watchdog: Chromium tidak responsif ${Math.round(elapsed/1000)}s. Reinit...`);
            clientReady = false;
            lastHeartbeat = Date.now(); // reset agar tidak trigger lagi segera
            writeStatus({ state: "disconnected", qrText: "", message: "Watchdog: koneksi terputus, mencoba reconnect..." });
            try {
                await client.destroy();
            } catch (_) { /* abaikan */ }
            setTimeout(() => {
                client.initialize().catch((e) =>
                    console.error("[CC] Watchdog reinit error:", (e && e.message) || e)
                );
            }, 3000);
        }
    }, WATCHDOG_INTERVAL_MS);
}

// ── incoming messages → forward to backend (NO auto-reply) ───────────────────

async function handleIncoming(msg) {
    try {
        if (!msg || msg.fromMe) return;
        const mid = (msg.id && msg.id._serialized) || "";
        if (mid && (ignoredIds.has(mid) || processedIds.has(mid))) return;
        if (mid) {
            processedIds.add(mid);
            if (processedIds.size > 2000) processedIds.clear();
        }
        if (msg.from === "status@broadcast") return;
        if (String(msg.from || "").endsWith("@g.us")) return;

        // Update heartbeat — ada pesan masuk berarti koneksi masih hidup
        lastHeartbeat = Date.now();

        const hadMedia = Boolean(msg.hasMedia);
        const probableMime = (msg._data && msg._data.mimetype) || (String(msg.type || "").toLowerCase() === "image" ? "image/jpeg" : "");
        const media = await buildMediaPayload(msg);
        const text = String(msg.body || "").trim();
        if (!text && !media && !hadMedia) return;

        // Get the JID first
        const fromJid = String(msg.from || "");
        if (!fromJid) return;

        let realNumber = normalizeNumber(fromJid);
        let displayName = realNumber;

        try {
            const contact = await msg.getContact();
            if (contact && contact.number) {
                realNumber = String(contact.number).replace(/\D/g, "");
            }
            displayName = String(
                (contact && contact.pushname) ||
                (contact && contact.name) ||
                (contact && contact.shortName) ||
                displayName
            ).trim() || displayName;
        } catch (_) {
            // fallback to normalized fromJid
        }

        // Use real phone number (e.g. 62812...) as user_id for DB
        const userId = realNumber || normalizeNumber(fromJid);

        const messageText = text || mediaFallbackText((media && media.mimetype) || probableMime);

        console.log(`[CC] recv from=${fromJid} number=${userId} name=${displayName} text="${messageText.slice(0, 80)}" media=${media ? media.mimetype : "-"}`);

        // Forward to dashboard backend — do not wait for or send a reply
        axios
            .post(
                INTERNAL_URL,
                {
                    user_id: userId,
                    username: displayName,
                    message: messageText,
                    message_id: mid || null,
                    media,
                },
                {
                    headers: {
                        "Content-Type": "application/json",
                        "X-ASKA-CC-TOKEN": INTERNAL_TOKEN,
                    },
                    maxBodyLength: Infinity,
                    maxContentLength: Infinity,
                    timeout: 15000,
                }
            )
            .catch((err) => {
                console.error(
                    "[CC] Backend error:",
                    (err && err.response && err.response.data) || (err && err.message) || err
                );
            });
    } catch (err) {
        console.error("[CC] handleIncoming error:", (err && err.message) || err);
    }
}

client.on("message", (msg) => handleIncoming(msg));
client.on("message_create", (msg) => handleIncoming(msg));

// ── Express HTTP API for outbound messages ───────────────────────────────────

const app = express();
app.use(express.json({ limit: "2mb" }));

// Auth middleware
function authCheck(req, res, next) {
    const token =
        req.headers["x-aska-cc-token"] || req.query.token || "";
    if (token !== INTERNAL_TOKEN) {
        return res.status(403).json({ error: "Unauthorized" });
    }
    next();
}

function boundedInt(value, fallback, min, max) {
    const parsed = parseInt(value, 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
}

async function getChatIdentity(chat) {
    const chatId = (chat && chat.id && chat.id._serialized) || "";
    let number = normalizeNumber(chatId);
    let displayName = (chat && chat.name) || number || chatId;

    try {
        const contact = await chat.getContact();
        if (contact && contact.number) {
            number = String(contact.number).replace(/\D/g, "");
        }
        displayName = String(
            (contact && contact.pushname) ||
            (contact && contact.name) ||
            (contact && contact.shortName) ||
            displayName
        ).trim() || displayName;
    } catch (_) {
        // Some historical chats may not expose a contact object.
    }

    return { number, displayName, chatId };
}

async function serializeHistoryMessage(msg, identity) {
    if (!msg) return null;
    if (msg.from === "status@broadcast" || msg.to === "status@broadcast") return null;

    const hadMedia = Boolean(msg.hasMedia);
    const probableMime = (msg._data && msg._data.mimetype) || (String(msg.type || "").toLowerCase() === "image" ? "image/jpeg" : "");
    const text = String(msg.body || "").trim();
    const media = await buildMediaPayload(msg);
    if (!text && !media && !hadMedia) return null;

    const timestamp = Number(msg.timestamp || 0);
    const createdAt = timestamp > 0 ? new Date(timestamp * 1000).toISOString() : new Date().toISOString();
    const messageId = (msg.id && msg.id._serialized) || "";

    return {
        user_id: identity.number,
        username: identity.displayName,
        direction: msg.fromMe ? "outbound" : "inbound",
        message: text || mediaFallbackText((media && media.mimetype) || probableMime),
        message_id: messageId || null,
        created_at: createdAt,
        media,
    };
}

function mergeImportStats(total, batchResult) {
    total.saved += Number((batchResult && batchResult.saved) || 0);
    total.duplicates += Number((batchResult && batchResult.duplicates) || 0);
    total.skipped += Number((batchResult && batchResult.skipped) || 0);
    total.conversations += Number((batchResult && batchResult.conversations) || 0);
}

async function postImportBatch(messages) {
    if (!messages.length) return {};
    const response = await axios.post(
        IMPORT_URL,
        { messages },
        {
            headers: {
                "Content-Type": "application/json",
                "X-ASKA-CC-TOKEN": INTERNAL_TOKEN,
            },
            maxBodyLength: Infinity,
            maxContentLength: Infinity,
            timeout: 60000,
        }
    );
    return response.data || {};
}

app.get("/health", (_req, res) => {
    res.json({ ok: true, state: "running" });
});

app.post("/sync-history", authCheck, async (req, res) => {
    if (!clientReady) {
        return res.status(409).json({ error: "WhatsApp bridge belum ready." });
    }

    const chatLimit = boundedInt(req.body && (req.body.chatLimit || req.body.chat_limit), 25, 1, 200);
    const limitPerChat = boundedInt(req.body && (req.body.limitPerChat || req.body.limit_per_chat), 50, 1, 500);
    const stats = {
        ok: true,
        chatLimit,
        limitPerChat,
        chats: 0,
        fetched: 0,
        sent: 0,
        saved: 0,
        duplicates: 0,
        skipped: 0,
        conversations: 0,
        failedChats: 0,
    };

    try {
        const chats = await client.getChats();
        const directChats = chats
            .filter((chat) => {
                const jid = (chat && chat.id && chat.id._serialized) || "";
                if (!jid || jid === "status@broadcast") return false;
                if (chat.isGroup || jid.endsWith("@g.us")) return false;
                return Boolean(normalizeNumber(jid));
            })
            .sort((a, b) => {
                const aTime = Number((a && a.timestamp) || (a && a.lastMessage && a.lastMessage.timestamp) || 0);
                const bTime = Number((b && b.timestamp) || (b && b.lastMessage && b.lastMessage.timestamp) || 0);
                return bTime - aTime;
            })
            .slice(0, chatLimit);

        stats.chats = directChats.length;
        let batch = [];

        for (const chat of directChats) {
            try {
                const identity = await getChatIdentity(chat);
                if (!identity.number) {
                    stats.skipped += 1;
                    continue;
                }

                // Delay antar chat agar WhatsApp Web internal store siap
                await new Promise((r) => setTimeout(r, 300));

                let messages = [];
                try {
                    messages = await chat.fetchMessages({ limit: limitPerChat });
                } catch (fetchErr) {
                    // Retry sekali setelah delay jika store belum siap (waitForChatLoading)
                    const isStoreErr = (fetchErr && fetchErr.message || "").includes("waitForChatLoading") ||
                        (fetchErr && fetchErr.message || "").includes("Cannot read properties of undefined");
                    if (isStoreErr) {
                        await new Promise((r) => setTimeout(r, 1500));
                        try {
                            messages = await chat.fetchMessages({ limit: limitPerChat });
                        } catch (_retryErr) {
                            stats.failedChats += 1;
                            console.warn("[CC] sync chat skip (store not ready):", identity.number);
                            continue;
                        }
                    } else {
                        throw fetchErr;
                    }
                }

                messages.sort((a, b) => Number(a.timestamp || 0) - Number(b.timestamp || 0));

                for (const msg of messages) {
                    const item = await serializeHistoryMessage(msg, identity);
                    if (!item) {
                        stats.skipped += 1;
                        continue;
                    }
                    batch.push(item);
                    stats.fetched += 1;

                    if (batch.length >= 100) {
                        const result = await postImportBatch(batch);
                        stats.sent += batch.length;
                        mergeImportStats(stats, result);
                        batch = [];
                    }
                }
            } catch (err) {
                stats.failedChats += 1;
                console.error("[CC] sync chat error:", (err && err.message) || err);
            }
        }

        if (batch.length) {
            const result = await postImportBatch(batch);
            stats.sent += batch.length;
            mergeImportStats(stats, result);
        }

        console.log(
            `[CC] sync-history chats=${stats.chats} fetched=${stats.fetched} saved=${stats.saved} duplicates=${stats.duplicates} skipped=${stats.skipped}`
        );
        res.json(stats);
    } catch (err) {
        console.error("[CC] sync-history error:", (err && err.message) || err);
        res.status(500).json({ error: (err && err.message) || "Sync history failed" });
    }
});

app.post("/send", authCheck, async (req, res) => {
    const { to, message, media } = req.body || {};
    const hasMessage = String(message || "").trim().length > 0;
    const hasMedia = Boolean(media && media.data && media.mimetype);
    if (!to || (!hasMessage && !hasMedia)) {
        return res.status(400).json({ error: "Missing 'to' or 'message/media'" });
    }
    try {
        let jid;
        const sanitized = String(to).replace(/\D/g, "");
        if (String(to).includes("@")) {
            // Already a JID
            jid = String(to);
        } else {
            // Force @c.us for phone numbers
            jid = `${sanitized}@c.us`;
        }

        let sent;
        if (hasMedia) {
            const mimetype = String(media.mimetype || "").trim();
            const filename = String(media.filename || "attachment").trim() || "attachment";
            const data = String(media.data || "").replace(/\s+/g, "");
            if (!isAllowedMediaMime(mimetype)) {
                return res.status(400).json({ error: "Unsupported media type" });
            }
            const size = estimateBase64Bytes(data);
            const limit = outboundMediaSizeLimit(mimetype);
            if (Number.isFinite(limit) && limit > 0 && size > limit) {
                return res.status(413).json({ error: `Media too large. Max ${limit} bytes.` });
            }

            const messageMedia = new MessageMedia(mimetype, data, filename);
            const isImage = mimetype.toLowerCase().startsWith("image/");
            const options = {};
            if (hasMessage) options.caption = String(message).trim();
            if (!isImage) options.sendMediaAsDocument = true;
            sent = await client.sendMessage(jid, messageMedia, options);
        } else {
            sent = await client.sendMessage(jid, String(message));
        }
        const sentId = (sent && sent.id && sent.id._serialized) || "";
        if (sentId) ignoredIds.add(sentId);
        console.log(`[CC] sent to=${jid} len=${String(message || "").length} media=${hasMedia ? media.mimetype : "-"}`);
        res.json({ ok: true, messageId: sentId });
    } catch (err) {
        console.error("[CC] sendMessage error:", (err && err.message) || err);
        res.status(500).json({ error: (err && err.message) || "Send failed" });
    }
});

// ── boot ─────────────────────────────────────────────────────────────────────

app.listen(HTTP_PORT, () => {
    console.log(`[CC] HTTP API listening on port ${HTTP_PORT}`);
});

writeStatus({
    state: "starting",
    qrText: "",
    message: "Call Center bridge sedang inisialisasi...",
    sessionPath: SESSION_PATH,
    clientId: CLIENT_ID,
    internalUrl: INTERNAL_URL,
    httpPort: HTTP_PORT,
});

client.initialize().catch((err) => {
    writeStatus({ state: "error", qrText: "", message: (err && err.message) || String(err) });
    console.error("[CC] Init error:", (err && err.message) || err);
    process.exit(1);
});
