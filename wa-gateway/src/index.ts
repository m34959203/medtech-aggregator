import express from 'express';
import { Pool } from 'pg';
import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} from '@whiskeysockets/baileys';

// 405-фикс: если Baileys-версию не удалось получить (Hoster блочит
// raw.githubusercontent.com / таймаут) — берём заведомо рабочий fallback.
const WA_VERSION_FALLBACK: [number, number, number] = [2, 3000, 1037700952];
import * as QRCode from 'qrcode';
import pino from 'pino';
import { usePgAuthState } from './pg-auth-store';

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });
const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || '3200');
const API_SECRET = process.env.WA_API_SECRET || 'change-me';
const DATABASE_URL = process.env.DATABASE_URL || '';
const INBOUND_WEBHOOK_URL = process.env.WA_INBOUND_WEBHOOK_URL || '';
const INBOUND_WEBHOOK_SECRET = process.env.WA_INBOUND_WEBHOOK_SECRET || '';

// Anti-ban knobs
const HUMANIZE = (process.env.WA_HUMANIZE ?? 'true') !== 'false';
const HUMANIZE_MIN_MS = parseInt(process.env.WA_HUMANIZE_MIN_MS || '3000');
const HUMANIZE_MAX_MS = parseInt(process.env.WA_HUMANIZE_MAX_MS || '15000');
const DAILY_LIMIT = parseInt(process.env.WA_DAILY_LIMIT || '100');
const REQUIRE_CLIENT_INITIATED =
  (process.env.WA_REQUIRE_CLIENT_INITIATED ?? 'true') !== 'false';
const ALLOW_SELF_CHAT = process.env.WA_ALLOW_SELF_CHAT === 'true';

const pool = new Pool({ connectionString: DATABASE_URL });

let socket: ReturnType<typeof makeWASocket> | null = null;
let qrDataUrl: string | null = null;
let connectionStatus: 'disconnected' | 'connecting' | 'qr_ready' | 'connected' = 'disconnected';
let phoneNumber: string | null = null;
let reconnectTimer: NodeJS.Timeout | null = null;
let reconnectAttempts = 0;
const MAX_RECONNECT = 5;

// Самодостаточная схема: туннель сам заводит свои таблицы (не зависит от
// миграций основного приложения). Идемпотентно.
async function ensureSchema(): Promise<void> {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS whatsapp_sessions (
      id          TEXT PRIMARY KEY,
      data        JSONB NOT NULL,
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS whatsapp_messages (
      id            BIGSERIAL PRIMARY KEY,
      direction     TEXT NOT NULL,
      chat_id       TEXT NOT NULL,
      message_type  TEXT NOT NULL DEFAULT 'text',
      content       TEXT,
      wa_message_id TEXT,
      status        TEXT,
      error         TEXT,
      lead_id       TEXT,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_wa_msg_chat ON whatsapp_messages (chat_id);
    CREATE INDEX IF NOT EXISTS idx_wa_msg_dir_created ON whatsapp_messages (direction, created_at);
  `);
}

// Auth middleware
function authMiddleware(req: express.Request, res: express.Response, next: express.NextFunction) {
  const secret = req.headers['x-api-secret'] as string;
  if (secret !== API_SECRET) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }
  next();
}

app.use('/api', authMiddleware);

// Health (no auth)
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', wa: connectionStatus });
});

// Status
app.get('/api/status', (_req, res) => {
  res.json({
    status: connectionStatus,
    phoneNumber,
    qrCode: qrDataUrl,
  });
});

// Connect — fire-and-forget: never block the caller on Baileys handshake.
// UI polls /api/status for qr_ready/connected transitions.
app.post('/api/connect', (_req, res) => {
  if (connectionStatus === 'connected') {
    res.json({ status: 'already_connected', phoneNumber });
    return;
  }
  if (connectionStatus === 'connecting' || connectionStatus === 'qr_ready') {
    res.json({ status: connectionStatus, qrCode: qrDataUrl });
    return;
  }

  connectionStatus = 'connecting';
  startConnection().catch((err) => {
    logger.error({ err }, 'startConnection failed');
    connectionStatus = 'disconnected';
  });
  res.json({ status: 'connecting', qrCode: null });
});

// Disconnect
app.post('/api/disconnect', async (_req, res) => {
  await disconnect();
  res.json({ status: 'disconnected' });
});

// Logout (clear session)
app.post('/api/logout', async (_req, res) => {
  try {
    if (socket) {
      await socket.logout();
      socket.end(undefined);
      socket = null;
    }
  } catch { /* ignore */ }
  connectionStatus = 'disconnected';
  phoneNumber = null;
  qrDataUrl = null;
  await pool.query('DELETE FROM whatsapp_sessions');
  res.json({ status: 'logged_out' });
});

// ---- Outbound pacing: serial queue with humanize + gates ----
type SendJob = {
  chatId: string;
  message: string;
  leadId?: string | null;
  bypassGates?: boolean;
  resolve: (v: { success: true; messageId: string } | { success: false; error: string; status: number }) => void;
};
const sendQueue: SendJob[] = [];
let queueRunning = false;

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function countOutgoing24h(): Promise<number> {
  const { rows } = await pool.query<{ c: string }>(
    `SELECT COUNT(*)::text AS c FROM whatsapp_messages
     WHERE direction = 'outgoing' AND status = 'sent'
       AND created_at > NOW() - INTERVAL '24 hours'`
  );
  return parseInt(rows[0]?.c || '0');
}

async function hasIncomingFrom(chatId: string): Promise<boolean> {
  const { rows } = await pool.query(
    `SELECT 1 FROM whatsapp_messages
     WHERE direction = 'incoming' AND chat_id = $1 LIMIT 1`,
    [chatId]
  );
  return rows.length > 0;
}

async function processQueue() {
  if (queueRunning) return;
  queueRunning = true;
  try {
    while (sendQueue.length > 0) {
      const job = sendQueue.shift()!;
      await runSendJob(job);
    }
  } finally {
    queueRunning = false;
  }
}

async function runSendJob(job: SendJob) {
  const { chatId, message, leadId, bypassGates } = job;

  if (connectionStatus !== 'connected' || !socket) {
    job.resolve({ success: false, error: 'WhatsApp not connected', status: 400 });
    return;
  }

  if (!bypassGates && REQUIRE_CLIENT_INITIATED) {
    const ok = await hasIncomingFrom(chatId).catch(() => false);
    if (!ok) {
      job.resolve({
        success: false,
        error: 'client_not_initiated: send only to chats where client wrote first',
        status: 409,
      });
      return;
    }
  }

  if (!bypassGates && DAILY_LIMIT > 0) {
    const sent = await countOutgoing24h().catch(() => 0);
    if (sent >= DAILY_LIMIT) {
      job.resolve({
        success: false,
        error: `daily_limit_reached: ${sent}/${DAILY_LIMIT} in last 24h`,
        status: 429,
      });
      return;
    }
  }

  if (HUMANIZE) {
    try {
      const typingMs = Math.min(
        HUMANIZE_MAX_MS,
        Math.max(HUMANIZE_MIN_MS, message.length * 50 + Math.floor(Math.random() * 3000))
      );
      await socket.sendPresenceUpdate('composing', chatId);
      await sleep(typingMs);
      await socket.sendPresenceUpdate('paused', chatId);
    } catch (err) {
      logger.warn({ err }, 'presence update failed (ignored)');
    }
  }

  try {
    const msg = await socket.sendMessage(chatId, { text: message });
    const waMessageId = msg?.key.id || `sent_${Date.now()}`;
    await pool.query(
      `INSERT INTO whatsapp_messages (direction, chat_id, message_type, content, wa_message_id, status, lead_id)
       VALUES ('outgoing', $1, 'text', $2, $3, 'sent', $4)`,
      [chatId, message, waMessageId, leadId || null]
    );
    job.resolve({ success: true, messageId: waMessageId });
  } catch (err: any) {
    logger.error({ err, chatId }, 'Failed to send message');
    await pool.query(
      `INSERT INTO whatsapp_messages (direction, chat_id, message_type, content, status, error, lead_id)
       VALUES ('outgoing', $1, 'text', $2, 'failed', $3, $4)`,
      [chatId, message, err.message, leadId || null]
    ).catch(() => {});
    job.resolve({ success: false, error: 'Failed to send message', status: 500 });
  }
}

// Send text message
app.post('/api/send', async (req, res) => {
  const { phone, message, leadId, bypassGates } = req.body || {};
  if (!phone || !message) {
    res.status(400).json({ error: 'phone and message are required' });
    return;
  }
  const chatId = phone.includes('@') ? phone : `${phone.replace(/\D/g, '')}@s.whatsapp.net`;

  const result = await new Promise<
    { success: true; messageId: string } | { success: false; error: string; status: number }
  >((resolve) => {
    sendQueue.push({ chatId, message, leadId, bypassGates: !!bypassGates, resolve });
    processQueue();
  });

  if (!result.success) {
    res.status(result.status).json({ error: result.error });
    return;
  }
  res.json({ success: true, messageId: result.messageId });
});

// Outbound limit status
app.get('/api/limits', async (_req, res) => {
  const sent = await countOutgoing24h().catch(() => 0);
  res.json({
    dailyLimit: DAILY_LIMIT,
    sentLast24h: sent,
    remaining: Math.max(0, DAILY_LIMIT - sent),
    humanize: HUMANIZE,
    requireClientInitiated: REQUIRE_CLIENT_INITIATED,
    queueDepth: sendQueue.length,
  });
});

// Check if number exists on WhatsApp
app.post('/api/check-number', async (req, res) => {
  if (connectionStatus !== 'connected' || !socket) {
    res.status(400).json({ error: 'WhatsApp not connected' });
    return;
  }

  const { phone } = req.body;
  if (!phone) {
    res.status(400).json({ error: 'phone is required' });
    return;
  }

  try {
    const results = await socket.onWhatsApp(phone.replace(/\D/g, ''));
    const result = results?.[0];
    res.json({ exists: result?.exists || false, jid: result?.jid });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// Fire-and-forget webhook dispatch for inbound messages
async function forwardInboundToApp(payload: {
  phone: string;
  chatId: string;
  message: string;
  messageId: string;
  timestamp: number;
}): Promise<void> {
  if (!INBOUND_WEBHOOK_URL) return;
  try {
    const res = await fetch(INBOUND_WEBHOOK_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Webhook-Secret': INBOUND_WEBHOOK_SECRET,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      logger.warn({ status: res.status, url: INBOUND_WEBHOOK_URL }, 'Inbound webhook returned non-2xx');
    }
  } catch (err) {
    logger.error({ err }, 'Failed to POST inbound webhook');
  }
}

// Connection logic
async function startConnection() {
  connectionStatus = 'connecting';
  reconnectAttempts = 0;

  const { state, saveCreds } = await usePgAuthState(pool);
  let version: [number, number, number] = WA_VERSION_FALLBACK;
  try {
    const fetched = await Promise.race([
      fetchLatestBaileysVersion(),
      new Promise<never>((_, rej) =>
        setTimeout(() => rej(new Error('version fetch timeout')), 5000),
      ),
    ]);
    version = fetched.version as [number, number, number];
  } catch (err) {
    logger.warn({ err: (err as Error).message }, 'Using fallback WA version');
  }

  const baileysLogger = logger.child({ module: 'baileys' });
  baileysLogger.level = 'warn';

  socket = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, baileysLogger),
    },
    printQRInTerminal: false,
    logger: baileysLogger,
    generateHighQualityLinkPreview: false,
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  socket.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      qrDataUrl = await QRCode.toDataURL(qr);
      connectionStatus = 'qr_ready';
      logger.info('QR code generated');
    }

    if (connection === 'open') {
      connectionStatus = 'connected';
      reconnectAttempts = 0;
      qrDataUrl = null;
      phoneNumber = socket?.user?.id?.split(':')[0] || null;
      logger.info({ phoneNumber }, 'WhatsApp connected');
    }

    if (connection === 'close') {
      connectionStatus = 'disconnected';
      phoneNumber = null;
      qrDataUrl = null;

      const statusCode = (lastDisconnect?.error as any)?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      if (statusCode === DisconnectReason.loggedOut) {
        logger.error({ statusCode, reason: 'loggedOut' }, '⚠️ Session logged out — possible ban or manual unlink');
      } else if (statusCode === 401 || statusCode === 403) {
        logger.error({ statusCode }, '⚠️ Auth rejected — possible ban');
      } else if (statusCode) {
        logger.warn({ statusCode, err: lastDisconnect?.error?.message }, 'Connection closed');
      }

      if (shouldReconnect && reconnectAttempts < MAX_RECONNECT) {
        reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        logger.info({ attempt: reconnectAttempts, delay }, 'Reconnecting...');
        reconnectTimer = setTimeout(() => startConnection(), delay);
      } else {
        logger.warn({ statusCode }, 'Not reconnecting');
        if (statusCode === DisconnectReason.loggedOut) {
          await pool.query('DELETE FROM whatsapp_sessions');
        }
      }
    }
  });

  socket.ev.on('creds.update', saveCreds);

  // Handle incoming messages: log to DB and forward to app via webhook
  socket.ev.on('messages.upsert', async ({ messages: msgs, type }) => {
    if (type !== 'notify') return;
    for (const msg of msgs) {
      if (!msg.message) continue;
      const chatId = msg.key.remoteJid;
      if (!chatId) continue;

      if (msg.key.fromMe) {
        const ownJid = socket?.user?.id?.replace(/:\d+/, '') || '';
        const isSelfChat = ALLOW_SELF_CHAT && chatId === ownJid;
        if (!isSelfChat) continue;
        const waId = msg.key.id;
        if (waId) {
          const { rows } = await pool.query(
            `SELECT 1 FROM whatsapp_messages WHERE wa_message_id = $1 AND direction = 'outgoing' LIMIT 1`,
            [waId]
          );
          if (rows.length > 0) continue;
        }
      }

      const text = msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        '[media]';

      const waMessageId = msg.key.id || `recv_${Date.now()}`;
      const phone = chatId.split('@')[0];
      const timestamp = typeof msg.messageTimestamp === 'number'
        ? msg.messageTimestamp
        : Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000);

      await pool.query(
        `INSERT INTO whatsapp_messages (direction, chat_id, message_type, content, wa_message_id, status)
         VALUES ('incoming', $1, 'text', $2, $3, 'received')`,
        [chatId, text, waMessageId]
      ).catch((err) => logger.error({ err }, 'Failed to log incoming message'));

      logger.info({ chatId, from: msg.pushName }, 'Incoming message');

      forwardInboundToApp({
        phone,
        chatId,
        message: text,
        messageId: waMessageId,
        timestamp,
      }).catch((err) => logger.error({ err }, 'Inbound webhook dispatch error'));
    }
  });
}

async function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (socket) {
    socket.end(undefined);
    socket = null;
  }
  connectionStatus = 'disconnected';
  phoneNumber = null;
  qrDataUrl = null;
}

// Start server and auto-connect if previous session exists
app.listen(PORT, '0.0.0.0', async () => {
  logger.info({ port: PORT }, 'medtech WA Gateway started');

  try {
    await ensureSchema();
  } catch (err) {
    logger.error({ err }, 'ensureSchema failed');
  }

  // Auto-connect if we have saved credentials (previous session)
  try {
    const { rows } = await pool.query("SELECT 1 FROM whatsapp_sessions WHERE id = 'creds' LIMIT 1");
    if (rows.length > 0) {
      logger.info('Found saved session, auto-connecting...');
      await startConnection();
    } else {
      logger.info('No saved session, waiting for /api/connect');
    }
  } catch (err) {
    logger.error({ err }, 'Auto-connect check failed');
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  logger.info('Shutting down...');
  await disconnect();
  await pool.end();
  process.exit(0);
});
