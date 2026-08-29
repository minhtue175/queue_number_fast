/**
 * Production-ready Node.js Express + Better-SQLite3 Server Reference
 * For deployment on Node.js runtimes (Vercel, Render, Railway, VPS)
 */

const express = require('express');
const Database = require('better-sqlite3');
const crypto = require('crypto');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 8000;
const SECRET_KEY = process.env.SECRET_KEY || 'QR_QUEUE_SECRET_KEY_CHANGE_IN_PRODUCTION_2026';

app.use(express.json());
app.use(express.static(__dirname));

const db = new Database('queue.db');
db.pragma('journal_mode = WAL');

// Initialize database schema
db.exec(`
    CREATE TABLE IF NOT EXISTS daily_counters (
        date_key TEXT PRIMARY KEY,
        current_number INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tickets (
        ticket_id TEXT PRIMARY KEY,
        date_key TEXT NOT NULL,
        ticket_number INTEGER NOT NULL,
        idempotency_key TEXT UNIQUE,
        status TEXT NOT NULL DEFAULT 'ISSUED',
        checksum TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_tickets_date_key ON tickets(date_key);
    CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
    CREATE INDEX IF NOT EXISTS idx_tickets_idempotency ON tickets(idempotency_key);
`);

function getVietnamDateKey() {
    const d = new Date();
    // Offset +7 hours for Vietnam Time
    const utc7 = new Date(d.getTime() + (7 * 60 + d.getTimezoneOffset()) * 60000);
    return utc7.toISOString().split('T')[0];
}

function generateChecksum(ticketId, dateKey, ticketNumber, createdAt) {
    const raw = `${ticketId}:${dateKey}:${ticketNumber}:${createdAt}`;
    return crypto.createHmac('sha256', SECRET_KEY).update(raw).digest('hex');
}

// Issue Ticket API (Atomic Transaction)
app.post('/api/queue/issue', (req, res) => {
    const idempotencyKey = req.body.idempotency_key || req.headers['x-idempotency-key'];
    const dateKey = getVietnamDateKey();

    // Idempotency check
    if (idempotencyKey) {
        const existing = db.prepare('SELECT * FROM tickets WHERE idempotency_key = ?').get(idempotencyKey);
        if (existing) {
            return res.json({
                success: true,
                reissued: true,
                ticket: existing
            });
        }
    }

    // Atomic transaction
    const issueTransaction = db.transaction(() => {
        const row = db.prepare('SELECT current_number FROM daily_counters WHERE date_key = ?').get(dateKey);
        let nextNumber = 1;

        if (!row) {
            db.prepare('INSERT INTO daily_counters (date_key, current_number, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)')
                .run(dateKey, 1);
            // 🧹 AUTO PRUNING: Purge tickets & daily_counters older than 30 days
            db.prepare("DELETE FROM tickets WHERE date_key < date(?, '-30 days')").run(dateKey);
            db.prepare("DELETE FROM daily_counters WHERE date_key < date(?, '-30 days')").run(dateKey);
        } else {
            nextNumber = row.current_number + 1;
            db.prepare('UPDATE daily_counters SET current_number = ?, updated_at = CURRENT_TIMESTAMP WHERE date_key = ?')
                .run(nextNumber, dateKey);
        }

        const ticketId = crypto.randomUUID();
        const createdAt = new Date().toISOString();
        const checksum = generateChecksum(ticketId, dateKey, nextNumber, createdAt);

        db.prepare(`
            INSERT INTO tickets 
            (ticket_id, date_key, ticket_number, idempotency_key, status, checksum, created_at)
            VALUES (?, ?, ?, ?, 'ISSUED', ?, ?)
        `).run(ticketId, dateKey, nextNumber, idempotencyKey || null, checksum, createdAt);

        return { ticket_id: ticketId, date_key: dateKey, ticket_number: nextNumber, status: 'ISSUED', checksum, created_at: createdAt };
    });

    try {
        const ticket = issueTransaction();
        res.status(201).json({ success: true, reissued: false, ticket });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// Complete Ticket API
app.post('/api/queue/complete', (req, res) => {
    const { ticket_id } = req.body;
    if (!ticket_id) {
        return res.status(400).json({ success: false, error: 'Thiếu ticket_id' });
    }

    const ticket = db.prepare('SELECT * FROM tickets WHERE ticket_id = ?').get(ticket_id);
    if (!ticket) {
        return res.status(404).json({ success: false, error: 'Không tìm thấy vé' });
    }

    if (ticket.status === 'COMPLETED') {
        return res.status(400).json({ success: false, error: 'Vé này đã hoàn tất dịch vụ rồi' });
    }

    // Strict FIFO check: Cannot complete if any previous ticket for today is still ISSUED
    const prevTicket = db.prepare(
        "SELECT ticket_number FROM tickets WHERE date_key = ? AND status = 'ISSUED' AND ticket_number < ? ORDER BY ticket_number ASC LIMIT 1"
    ).get(ticket.date_key, ticket.ticket_number);

    if (prevTicket) {
        const prevNum = String(prevTicket.ticket_number).padStart(3, '0');
        return res.status(400).json({
            success: false,
            error: `Chưa thể hoàn tất! Số thứ tự #${prevNum} trước bạn chưa hoàn thành dịch vụ.`
        });
    }

    const completedAt = new Date().toISOString();
    db.prepare("UPDATE tickets SET status = 'COMPLETED', completed_at = ? WHERE ticket_id = ?")
        .run(completedAt, ticket_id);

    res.json({ success: true, ticket_id, status: 'COMPLETED', completed_at: completedAt });
});

// Status API
app.get('/api/queue/status', (req, res) => {
    const dateKey = getVietnamDateKey();
    const ticketNumber = req.query.ticket_number ? parseInt(req.query.ticket_number, 10) : null;
    const row = db.prepare('SELECT current_number FROM daily_counters WHERE date_key = ?').get(dateKey);
    const totalRow = db.prepare("SELECT COUNT(*) as cnt FROM tickets WHERE date_key = ? AND status = 'ISSUED'").get(dateKey);

    let waitingAhead = 0;
    if (ticketNumber !== null && !isNaN(ticketNumber)) {
        const aheadRow = db.prepare("SELECT COUNT(*) as cnt FROM tickets WHERE date_key = ? AND status = 'ISSUED' AND ticket_number < ?")
            .get(dateKey, ticketNumber);
        waitingAhead = aheadRow ? aheadRow.cnt : 0;
    }

    res.json({
        success: true,
        server_date: dateKey,
        server_time: new Date().toISOString(),
        latest_issued_number: row ? row.current_number : 0,
        total_waiting: totalRow ? totalRow.cnt : 0,
        waiting_ahead: waitingAhead
    });
});

app.listen(PORT, () => {
    console.log(`🚀 Node.js Express QR Server listening on http://localhost:${PORT}`);
});
