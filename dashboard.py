# pyre-ignore[21]
import streamlit as st
import sqlite3
# pyre-ignore[21]
import pandas as pd
import os
import time

try:
    # pyre-ignore[21]
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

# Connect to the SQLite DB in the driver_app folder
DB_PATH = os.path.join(os.path.dirname(__file__), "driver_app", "crashguard.db")

st.set_page_config(page_title="IRIS Command Center", layout="wide")

# Auto-refresh every 2 seconds
if st_autorefresh:
    st_autorefresh(interval=2000, limit=None, key="data_refresh")

st.title("🚨 IRIS Command Center")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

try:
    conn = get_db_connection()
    # Query the latest incident with evidence snapshot
    query = """
    SELECT i.incident_id, i.lat, i.long, i.status, i.timestamp, e.snapshot_path 
    FROM INCIDENT i
    LEFT JOIN EVIDENCE e ON i.incident_id = e.incident_id
    ORDER BY i.incident_id DESC LIMIT 1
    """
    latest = conn.execute(query).fetchone()
    
    if latest:
        st.subheader("Latest Accident Alert")
        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown(f"**Incident ID:** {latest['incident_id']}")
            st.markdown(f"**Time:** {latest['timestamp']}")
            st.markdown(f"**Location (Lat, Lon):** {latest['lat']}, {latest['long']}")
            st.markdown(f"**Status:** {latest['status']}")
            
            # Map fallback (dropping red pin essentially if new)
            df = pd.DataFrame({'lat': [latest['lat']], 'lon': [latest['long']]})
            st.map(df, zoom=14, color="#ff0000")

        with col2:
            snap_path = latest['snapshot_path']
            if snap_path and os.path.exists(snap_path):
                st.image(snap_path, caption="Snapshot from AI Sensor", use_container_width=True)
            else:
                st.warning("No snapshot available.")
    else:
        st.info("No accidents detected yet.")

    st.markdown("---")
    st.subheader("Active Incidents & Ambulances")
    
    colA, colB = st.columns(2)
    with colA:
        st.markdown("**All Recent Incidents**")
        incs = conn.execute("SELECT incident_id, timestamp, status, lat, long FROM INCIDENT ORDER BY incident_id DESC LIMIT 5").fetchall()
        if incs:
            st.dataframe(pd.DataFrame([dict(r) for r in incs]), use_container_width=True)
            
    with colB:
        st.markdown("**Ambulance Units Status**")
        ambs = conn.execute("SELECT ambulance_id, unit_name, availability FROM AMBULANCE").fetchall()
        if ambs:
            st.dataframe(pd.DataFrame([dict(r) for r in ambs]), use_container_width=True)
            
    conn.close()

except Exception as e:
    st.error(f"Error connecting to database: {e}")

# Fallback for manual or logic rerunning if no library is available
if not st_autorefresh:
    time.sleep(2)
    st.rerun()
