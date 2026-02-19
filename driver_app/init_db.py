"""
CrashGuard-S — Database Initializer
Run once: python init_db.py
Creates crashguard.db with schema and seeds Kerala ambulance units + driver accounts.
"""
import sqlite3, os, hashlib

DB_PATH = os.path.join(os.path.dirname(__file__), "crashguard.db")

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── crashes ────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS crashes (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp             TEXT    NOT NULL,
            latitude              REAL    NOT NULL,
            longitude             REAL    NOT NULL,
            snapshot_path         TEXT,
            status                TEXT    NOT NULL DEFAULT 'new',
            assigned_ambulance_id TEXT
        )
    """)

    # ── ambulances ─────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS ambulances (
            id           TEXT PRIMARY KEY,
            latitude     REAL NOT NULL,
            longitude    REAL NOT NULL,
            is_available INTEGER NOT NULL DEFAULT 1
        )
    """)

    # ── drivers ────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            badge        TEXT NOT NULL UNIQUE,
            password     TEXT NOT NULL,
            unit_id      TEXT NOT NULL,
            is_on_duty   INTEGER NOT NULL DEFAULT 0
        )
    """)

    # ── Seed: Kerala ambulance units (Thrissur / Ernakulam area) ───────────────
    units = [
        ("Unit-01", 10.5276, 76.2144, 1),   # Thrissur Medical College
        ("Unit-02", 10.5167, 76.2167, 1),   # Thrissur Town
        ("Unit-03", 9.9312,  76.2673, 1),   # Ernakulam General Hospital
        ("Unit-04", 10.0159, 76.3419, 1),   # Aluva
        ("Unit-05", 10.4515, 76.1875, 1),   # Irinjalakuda
    ]
    c.executemany(
        "INSERT OR IGNORE INTO ambulances (id, latitude, longitude, is_available) VALUES (?,?,?,?)",
        units
    )

    # ── Seed: Driver accounts ──────────────────────────────────────────────────
    drivers = [
        ("Arjun Nair",    "DRV-01", hash_pw("driver01"), "Unit-01"),
        ("Priya Menon",   "DRV-02", hash_pw("driver02"), "Unit-02"),
        ("Rahul Krishnan","DRV-03", hash_pw("driver03"), "Unit-03"),
        ("Anitha Suresh", "DRV-04", hash_pw("driver04"), "Unit-04"),
        ("Vishnu Kumar",  "DRV-05", hash_pw("driver05"), "Unit-05"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO drivers (name, badge, password, unit_id) VALUES (?,?,?,?)",
        drivers
    )

    conn.commit()
    conn.close()
    print(f"[init_db] Database ready: {DB_PATH}")
    print("\nDriver Login Credentials:")
    print("  Badge    | Password  | Unit")
    print("  ---------|-----------|--------")
    for d in drivers:
        print(f"  {d[1]:<8} | {d[3][4:]+'0':<9} | {d[3]}")

if __name__ == "__main__":
    init()
