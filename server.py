import http.server
import socketserver
import json
import sqlite3
import hashlib
import hmac
import uuid
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs

PORT = 8000
DB_FILE = "queue.db"
SECRET_KEY = b"QR_QUEUE_SECRET_KEY_CHANGE_IN_PRODUCTION_2026"
VIETNAM_TZ = timezone(timedelta(hours=7))

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=20.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_counters (
            date_key TEXT PRIMARY KEY,
            current_number INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cursor.execute("""
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
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_date_key ON tickets(date_key);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_idempotency ON tickets(idempotency_key);")
    conn.commit()
    conn.close()

def generate_checksum(ticket_id, date_key, ticket_number, created_at):
    raw = f"{ticket_id}:{date_key}:{ticket_number}:{created_at}"
    return hmac.new(SECRET_KEY, raw.encode('utf-8'), hashlib.sha256).hexdigest()

def get_current_date_key():
    now = datetime.now(VIETNAM_TZ)
    return now.strftime("%Y-%m-%d")

class QueueHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Idempotency-Key')
        self.end_headers()

    def send_json(self, status_code, data):
        try:
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
            pass

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == '/api/queue/status':
            query_params = parse_qs(parsed_url.query)
            ticket_num_param = query_params.get('ticket_number', [None])[0]
            
            date_key = get_current_date_key()
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT current_number FROM daily_counters WHERE date_key = ?", (date_key,))
            row = cursor.fetchone()
            current_num = row['current_number'] if row else 0
            
            cursor.execute("SELECT COUNT(*) as cnt FROM tickets WHERE date_key = ? AND status = 'ISSUED'", (date_key,))
            total_waiting = cursor.fetchone()['cnt']
            
            waiting_ahead = 0
            if ticket_num_param is not None:
                try:
                    t_num = int(ticket_num_param)
                    cursor.execute(
                        "SELECT COUNT(*) as cnt FROM tickets WHERE date_key = ? AND status = 'ISSUED' AND ticket_number < ?",
                        (date_key, t_num)
                    )
                    waiting_ahead = cursor.fetchone()['cnt']
                except ValueError:
                    waiting_ahead = 0

            now = datetime.now(VIETNAM_TZ)
            conn.close()
            self.send_json(200, {
                "success": True,
                "server_date": date_key,
                "server_time": now.isoformat(),
                "latest_issued_number": current_num,
                "total_waiting": total_waiting,
                "waiting_ahead": waiting_ahead
            })
            return

        # Serve static files (index.html by default)
        if self.path == '/' or self.path == '/index.html' or self.path.startswith('/?'):
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            body = json.loads(body_bytes.decode('utf-8'))
        except Exception:
            body = {}

        if self.path == '/api/queue/issue':
            idempotency_key = body.get('idempotency_key') or self.headers.get('X-Idempotency-Key')
            date_key = get_current_date_key()

            conn = get_db()
            try:
                # 1. Idempotency Check
                if idempotency_key:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM tickets WHERE idempotency_key = ?", (idempotency_key,))
                    existing = cursor.fetchone()
                    if existing:
                        conn.close()
                        self.send_json(200, {
                            "success": True,
                            "reissued": True,
                            "ticket": {
                                "ticket_id": existing['ticket_id'],
                                "date_key": existing['date_key'],
                                "ticket_number": existing['ticket_number'],
                                "status": existing['status'],
                                "checksum": existing['checksum'],
                                "created_at": existing['created_at']
                            }
                        })
                        return

                # 2. Atomic Transaction Execution
                conn.execute("BEGIN EXCLUSIVE TRANSACTION;")
                cursor = conn.cursor()

                # Get or initialize today's counter
                cursor.execute("SELECT current_number FROM daily_counters WHERE date_key = ?", (date_key,))
                row = cursor.fetchone()

                if row is None:
                    next_number = 1
                    cursor.execute(
                        "INSERT INTO daily_counters (date_key, current_number, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                        (date_key, next_number)
                    )
                    # 🧹 AUTO PRUNING: Automatically purge data older than 30 days to keep DB micro-sized
                    cursor.execute("DELETE FROM tickets WHERE date_key < date(?, '-30 days')", (date_key,))
                    cursor.execute("DELETE FROM daily_counters WHERE date_key < date(?, '-30 days')", (date_key,))
                else:
                    next_number = row['current_number'] + 1
                    cursor.execute(
                        "UPDATE daily_counters SET current_number = ?, updated_at = CURRENT_TIMESTAMP WHERE date_key = ?",
                        (next_number, date_key)
                    )

                # Create ticket record
                ticket_id = str(uuid.uuid4())
                created_at = datetime.now(VIETNAM_TZ).isoformat()
                checksum = generate_checksum(ticket_id, date_key, next_number, created_at)

                cursor.execute(
                    """INSERT INTO tickets 
                       (ticket_id, date_key, ticket_number, idempotency_key, status, checksum, created_at) 
                       VALUES (?, ?, ?, ?, 'ISSUED', ?, ?)""",
                    (ticket_id, date_key, next_number, idempotency_key, checksum, created_at)
                )

                # Calculate count of people waiting ahead
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM tickets WHERE date_key = ? AND status = 'ISSUED' AND ticket_number < ?",
                    (date_key, next_number)
                )
                waiting_ahead = cursor.fetchone()['cnt']

                conn.commit()
                conn.close()

                self.send_json(201, {
                    "success": True,
                    "reissued": False,
                    "ticket": {
                        "ticket_id": ticket_id,
                        "date_key": date_key,
                        "ticket_number": next_number,
                        "status": "ISSUED",
                        "checksum": checksum,
                        "created_at": created_at,
                        "waiting_ahead": waiting_ahead
                    }
                })

            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "error": str(e)})
            return

        elif self.path == '/api/queue/complete':
            ticket_id = body.get('ticket_id')
            if not ticket_id:
                self.send_json(400, {"success": False, "error": "Thiếu ticket_id"})
                return

            conn = get_db()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
                ticket = cursor.fetchone()
                if not ticket:
                    conn.close()
                    self.send_json(404, {"success": False, "error": "Không tìm thấy vé"})
                    return

                completed_at = datetime.now(VIETNAM_TZ).isoformat()
                cursor.execute(
                    "UPDATE tickets SET status = 'COMPLETED', completed_at = ? WHERE ticket_id = ?",
                    (completed_at, ticket_id)
                )
                conn.commit()
                conn.close()

                self.send_json(200, {
                    "success": True,
                    "ticket_id": ticket_id,
                    "status": "COMPLETED",
                    "completed_at": completed_at
                })
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "error": str(e)})
            return

        self.send_json(404, {"success": False, "error": "Endpoint không tồn tại"})

if __name__ == '__main__':
    init_db()
    print(f"[INFO] Server QR Boc So Thu Tu dang chay tai: http://localhost:{PORT}")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), QueueHTTPRequestHandler) as httpd:
        httpd.serve_forever()
