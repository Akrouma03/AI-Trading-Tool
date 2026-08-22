import json
import sqlite3
from config import DB_FILE


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            market_state TEXT,
            action TEXT,
            confidence REAL,
            reasoning TEXT,
            model TEXT,
            balance_at_decision REAL,
            expected_outcome TEXT
        )
    """)
    existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(decisions)")}
    if "balance_at_decision" not in existing_columns:
        cursor.execute("ALTER TABLE decisions ADD COLUMN balance_at_decision REAL")
    if "expected_outcome" not in existing_columns:
        cursor.execute("ALTER TABLE decisions ADD COLUMN expected_outcome TEXT")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            checked_at TEXT,
            price_at_decision REAL,
            price_now REAL,
            pct_change REAL,
            correct TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id INTEGER,
            order_id TEXT,
            symbol TEXT,
            side TEXT,
            qty TEXT,
            status TEXT,
            submitted_at TEXT,
            raw TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_decision(symbol, market_state, action, confidence, reasoning, model, balance_at_decision=None, expected_outcome=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO decisions (timestamp, symbol, market_state, action, confidence, reasoning, model, balance_at_decision, expected_outcome) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)",
        (symbol, market_state, action, confidence, reasoning, model, balance_at_decision, expected_outcome),
    )
    decision_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return decision_id


def log_order(decision_id, order):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (decision_id, order_id, symbol, side, qty, status, submitted_at, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            order.get("id") or order.get("orderId"),
            order.get("symbol"),
            order.get("side"),
            order.get("qty") or order.get("origQty") or order.get("executedQty"),
            "skipped" if order.get("skipped") else order.get("status"),
            order.get("submitted_at") or order.get("transactTime"),
            json.dumps(order),
        ),
    )
    conn.commit()
    conn.close()


def log_outcome(decision_id, price_at_decision, price_now, pct_change, correct):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO outcomes (decision_id, checked_at, price_at_decision, price_now, pct_change, correct) VALUES (?, datetime('now'), ?, ?, ?, ?)",
        (decision_id, price_at_decision, price_now, pct_change, correct),
    )
    conn.commit()
    conn.close()
