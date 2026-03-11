"""
IRIS — Flask Backend (server.py)
Features:
  - Driver login with session management
  - Per-driver availability toggle
  - SQLite persistence (crashes + ambulances + drivers)
  - Haversine dispatch engine (Kerala coordinates)
  - Server-Sent Events (SSE) for real-time push
  - Crash snapshot from video
  - Accessible on local network (phone support)
"""

# pyre-ignore[21]
from flask import (Flask, jsonify, request, send_file,
                   Response, send_from_directory, session)
import sqlite3, os, json, math, time, queue, threading, hashlib
from datetime import datetime
# pyre-ignore[21]
import cv2

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR     = os.path.dirname(__file__)
DB_PATH      = os.path.join(BASE_DIR, "crashguard.db")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
VIDEO_PATH   = os.path.join(os.path.dirname(BASE_DIR), "test1.mp4")
SECRET_KEY   = "crashguard-secret-2024"

os.makedirs(SNAPSHOT_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
app.secret_key = SECRET_KEY

# ── SSE subscribers ─────────────────────────────────────────────────────────────
_subscribers = {}  # unit_id -> [queues]
_sub_lock = threading.Lock()

# ── Operator SSE subscribers ─────────────────────────────────────────────────────
_op_subscribers = []
_op_lock = threading.Lock()

def push_operator(event_type: str, data: dict):
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _op_lock:
        for q in list(_op_subscribers):
            try: q.put_nowait(msg)
            except queue.Full: pass

def push_event(unit_id: str, event_type: str, data: dict):
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _sub_lock:
        for q in _subscribers.get(unit_id, []):
            try: q.put_nowait(msg)
            except queue.Full: pass

def push_all(event_type: str, data: dict):
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _sub_lock:
        for queues in _subscribers.values():
            for q in queues:
                try: q.put_nowait(msg)
                except queue.Full: pass
    # Also push to operator subscribers
    push_operator(event_type, data)

# ── DB helpers ──────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── Haversine ───────────────────────────────────────────────────────────────────
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# ── Dispatch ────────────────────────────────────────────────────────────────────
def dispatch(incident_id, crash_lat, crash_lon, exclude_unit=None):
    conn = get_db()
    
    # Find available ambulances and drivers
    query = """
        SELECT a.ambulance_id, a.unit_name, a.lat, a.long, d.driver_id
        FROM AMBULANCE a
        JOIN DRIVER d ON d.ambulance_id = a.ambulance_id
        WHERE a.availability = 'available' AND d.on_duty = 1
    """
    if exclude_unit:
        query += f" AND a.ambulance_id != {exclude_unit}"
        
    available_units = conn.execute(query).fetchall()

    if not available_units:
        conn.execute("UPDATE INCIDENT SET status='no_unit_available' WHERE incident_id=?", (incident_id,))
        conn.commit()
        conn.close()
        return None

    # Find nearest by Haversine distance
    nearest = min(available_units, key=lambda u: haversine(crash_lat, crash_lon, u["lat"], u["long"]))
    dist_km = haversine(crash_lat, crash_lon, nearest["lat"], nearest["long"])

    # Create dispatch record
    conn.execute(
        "INSERT INTO DISPATCH (incident_id, ambulance_id, driver_id, status) VALUES (?, ?, ?, 'dispatched')",
        (incident_id, nearest["ambulance_id"], nearest["driver_id"])
    )
    
    # Update incident status
    conn.execute(
        "UPDATE INCIDENT SET status='waiting_for_driver' WHERE incident_id=?",
        (incident_id,)
    )
    conn.commit()
    conn.close()

    push_event(str(nearest["ambulance_id"]), "mission_assigned", {
        "crash_id":     incident_id,
        "unit_id":      nearest["unit_name"],
        "crash_lat":    crash_lat,
        "crash_lon":    crash_lon,
        "distance_km":  float(f"{dist_km:.2f}"),
        "snapshot_url": f"/api/snapshot/{incident_id}",
        "address":      get_address(crash_lat, crash_lon),
        "timestamp":    datetime.now().isoformat()
    })
    return nearest["unit_name"]

def get_address(lat, lon):
    """Return a human-readable dummy address based on Kerala coordinates."""
    # Simple lookup for demo — in production use reverse geocoding API
    landmarks = [
        (10.5276, 76.2144, "Thrissur Medical College, Thrissur, Kerala"),
        (10.5167, 76.2167, "Sakthan Thampuran Nagar, Thrissur, Kerala"),
        (9.9312,  76.2673, "General Hospital, Ernakulam, Kerala"),
        (10.0159, 76.3419, "Aluva Junction, Ernakulam, Kerala"),
        (10.4515, 76.1875, "Irinjalakuda Town, Thrissur, Kerala"),
        (10.8505, 76.2711, "Palakkad Town, Kerala"),
        (10.3528, 76.5120, "Chalakudy, Thrissur, Kerala"),
        (9.5916,  76.5222, "Kottayam Medical College, Kerala"),
    ]
    nearest = min(landmarks, key=lambda l: haversine(lat, lon, l[0], l[1]))
    dist = haversine(lat, lon, nearest[0], nearest[1])
    if dist < 5:
        return f"Near {nearest[2]}"
    return f"NH-544, Kerala ({lat:.4f}, {lon:.4f})"

# ── Snapshot ────────────────────────────────────────────────────────────────────
def capture_snapshot(crash_id):
    snap_path = os.path.join(SNAPSHOT_DIR, f"crash_{crash_id}.jpg")
    try:
        cap = cv2.VideoCapture(VIDEO_PATH)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, total // 3))
        ret, frame = cap.read()
        cap.release()
        if ret:
            h, w = frame.shape[:2]
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 70), (20, 20, 160), -1)
            cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
            cv2.putText(frame, "ACCIDENT DETECTED  |  IRIS",
                        (12, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255,255,255), 2)
            ts = datetime.now().strftime("%d %b %Y  %H:%M:%S")
            cv2.putText(frame, ts, (12, h - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1)
            cv2.imwrite(snap_path, frame)
            # Insert EVIDENCE record (snapshots)
            conn = get_db()
            conn.execute("INSERT INTO EVIDENCE (incident_id, snapshot_path) VALUES (?, ?)", (crash_id, snap_path))
            conn.commit()
            conn.close()
            return snap_path
    except Exception as e:
        print(f"[snapshot] {e}")
    # Fallback
    # pyre-ignore[21]
    import numpy as np
    img = np.zeros((480, 640, 3), dtype="uint8")
    img[:] = (30, 30, 160)
    cv2.putText(img, "ACCIDENT DETECTED", (80, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255,255,255), 3)
    cv2.imwrite(snap_path, img)
    return snap_path

# ── Auth middleware ─────────────────────────────────────────────────────────────
def get_current_driver() -> dict:
    driver_id = session.get("driver_id")
    if not driver_id:
        return {}
    conn = get_db()
    driver = conn.execute("""
        SELECT d.driver_id, d.on_duty, u.name, u.phone, a.ambulance_id, a.unit_name 
        FROM DRIVER d
        JOIN USER u ON u.user_id = d.user_id
        JOIN AMBULANCE a ON a.ambulance_id = d.ambulance_id
        WHERE d.driver_id=?
    """, (driver_id,)).fetchone()
    conn.close()
    return dict(driver) if driver else {}

# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

# ── Auth ────────────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    password = data.get("password", "")
    conn = get_db()
    
    # Query USER and linked DRIVER
    user = conn.execute("""
        SELECT u.*, d.driver_id, d.on_duty, a.ambulance_id, a.unit_name
        FROM USER u
        JOIN DRIVER d ON d.user_id = u.user_id
        JOIN AMBULANCE a ON a.ambulance_id = d.ambulance_id
        WHERE u.phone=? AND u.password=?
    """, (phone, hash_pw(password))).fetchone()
    
    conn.close()
    
    if not user:
        return jsonify({"ok": False, "error": "Invalid phone number or password"}), 401
        
    session["driver_id"] = user["driver_id"]
    return jsonify({
        "ok": True,
        "driver": {
            "id":        user["driver_id"],
            "name":      user["name"],
            "phone":     user["phone"],
            "unit_id":   user["unit_name"],
            "amb_id":    user["ambulance_id"],
            "is_on_duty": user["on_duty"]
        }
    })

@app.route("/api/logout", methods=["POST"])
def logout():
    driver = get_current_driver()
    if driver:
        conn = get_db()
        conn.execute("UPDATE DRIVER SET on_duty=0 WHERE driver_id=?", (driver["driver_id"],))
        conn.execute("UPDATE AMBULANCE SET availability='unavailable' WHERE ambulance_id=?", (driver["ambulance_id"],))
        conn.commit()
        conn.close()
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    password = data.get("password", "")
    
    if not name or not phone or not password:
        return jsonify({"ok": False, "error": "Name, phone, and password required"}), 400
        
    conn = get_db()
    
    # Check if user already exists
    existing = conn.execute("SELECT user_id FROM USER WHERE phone=?", (phone,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"ok": False, "error": "Phone number already registered"}), 400
        
    try:
        # 1. Create User
        cur = conn.execute(
            "INSERT INTO USER (name, role, phone, password) VALUES (?, ?, ?, ?)",
            (name, 'driver', phone, hash_pw(password))
        )
        user_id = cur.lastrowid
        
        # 2. Assign to an Ambulance logic:
        # For this prototype, we'll try to find an ambulance without a driver, 
        # or just create a new standby one if all are taken.
        amb_id = None
        unassigned_amb = conn.execute("""
            SELECT ambulance_id FROM AMBULANCE 
            WHERE ambulance_id NOT IN (SELECT ambulance_id FROM DRIVER)
            LIMIT 1
        """).fetchone()
        
        if unassigned_amb:
             amb_id = unassigned_amb['ambulance_id']
        else:
             # Create new generic ambulance unit
             unit_count = conn.execute("SELECT COUNT(*) FROM AMBULANCE").fetchone()[0]
             new_unit_name = f"Unit-{str(unit_count + 1).zfill(2)}"
             # Random nearby coordinates for Thrissur generic default
             cur_amb = conn.execute(
                 "INSERT INTO AMBULANCE (unit_name, availability, lat, long) VALUES (?, ?, ?, ?)",
                 (new_unit_name, "available", 10.5276, 76.2144)
             )
             amb_id = cur_amb.lastrowid
             
        # 3. Create Driver Record
        cur_drv = conn.execute(
            "INSERT INTO DRIVER (user_id, ambulance_id, on_duty) VALUES (?, ?, ?)",
            (user_id, amb_id, 0)
        )
        driver_id = cur_drv.lastrowid
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"ok": False, "error": str(e)}), 500
        
    # Query back the full user context to match login payload exactly
    user = conn.execute("""
        SELECT u.*, d.driver_id, d.on_duty, a.ambulance_id, a.unit_name
        FROM USER u
        JOIN DRIVER d ON d.user_id = u.user_id
        JOIN AMBULANCE a ON a.ambulance_id = d.ambulance_id
        WHERE d.driver_id=?
    """, (driver_id,)).fetchone()
    
    conn.close()
    
    session["driver_id"] = user["driver_id"]
    return jsonify({
        "ok": True,
        "driver": {
            "id":        user["driver_id"],
            "name":      user["name"],
            "phone":     user["phone"],
            "unit_id":   user["unit_name"],
            "amb_id":    user["ambulance_id"],
            "is_on_duty": user["on_duty"]
        }
    })

@app.route("/api/me")
def me():
    driver = get_current_driver()
    if not driver:
        return jsonify({"ok": False}), 401
    return jsonify({
        "ok": True,
        "driver": {
            "id":        driver["driver_id"],
            "name":      driver["name"],
            "phone":     driver["phone"],
            "unit_id":   driver["unit_name"],
            "amb_id":    driver["ambulance_id"],
            "is_on_duty": driver["on_duty"]
        }
    })

# ── Availability toggle ─────────────────────────────────────────────────────────
@app.route("/api/availability", methods=["POST"])
def set_availability():
    driver = get_current_driver()
    if not driver:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    data = request.json or {}
    on_duty = 1 if data.get("on_duty") else 0
    avail_str = 'available' if on_duty else 'unavailable'
    
    conn = get_db()
    conn.execute("UPDATE DRIVER SET on_duty=? WHERE driver_id=?", (on_duty, driver["driver_id"]))
    conn.execute("UPDATE AMBULANCE SET availability=? WHERE ambulance_id=?", (avail_str, driver["ambulance_id"]))
    conn.commit()
    
    # Check if there's a pending unassigned incident or an override targeting an off-duty driver
    dispatched_incident = None
    if on_duty:
        dispatched_incident = conn.execute("""
            SELECT i.incident_id, i.lat, i.long 
            FROM INCIDENT i
            LEFT JOIN DISPATCH dp ON dp.incident_id = i.incident_id AND dp.status = 'dispatched'
            LEFT JOIN DRIVER target_d ON target_d.driver_id = dp.driver_id
            WHERE i.status='no_unit_available' 
               OR (i.status='waiting_for_driver' AND target_d.on_duty=0)
            ORDER BY i.timestamp ASC LIMIT 1
        """).fetchone()
        
    conn.close()
    
    push_all("availability_update", {
        "unit_id": driver["unit_name"],
        "driver":  driver["name"],
        "on_duty": on_duty
    })
    
    # If a valid incident was waiting or being overridden, cancel the old and auto-assign
    if dispatched_incident and on_duty:
        inc_id = dispatched_incident["incident_id"]
        # Cancel any active dispatch traces (if we stole an override)
        conn2 = get_db()
        conn2.execute("UPDATE DISPATCH SET status='cancelled' WHERE incident_id=? AND status='dispatched'", (inc_id,))
        # Temporarily revert incident status so dispatch() correctly processes it
        conn2.execute("UPDATE INCIDENT SET status='new' WHERE incident_id=?", (inc_id,))
        conn2.commit()
        conn2.close()
        
        # Notify operator dashboard to close its popup just in case
        push_operator("dispatch_cancelled", {"incident_id": inc_id})
        
        # Finally re-route it using distance calculation
        dispatch(inc_id, dispatched_incident["lat"], dispatched_incident["long"])
        
    return jsonify({"ok": True, "on_duty": on_duty})

# ── Location update ─────────────────────────────────────────────────────────────
@app.route("/api/location", methods=["POST"])
def update_location():
    driver = get_current_driver()
    if not driver:
        return jsonify({"ok": False, "error": "Not logged in"}), 401
    data = request.json or {}
    lat = data.get("lat")
    lon = data.get("lon")
    
    if lat is None or lon is None:
        return jsonify({"ok": False, "error": "Missing coordinates"}), 400
        
    conn = get_db()
    conn.execute("UPDATE AMBULANCE SET lat=?, long=? WHERE ambulance_id=?", (lat, lon, driver["ambulance_id"]))
    conn.commit()
    conn.close()
    
    # Push to operators so they see real-time movement
    push_operator("location_update", {
        "unit_id": driver["unit_name"],
        "lat": lat,
        "lon": lon
    })
    return jsonify({"ok": True})

# ── SSE ─────────────────────────────────────────────────────────────────────────
@app.route("/events")
def sse_stream():
    driver = get_current_driver()
    if not driver:
        return jsonify({"error": "Not logged in"}), 401
    unit_id = str(driver["ambulance_id"])
    q = queue.Queue(maxsize=30)
    with _sub_lock:
        _subscribers.setdefault(unit_id, []).append(q)

    def generate():
        try:
            yield f"event: connected\ndata: {json.dumps({'unit': unit_id, 'driver': driver['name']})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            cleanup()

    def cleanup():
        with _sub_lock:
            try: _subscribers[unit_id].remove(q)
            except: pass

    resp = Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return resp

# ── Mission ─────────────────────────────────────────────────────────────────────
@app.route("/api/mission")
def get_mission():
    driver = get_current_driver()
    if not driver:
        return jsonify({"status": "not_logged_in"}), 401
    conn = get_db()
    
    row = conn.execute(
        """SELECT i.*, disp.status as disp_status, a.lat as amb_lat, a.long as amb_lon
           FROM INCIDENT i
           JOIN DISPATCH disp ON disp.incident_id = i.incident_id
           LEFT JOIN AMBULANCE a ON disp.ambulance_id = a.ambulance_id
           WHERE disp.driver_id=? AND disp.status IN ('dispatched','en_route')
           ORDER BY i.incident_id DESC LIMIT 1""",
        (driver["driver_id"],)
    ).fetchone()
    
    conn.close()
    if not row:
        return jsonify({"status": "standby"})
        
    # Map old UI statuses
    ui_status = 'waiting_for_driver' if row["disp_status"] == 'dispatched' else 'en_route'
        
    return jsonify({
        "status":       ui_status,
        "crash_id":     row["incident_id"],
        "crash_lat":    row["lat"],
        "crash_lon":    row["long"],
        "timestamp":    row["timestamp"],
        "snapshot_url": f"/api/snapshot/{row['incident_id']}",
        "address":      get_address(row["lat"], row["long"]),
        "distance_km":  float(f"{haversine(row['lat'], row['long'], row['amb_lat'] or 0, row['amb_lon'] or 0):.2f}")
    })

@app.route("/api/mission/accept", methods=["POST"])
def accept_mission():
    driver = get_current_driver()
    if not driver:
        return jsonify({"ok": False}), 401
    data = request.json or {}
    crash_id = data.get("crash_id")
    
    conn = get_db()
    conn.execute("UPDATE DISPATCH SET status='en_route' WHERE incident_id=? AND driver_id=?", (crash_id, driver["driver_id"]))
    conn.execute("UPDATE INCIDENT SET status='en_route' WHERE incident_id=?", (crash_id,))
    conn.execute("UPDATE AMBULANCE SET availability='unavailable' WHERE ambulance_id=?", (driver["ambulance_id"],))
    conn.commit()
    conn.close()
    
    push_all("status_update", {"crash_id": crash_id, "status": "en_route", "unit": driver["unit_name"]})
    return jsonify({"ok": True, "status": "en_route"})

@app.route("/api/mission/decline", methods=["POST"])
def decline_mission():
    driver = get_current_driver()
    if not driver:
        return jsonify({"ok": False}), 401
    data = request.json or {}
    crash_id = data.get("crash_id")
    
    conn = get_db()
    row = conn.execute("SELECT * FROM INCIDENT WHERE incident_id=?", (crash_id,)).fetchone()
    
    # Mark old dispatch as declined
    conn.execute("UPDATE DISPATCH SET status='declined' WHERE incident_id=? AND driver_id=?", (crash_id, driver["driver_id"]))
    
    # Reset incident
    conn.execute("UPDATE INCIDENT SET status='new' WHERE incident_id=?", (crash_id,))
    conn.commit()
    conn.close()
    
    reassigned_to = None
    if row:
        reassigned_to = dispatch(crash_id, row["lat"], row["long"], exclude_unit=driver["ambulance_id"])
    return jsonify({"ok": True, "status": "standby", "reassigned_to": reassigned_to})

@app.route("/api/mission/arrived", methods=["POST"])
def arrived():
    driver = get_current_driver()
    if not driver:
        return jsonify({"ok": False}), 401
    data = request.json or {}
    crash_id = data.get("crash_id")
    closure_reason = data.get("closure_reason")
    
    conn = get_db()
    conn.execute("UPDATE DISPATCH SET status='arrived' WHERE incident_id=?", (crash_id,))
    if closure_reason:
        conn.execute("UPDATE INCIDENT SET status='resolved', closure_reason=? WHERE incident_id=?", (closure_reason, crash_id))
    else:
        conn.execute("UPDATE INCIDENT SET status='resolved' WHERE incident_id=?", (crash_id,))
    conn.execute("UPDATE AMBULANCE SET availability='available' WHERE ambulance_id=?", (driver["ambulance_id"],))
    conn.commit()
    conn.close()
    
    push_all("status_update", {"crash_id": crash_id, "status": "resolved", "closure_reason": closure_reason})
    return jsonify({"ok": True, "status": "resolved"})

# ── Snapshot ────────────────────────────────────────────────────────────────────
@app.route("/api/snapshot/<int:crash_id>")
def get_snapshot(crash_id):
    conn = get_db()
    row = conn.execute("SELECT snapshot_path FROM EVIDENCE WHERE incident_id=?", (crash_id,)).fetchone()
    conn.close()

    if row and row["snapshot_path"] and os.path.exists(row["snapshot_path"]):
        return send_file(row["snapshot_path"], mimetype="image/jpeg")

    # Fallback to local snapshots directory
    snap_path = os.path.join(SNAPSHOT_DIR, f"crash_{crash_id}.jpg")
    if not os.path.exists(snap_path):
        return jsonify({"error": "not found"}), 404
    return send_file(snap_path, mimetype="image/jpeg")

# ── Incident Submission (AI Script) ─────────────────────────────────────────────
@app.route("/api/new_alert", methods=["POST"])
def new_alert():
    data = request.json or {}
    ts = data.get("time") or datetime.now().isoformat()
    image_path = data.get("image_path", "")

    # For testing, we generate dummy coordinates around Thrissur if not provided
    lat = data.get("lat", 10.5276)
    lon = data.get("lon", 76.2144)
    camera_id = data.get("camera_id")

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO INCIDENT (camera_id, timestamp, lat, long, status) VALUES (?,?,?,?,?)",
        (camera_id, ts, float(lat), float(lon), "new")
    )
    crash_id = cur.lastrowid
    
    if image_path:
        conn.execute("INSERT INTO EVIDENCE (incident_id, snapshot_path) VALUES (?, ?)", (crash_id, image_path))
        
    conn.commit()
    conn.close()
    
    assigned = dispatch(crash_id, float(lat), float(lon))
    return jsonify({
        "ok": True, "crash_id": crash_id, "assigned_to": assigned,
        "lat": lat, "lon": lon
    })

# ── Alert Fetching (App & Dashboard) ────────────────────────────────────────────
@app.route("/api/latest_alert")
def latest_alert():
    conn = get_db()
    row = conn.execute("SELECT * FROM INCIDENT ORDER BY timestamp DESC LIMIT 1").fetchone()
    
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "No alerts"})
        
    # Get snapshot
    ev = conn.execute("SELECT snapshot_path FROM EVIDENCE WHERE incident_id=?", (row["incident_id"],)).fetchone()
    conn.close()
    
    data = dict(row)
    data["image_path"] = ev["snapshot_path"] if ev else ""
    return jsonify({"ok": True, "data": data})

# ── Data endpoints ──────────────────────────────────────────────────────────────
@app.route("/api/crashes")
def list_crashes():
    conn = get_db()
    rows = conn.execute("SELECT * FROM INCIDENT ORDER BY incident_id DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/ambulances")
def list_ambulances():
    conn = get_db()
    rows = conn.execute("""
        SELECT a.ambulance_id as id, a.lat as latitude, a.long as longitude, a.availability as is_available,
               u.name as driver_name, u.phone, d.on_duty as is_on_duty 
        FROM AMBULANCE a 
        LEFT JOIN DRIVER d ON d.ambulance_id = a.ambulance_id
        LEFT JOIN USER u ON u.user_id = d.user_id
    """).fetchall()
    conn.close()
    
    # Map back to old UI format slightly to avoid full UI rewrite
    res = []
    for r in rows:
        d = dict(r)
        d['is_available'] = 1 if d['is_available'] == 'available' else 0
        d['is_on_duty'] = 1 if d['is_on_duty'] else 0
        res.append(d)
    return jsonify(res)

# ══════════════════════════════════════════════════════════════════════════════
# OPERATOR ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/operator")
def operator_dashboard():
    return send_from_directory(BASE_DIR, "operator_dashboard.html")

@app.route("/operator/events")
def operator_sse_stream():
    q = queue.Queue(maxsize=50)
    with _op_lock:
        _op_subscribers.append(q)

    def generate():
        try:
            yield f"event: connected\ndata: {json.dumps({'role': 'operator'})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=25)
                    yield msg
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            with _op_lock:
                try: _op_subscribers.remove(q)
                except: pass

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/operator/stats")
def operator_stats():
    conn = get_db()
    total   = conn.execute("SELECT COUNT(*) FROM INCIDENT").fetchone()[0]
    active  = conn.execute("SELECT COUNT(*) FROM INCIDENT WHERE status IN ('new','waiting_for_driver')").fetchone()[0]
    enroute = conn.execute("SELECT COUNT(*) FROM INCIDENT WHERE status='en_route'").fetchone()[0]
    nunit   = conn.execute("SELECT COUNT(*) FROM INCIDENT WHERE status='no_unit_available'").fetchone()[0]
    today   = conn.execute("SELECT COUNT(*) FROM INCIDENT WHERE status='resolved' AND date(timestamp)=date('now')").fetchone()[0]
    avail   = conn.execute("SELECT COUNT(*) FROM AMBULANCE WHERE availability='available'").fetchone()[0]
    on_duty = conn.execute("SELECT COUNT(*) FROM DRIVER WHERE on_duty=1").fetchone()[0]
    conn.close()
    return jsonify({
        "total": total, "active": active, "en_route": enroute,
        "no_unit": nunit, "resolved_today": today,
        "available_units": avail, "on_duty_drivers": on_duty
    })

@app.route("/api/operator/incidents")
def operator_incidents():
    conn = get_db()
    rows = conn.execute("""
        SELECT i.incident_id, i.lat, i.long, i.status, i.closure_reason, i.timestamp, i.camera_id,
               d.status as disp_status, d.dispatch_id,
               a.unit_name, a.ambulance_id,
               u.name as driver_name, u.phone,
               e.snapshot_path
        FROM INCIDENT i
        LEFT JOIN DISPATCH d ON d.incident_id = i.incident_id
            AND d.status NOT IN ('declined')
        LEFT JOIN AMBULANCE a ON a.ambulance_id = d.ambulance_id
        LEFT JOIN DRIVER dr ON dr.driver_id = d.driver_id
        LEFT JOIN USER u ON u.user_id = dr.user_id
        LEFT JOIN EVIDENCE e ON e.incident_id = i.incident_id
        ORDER BY i.incident_id DESC LIMIT 50
    """).fetchall()
    conn.close()
    result = []
    seen = set()
    for r in rows:
        iid = r["incident_id"]
        if iid in seen:
            continue
        seen.add(iid)
        d = dict(r)
        d["address"] = get_address(r["lat"], r["long"])
        result.append(d)
    return jsonify(result)

@app.route("/api/operator/drivers")
def operator_drivers():
    conn = get_db()
    rows = conn.execute("""
        SELECT d.driver_id, d.on_duty, d.ambulance_id,
               u.name, u.phone, u.email,
               a.unit_name, a.availability, a.lat, a.long
        FROM DRIVER d
        JOIN USER u ON u.user_id = d.user_id
        JOIN AMBULANCE a ON a.ambulance_id = d.ambulance_id
        ORDER BY a.unit_name
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/operator/override", methods=["POST"])
def operator_override():
    """Force-assign a specific ambulance to a failed/pending incident."""
    data = request.json or {}
    incident_id  = data.get("incident_id")
    ambulance_id = data.get("ambulance_id")
    if not incident_id or not ambulance_id:
        return jsonify({"ok": False, "error": "Missing incident_id or ambulance_id"}), 400

    conn = get_db()
    inc = conn.execute("SELECT * FROM INCIDENT WHERE incident_id=?", (incident_id,)).fetchone()
    amb = conn.execute(
        "SELECT a.*, d.driver_id FROM AMBULANCE a JOIN DRIVER d ON d.ambulance_id=a.ambulance_id WHERE a.ambulance_id=?",
        (ambulance_id,)).fetchone()

    if not inc or not amb:
        conn.close()
        return jsonify({"ok": False, "error": "Incident or ambulance not found"}), 404

    # Cancel any pending dispatches for this incident
    conn.execute("UPDATE DISPATCH SET status='cancelled' WHERE incident_id=? AND status IN ('dispatched','en_route')", (incident_id,))

    # Create new override dispatch
    conn.execute(
        "INSERT INTO DISPATCH (incident_id, ambulance_id, driver_id, status) VALUES (?,?,?,'dispatched')",
        (incident_id, ambulance_id, amb["driver_id"])
    )
    conn.execute("UPDATE INCIDENT SET status='waiting_for_driver' WHERE incident_id=?", (incident_id,))
    conn.execute("UPDATE AMBULANCE SET availability='unavailable' WHERE ambulance_id=?", (ambulance_id,))
    conn.commit()
    conn.close()

    push_operator("override_dispatch", {
        "incident_id": incident_id,
        "unit": amb["unit_name"],
        "operator_action": True
    })
    push_event(str(ambulance_id), "mission_assigned", {
        "crash_id":    incident_id,
        "unit_id":     amb["unit_name"],
        "crash_lat":   inc["lat"],
        "crash_lon":   inc["long"],
        "distance_km": float(f"{haversine(inc['lat'], inc['long'], amb['lat'], amb['long']):.2f}"),
        "snapshot_url": f"/api/snapshot/{incident_id}",
        "address":     get_address(inc["lat"], inc["long"]),
        "timestamp":   datetime.now().isoformat(),
        "operator_override": True
    })
    return jsonify({"ok": True, "unit": amb["unit_name"]})

@app.route("/api/operator/cancel_dispatch", methods=["POST"])
def operator_cancel_dispatch():
    data = request.json or {}
    incident_id = data.get("incident_id")
    conn = get_db()
    
    # 1. Clear any active dispatches
    conn.execute("UPDATE DISPATCH SET status='cancelled' WHERE incident_id=? AND status IN ('dispatched','en_route')", (incident_id,))
    
    # 2. Re-evaluate unit availability. If no units are available, this goes back to no_unit_available
    avail_count = conn.execute("SELECT COUNT(*) FROM AMBULANCE a JOIN DRIVER d ON d.ambulance_id = a.ambulance_id WHERE a.availability='available' AND d.on_duty=1").fetchone()[0]
    
    if avail_count == 0:
        conn.execute("UPDATE INCIDENT SET status='no_unit_available' WHERE incident_id=?", (incident_id,))
    else:
        conn.execute("UPDATE INCIDENT SET status='new' WHERE incident_id=?", (incident_id,))
        
    conn.commit()
    conn.close()
    push_operator("dispatch_cancelled", {"incident_id": incident_id})
    return jsonify({"ok": True})

@app.route("/api/operator/update_status", methods=["POST"])
def operator_update_status():
    data = request.json or {}
    incident_id = data.get("incident_id")
    status      = data.get("status")
    allowed = ['new','waiting_for_driver','en_route','resolved','no_unit_available']
    if status not in allowed:
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    conn = get_db()
    conn.execute("UPDATE INCIDENT SET status=? WHERE incident_id=?", (status, incident_id))
    if status == 'resolved':
        # Free up the ambulance
        disp = conn.execute("SELECT ambulance_id FROM DISPATCH WHERE incident_id=? ORDER BY dispatch_id DESC LIMIT 1", (incident_id,)).fetchone()
        if disp:
            conn.execute("UPDATE AMBULANCE SET availability='available' WHERE ambulance_id=?", (disp["ambulance_id"],))
            conn.execute("UPDATE DISPATCH SET status='arrived' WHERE incident_id=? AND status IN ('dispatched','en_route')", (incident_id,))
    conn.commit()
    conn.close()
    push_all("status_update", {"crash_id": incident_id, "status": status})
    return jsonify({"ok": True})

# ── Main ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # pyre-ignore[21]
    from init_db import init
    init()
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print("\n" + "="*60)
    print("  IRIS")
    print(f"  Driver App:        http://localhost:5000")
    print(f"  Operator Dashboard: http://localhost:5000/operator")
    print(f"  Network:           http://{local_ip}:5000")
    print("="*60 + "\n")
    app.run(host="0.0.0.0", debug=False, threaded=True, port=5000)
