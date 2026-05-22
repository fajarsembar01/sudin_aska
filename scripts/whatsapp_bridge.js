#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const axios = require("axios");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

function loadDotEnvFile(filePath) {
  try {
    if (!fs.existsSync(filePath)) {
      return;
    }
    const raw = fs.readFileSync(filePath, "utf8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }
      const eqIdx = trimmed.indexOf("=");
      if (eqIdx <= 0) {
        continue;
      }
      const key = trimmed.slice(0, eqIdx).trim();
      const value = trimmed.slice(eqIdx + 1).trim();
      if (key && !(key in process.env)) {
        process.env[key] = value;
      }
    }
  } catch (err) {
    console.warn("[WA] Gagal membaca .env:", (err && err.message) || err);
  }
}

loadDotEnvFile(path.resolve(process.cwd(), ".env"));

const INTERNAL_URL =
  (process.env.ASKA_WHATSAPP_INTERNAL_URL || "http://127.0.0.1:5001/api/whatsapp/inbound").trim();
const INTERNAL_TOKEN = (process.env.ASKA_WHATSAPP_INTERNAL_TOKEN || "").trim();
const SESSION_PATH = path.resolve(process.env.ASKA_WHATSAPP_SESSION_PATH || ".wa_session");
const CLIENT_ID = (process.env.ASKA_WHATSAPP_CLIENT_ID || "aska-main").trim();
const STATUS_PATH = path.resolve(
  process.env.ASKA_WHATSAPP_STATUS_PATH || "runtime/whatsapp_bridge_status.json"
);
const REQUEST_TIMEOUT_MS = Math.max(
  5000,
  Number.parseInt(process.env.ASKA_WHATSAPP_TIMEOUT_MS || "45000", 10) || 45000
);

const UNSUPPORTED_TYPE_REPLY = "Saat ini ASKA WhatsApp baru support pesan teks dulu ya 🙏";
const TECHNICAL_REPLY = "ASKA lagi gangguan teknis sebentar. Coba kirim ulang beberapa saat lagi ya.";
const DEBUG_PREFIX = "[WA][DEBUG]";
const ignoredMessageIds = new Set();
const processedMessageIds = new Set();

if (!INTERNAL_TOKEN) {
  console.error("[WA] ASKA_WHATSAPP_INTERNAL_TOKEN belum diset. Worker dihentikan.");
  process.exit(1);
}

function writeStatus(statusPatch) {
  try {
    const dir = path.dirname(STATUS_PATH);
    fs.mkdirSync(dir, { recursive: true });
    let base = {};
    if (fs.existsSync(STATUS_PATH)) {
      try {
        base = JSON.parse(fs.readFileSync(STATUS_PATH, "utf8")) || {};
      } catch (err) {
        base = {};
      }
    }
    const payload = {
      ...base,
      ...statusPatch,
      updatedAt: new Date().toISOString(),
    };
    fs.writeFileSync(STATUS_PATH, JSON.stringify(payload, null, 2), "utf8");
  } catch (err) {
    console.error("[WA] Gagal menulis status file:", (err && err.message) || err);
  }
}

function normalizeNumberFromJid(jid) {
  const raw = String(jid || "");
  const base = raw.split("@")[0] || "";
  const digits = base.replace(/\D/g, "");
  return digits || "";
}

function splitLongReply(text, maxChunk = 3200) {
  const clean = String(text || "").trim();
  if (!clean) {
    return [];
  }
  if (clean.length <= maxChunk) {
    return [clean];
  }
  const chunks = [];
  let current = clean;
  while (current.length > maxChunk) {
    let cutAt = current.lastIndexOf("\n\n", maxChunk);
    if (cutAt < 0) {
      cutAt = current.lastIndexOf("\n", maxChunk);
    }
    if (cutAt < 0) {
      cutAt = current.lastIndexOf(" ", maxChunk);
    }
    if (cutAt <= 0) {
      cutAt = maxChunk;
    }
    chunks.push(current.slice(0, cutAt).trim());
    current = current.slice(cutAt).trim();
  }
  if (current) {
    chunks.push(current);
  }
  return chunks.filter(Boolean);
}

async function postToAska(payload) {
  const response = await axios.post(INTERNAL_URL, payload, {
    headers: {
      "Content-Type": "application/json",
      "X-ASKA-WHATSAPP-TOKEN": INTERNAL_TOKEN,
    },
    timeout: REQUEST_TIMEOUT_MS,
  });
  return response.data || {};
}

const client = new Client({
  authStrategy: new LocalAuth({
    clientId: CLIENT_ID,
    dataPath: SESSION_PATH,
  }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", (qrText) => {
  writeStatus({
    state: "qr",
    qrText: String(qrText || ""),
    message: "Scan QR dari WhatsApp Linked Devices.",
  });
  console.log("\n[WA] Scan QR berikut di WhatsApp Linked Devices:\n");
  qrcode.generate(qrText, { small: true });
  console.log("\n[WA] QR siap dipindai.");
});

client.on("authenticated", () => {
  writeStatus({
    state: "authenticated",
    qrText: "",
    message: "Authenticated. Sesi tersimpan.",
    sessionPath: SESSION_PATH,
  });
  console.log("[WA] Authenticated. Sesi tersimpan di:", SESSION_PATH);
});

client.on("ready", () => {
  writeStatus({
    state: "ready",
    qrText: "",
    message: "Bridge siap menerima chat pribadi.",
  });
  console.log("[WA] Bridge siap menerima chat pribadi.");
});

client.on("auth_failure", (message) => {
  writeStatus({
    state: "auth_failure",
    qrText: "",
    message: String(message || "Auth failure"),
  });
  console.error("[WA] Auth failure:", message);
});

client.on("disconnected", (reason) => {
  writeStatus({
    state: "disconnected",
    qrText: "",
    message: String(reason || "Disconnected"),
  });
  console.warn("[WA] Disconnected:", reason);
  setTimeout(() => {
    client.initialize().catch((err) => {
      console.error("[WA] Gagal reinitialize client:", (err && err.message) || err);
    });
  }, 3000);
});

async function handleIncomingMessage(msg, sourceEvent = "message") {
  try {
    if (!msg) {
      return;
    }
    const incomingId = (msg.id && msg.id._serialized) || "";
    if (incomingId && ignoredMessageIds.has(incomingId)) {
      ignoredMessageIds.delete(incomingId);
      return;
    }
    if (incomingId && processedMessageIds.has(incomingId)) {
      return;
    }
    if (incomingId) {
      processedMessageIds.add(incomingId);
      if (processedMessageIds.size > 2000) {
        processedMessageIds.clear();
      }
    }

    if (msg.from === "status@broadcast") {
      return;
    }

    // Skip our own outgoing messages to prevent infinite reply loops
    if (msg.fromMe) {
      return;
    }

    if (String(msg.from || "").endsWith("@g.us")) {
      return;
    }

    if (msg.type !== "chat") {
      await msg.reply(UNSUPPORTED_TYPE_REPLY);
      return;
    }

    const text = String(msg.body || "").trim();
    if (!text) {
      return;
    }
    console.log(
      `${DEBUG_PREFIX} recv event=${sourceEvent} from=${msg.from} fromMe=${Boolean(
        msg.fromMe
      )} type=${msg.type} text="${text.slice(0, 80)}"`
    );

    const number = normalizeNumberFromJid(msg.from);
    if (!number) {
      return;
    }

    let displayName = number;
    try {
      const contact = await msg.getContact();
      displayName =
        String(
          (contact && contact.pushname) ||
            (contact && contact.name) ||
            (contact && contact.shortName) ||
            number
        ).trim() || number;
    } catch (err) {
      displayName = number;
    }

    const payload = {
      user_id: number,
      username: displayName,
      message: text,
      message_type: "text",
      message_id: (msg.id && msg.id._serialized) || null,
    };

    const data = await postToAska(payload);
    const replyText = String(data.response || "").trim();
    if (!replyText) {
      console.log(`${DEBUG_PREFIX} no-reply from backend for from=${msg.from}`);
      return;
    }

    const chunks = splitLongReply(replyText);
    for (const chunk of chunks) {
      const sent = await client.sendMessage(msg.from, chunk);
      const sentId = (sent && sent.id && sent.id._serialized) || "";
      if (sentId) {
        ignoredMessageIds.add(sentId);
      }
      console.log(`${DEBUG_PREFIX} sent to=${msg.from} len=${chunk.length}`);
    }
  } catch (err) {
    console.error(
      "[WA] Error menangani pesan:",
      (err && err.response && err.response.data) || (err && err.message) || err
    );
    try {
      await msg.reply(TECHNICAL_REPLY);
    } catch (sendErr) {
      console.error("[WA] Gagal kirim fallback reply:", (sendErr && sendErr.message) || sendErr);
    }
  }
}

client.on("message", async (msg) => {
  await handleIncomingMessage(msg, "message");
});

client.on("message_create", async (msg) => {
  await handleIncomingMessage(msg, "message_create");
});

writeStatus({
  state: "starting",
  qrText: "",
  message: "Bridge sedang inisialisasi...",
  sessionPath: SESSION_PATH,
  clientId: CLIENT_ID,
  internalUrl: INTERNAL_URL,
});
client.initialize().catch((err) => {
  writeStatus({
    state: "error",
    qrText: "",
    message: (err && err.message) || String(err),
  });
  console.error("[WA] Gagal initialize client:", (err && err.message) || err);
  process.exit(1);
});
