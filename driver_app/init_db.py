"""
IRIS — Database Initializer
Run once: python init_db.py
Creates crashguard.db with the updated ER diagram schema and seeds dummy data.
"""
import sqlite3, os, hashlib
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "crashguard.db")

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init():
    # Remove old DB if it exists to start fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. ZONE
    c.execute("""
        CREATE TABLE ZONE (
            zone_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR NOT NULL,
            center_lat DECIMAL NOT NULL,
            center_lon DECIMAL NOT NULL
        )
    """)

    # 2. CAMERA
    c.execute("""
        CREATE TABLE CAMERA (
            camera_id INTEGER PRIMARY KEY AUTOINCREMENT,
            zone_id INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            rtsp_url VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'active',
            FOREIGN KEY(zone_id) REFERENCES ZONE(zone_id)
        )
    """)

    # 3. USER (Drivers)
    c.execute("""
        CREATE TABLE USER (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR NOT NULL,
            role VARCHAR NOT NULL DEFAULT 'driver',
            email VARCHAR,
            phone VARCHAR UNIQUE NOT NULL,    -- Changed from badge
            password VARCHAR NOT NULL
        )
    """)

    # 4. AMBULANCE
    c.execute("""
        CREATE TABLE AMBULANCE (
            ambulance_id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_name VARCHAR NOT NULL UNIQUE,
            availability VARCHAR NOT NULL DEFAULT 'available',
            lat DECIMAL NOT NULL,             -- Kept for Haversine dispatch
            long DECIMAL NOT NULL             -- Kept for Haversine dispatch
        )
    """)

    # 5. DRIVER
    c.execute("""
        CREATE TABLE DRIVER (
            driver_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ambulance_id INTEGER NOT NULL,
            on_duty BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES USER(user_id),
            FOREIGN KEY(ambulance_id) REFERENCES AMBULANCE(ambulance_id)
        )
    """)

    # 6. INCIDENT (Crashes)
    c.execute("""
        CREATE TABLE INCIDENT (
            incident_id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id INTEGER,
            lat DECIMAL NOT NULL,
            long DECIMAL NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'new',
            closure_reason VARCHAR,           -- Additional info on dispatch resolution
            timestamp TEXT NOT NULL,          -- Kept for UI history
            FOREIGN KEY(camera_id) REFERENCES CAMERA(camera_id)
        )
    """)

    # 7. EVIDENCE (Snapshots)
    c.execute("""
        CREATE TABLE EVIDENCE (
            evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            snapshot_path VARCHAR NOT NULL,
            FOREIGN KEY(incident_id) REFERENCES INCIDENT(incident_id)
        )
    """)

    # 8. DISPATCH
    c.execute("""
        CREATE TABLE DISPATCH (
            dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            ambulance_id INTEGER NOT NULL,
            driver_id INTEGER NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'dispatched',
            FOREIGN KEY(incident_id) REFERENCES INCIDENT(incident_id),
            FOREIGN KEY(ambulance_id) REFERENCES AMBULANCE(ambulance_id),
            FOREIGN KEY(driver_id) REFERENCES DRIVER(driver_id)
        )
    """)

    # --- SEED DATA ---
    ts = datetime.now().isoformat()

    # Seed Zones
    zones = [
        ("Thrissur North", 10.5300, 76.2100),
        ("Ernakulam Central", 9.9312, 76.2673)
    ]
    c.executemany("INSERT INTO ZONE (name, center_lat, center_lon) VALUES (?,?,?)", zones)

    # Seed Cameras
    cameras = [
        (1, "Cam-Thrissur-01", "rtsp://demo/1", "active"),
        (2, "Cam-Ernakulam-01", "rtsp://demo/2", "active")
    ]
    c.executemany("INSERT INTO CAMERA (zone_id, name, rtsp_url, status) VALUES (?,?,?,?)", cameras)

    # Seed Users (Drivers)
    users = [
        ("Arjun Nair", "driver", "arjun@cg.local", "9876543210", hash_pw("driver01")),
        ("Priya Menon", "driver", "priya@cg.local", "9876543211", hash_pw("driver02")),
        ("Rahul Krishnan", "driver", "rahul@cg.local", "9876543212", hash_pw("driver03")),
        ("Anitha Suresh", "driver", "anitha@cg.local", "9876543213", hash_pw("driver04")),
        ("Vishnu Kumar", "driver", "vishnu@cg.local", "9876543214", hash_pw("driver05")),
        ("alvin", "driver", "alvin@cg.local", "9876543215", hash_pw("alvin"))
    ]
    c.executemany("INSERT INTO USER (name, role, email, phone, password) VALUES (?,?,?,?,?)", users)

    # Seed Ambulances
    ambulances = [
        ("Unit-01", "unavailable", 10.5276, 76.2144),
        ("Unit-02", "unavailable", 10.5167, 76.2167),
        ("Unit-03", "unavailable", 9.9312, 76.2673),
        ("Unit-04", "unavailable", 10.0159, 76.3419),
        ("Unit-05", "unavailable", 10.4515, 76.1875),
        ("Unit-06", "unavailable", 10.4515, 76.1875)
    ]
    c.executemany("INSERT INTO AMBULANCE (unit_name, availability, lat, long) VALUES (?,?,?,?)", ambulances)

    # Map Drivers to Ambulances (1-to-1 for simplicity)
    drivers = [
        (1, 1, 0),  # user_id 1 -> ambulance_id 1
        (2, 2, 0),
        (3, 3, 0),
        (4, 4, 0),
        (5, 5, 0),
        (6, 6, 0)
    ]
    c.executemany("INSERT INTO DRIVER (user_id, ambulance_id, on_duty) VALUES (?,?,?)", drivers)

    conn.commit()
    conn.close()
    
    print(f"[init_db] Database ready: {DB_PATH}")
    print("\nDriver Login Credentials:")
    print("  Phone      | Password")
    print("  -----------|-----------")
    for i, u in enumerate(users, 1):
        print(f"  {u[3]:<10} | driver0{i}" if i <= 5 else f"  {u[3]:<10} | alvin")

if __name__ == "__main__":
    init()
