"""SQLite storage for price history. One row per (product, retailer, fetch)."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS price_snapshots (
    id INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL,
    retailer TEXT NOT NULL,
    price REAL NOT NULL,
    in_stock INTEGER NOT NULL DEFAULT 1,
    url TEXT,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_product ON price_snapshots(product_id, fetched_at DESC);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def record_price(conn, product_id: str, retailer: str, price: float,
                 in_stock: bool = True, url: str | None = None) -> None:
    conn.execute(
        "INSERT INTO price_snapshots (product_id, retailer, price, in_stock, url, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (product_id, retailer, price, int(in_stock), url,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def latest_price(conn, product_id: str):
    """Best (lowest) price among each retailer's most recent snapshot."""
    rows = conn.execute(
        """SELECT retailer, price, in_stock, url, MAX(fetched_at)
           FROM price_snapshots WHERE product_id = ? GROUP BY retailer""",
        (product_id,),
    ).fetchall()
    if not rows:
        return None
    in_stock_rows = [r for r in rows if r[2]] or rows
    best = min(in_stock_rows, key=lambda r: r[1])
    return {"retailer": best[0], "price": best[1], "in_stock": bool(best[2]), "url": best[3]}
