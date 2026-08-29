-- SQL Schema for Client-driven Queue System
-- Compatible with SQLite3 and PostgreSQL

-- Table: daily_counters
-- Holds the current sequence number for each date (YYYY-MM-DD)
CREATE TABLE IF NOT EXISTS daily_counters (
    date_key VARCHAR(10) PRIMARY KEY,
    current_number INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: tickets
-- Holds issued tickets with checksum verification and idempotency protection
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id VARCHAR(36) PRIMARY KEY,
    date_key VARCHAR(10) NOT NULL,
    ticket_number INTEGER NOT NULL,
    idempotency_key VARCHAR(64) UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'ISSUED', -- 'ISSUED', 'COMPLETED', 'EXPIRED'
    checksum VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Indexes for fast lookup & filtering
CREATE INDEX IF NOT EXISTS idx_tickets_date_key ON tickets(date_key);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_idempotency ON tickets(idempotency_key);
