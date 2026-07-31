"""
MedShield AI — Laptop 1 Flask Backend
Pump Simulator + inter-laptop communication endpoints
"""

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import sqlite3, threading, time, random, os
from datetime import datetime
from dotenv import load_dotenv

from config import PUMP_IP, PUMP_PORT, DEVICE_ID, DEVICE_MAC

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = "medshield_pump_secret_2024"
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DB_PATH = os.path.join(os.path.dirname(__file__), "pump_state.db")

# ─── In-memory pump state ────────────────────────────────────────────────────
pump_state = {
    "device_id"          : DEVICE_ID,
    "device_mac"         : DEVICE_MAC,
    "status"             : "SAFE",
    "glucose_level"      : 98.0,
    "current_dose"       : 4.0,
    "basal_rate"         : 1.2,
    "total_dose_today"   : 12.0,
    "battery_percent"    : 87.0,
    "last_command_time"  : datetime.now().isoformat(),
    "last_command_from"  : "CGM_001",
    "is_compromised"     : False,
    "medshield_blocked"  : False,
    "alert_message"      : None,
    "block_reason"       : None,
    "risk_score"         : 0.18,
    "trust_score"        : 0.92,
    "blocked_count"      : 0,
    "attack_count"       : 0,
    "dose_history"       : []
}

simulation_running = False
state_lock         = threading.Lock()

# ─── DB setup ────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS dose_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp    TEXT,
            units        REAL,
            source       TEXT,
            source_mac   TEXT,
            auth_token   TEXT,
            status_after TEXT,
            is_attack    INTEGER,
            blocked_by   TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS block_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     TEXT,
            attack_type   TEXT,
            source        TEXT,
            units         REAL,
            risk_score    REAL,
            layer_trigger TEXT,
            shap_reason   TEXT,
            blocked_by    TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_dose(units, source, mac, token, status, blocked_by="NONE"):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""INSERT INTO dose_log
        (timestamp,units,source,source_mac,auth_token,status_after,is_attack,blocked_by)
        VALUES(?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(), units, source, mac,
         token, status, 1 if units > 50 else 0, blocked_by))
    conn.commit(); conn.close()

def log_block(attack_type, source, units, risk, layer, shap, blocked_by):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""INSERT INTO block_log
        (timestamp,attack_type,source,units,risk_score,layer_trigger,shap_reason,blocked_by)
        VALUES(?,?,?,?,?,?,?,?)""",
        (datetime.now().isoformat(), attack_type, source,
         units, risk, layer, shap, blocked_by))
    conn.commit(); conn.close()

def emit_state():
    with state_lock:
        state_copy              = dict(pump_state)
        state_copy["dose_history"] = list(pump_state["dose_history"])
    socketio.emit("pump_update", state_copy)

# ─── POST /dose — receive a dose command ─────────────────────────────────────
@app.route("/dose", methods=["POST"])
def receive_dose():
    data       = request.get_json(force=True) or {}
    units      = float(data.get("units", 0))
    source     = str(data.get("source", "UNKNOWN"))
    auth_token = str(data.get("auth_token", ""))
    source_mac = str(data.get("source_mac", "00:00:00:00:00:00"))

    with state_lock:
        pump_state["current_dose"]       = units
        pump_state["total_dose_today"]  += units
        pump_state["last_command_time"]  = datetime.now().isoformat()
        pump_state["last_command_from"]  = source
        pump_state["medshield_blocked"]  = False

        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "source"   : source,
            "units"    : units,
            "is_attack": units > 50
        }
        pump_state["dose_history"].insert(0, entry)
        pump_state["dose_history"] = pump_state["dose_history"][:30]

        if units > 50:
            pump_state["status"]         = "COMPROMISED"
            pump_state["is_compromised"] = True
            pump_state["attack_count"]  += 1
            pump_state["alert_message"]  = (
                f"⚠ ATTACK SUCCEEDED: {units:.0f}U injected from {source}. "
                f"Patient at critical risk! MedShield was NOT active."
            )
            status_after = "COMPROMISED"
        else:
            pump_state["status"]         = "SAFE"
            pump_state["is_compromised"] = False
            pump_state["alert_message"]  = None
            status_after = "SAFE"

    log_dose(units, source, source_mac, auth_token, status_after)
    emit_state()
    return jsonify(pump_state)

# ─── POST /basal ──────────────────────────────────────────────────────────────
@app.route("/basal", methods=["POST"])
def set_basal():
    data   = request.get_json(force=True) or {}
    rate   = float(data.get("rate", 1.0))
    source = str(data.get("source", "UNKNOWN"))
    with state_lock:
        pump_state["basal_rate"]         = rate
        pump_state["last_command_time"]  = datetime.now().isoformat()
        pump_state["last_command_from"]  = source
        if rate > 5.0:
            pump_state["status"]         = "COMPROMISED"
            pump_state["is_compromised"] = True
            pump_state["alert_message"]  = f"⚠ Abnormal basal rate: {rate} u/hr"
        else:
            pump_state["status"]         = "SAFE"
            pump_state["is_compromised"] = False
            pump_state["alert_message"]  = None
    emit_state()
    return jsonify(pump_state)

# ─── GET /status ──────────────────────────────────────────────────────────────
@app.route("/status", methods=["GET"])
def get_status():
    with state_lock:
        return jsonify(pump_state)

# ─── POST /reset ──────────────────────────────────────────────────────────────
@app.route("/reset", methods=["POST"])
def reset_pump():
    global simulation_running
    with state_lock:
        pump_state["status"]             = "SAFE"
        pump_state["glucose_level"]      = 98.0
        pump_state["current_dose"]       = 4.0
        pump_state["basal_rate"]         = 1.2
        pump_state["total_dose_today"]   = 12.0
        pump_state["battery_percent"]    = 87.0
        pump_state["last_command_time"]  = datetime.now().isoformat()
        pump_state["last_command_from"]  = "SYSTEM"
        pump_state["is_compromised"]     = False
        pump_state["medshield_blocked"]  = False
        pump_state["alert_message"]      = None
        pump_state["block_reason"]       = None
        pump_state["risk_score"]         = 0.18
        pump_state["trust_score"]        = 0.92
        pump_state["dose_history"]       = []
        pump_state["blocked_count"]      = 0
        pump_state["attack_count"]       = 0
    emit_state()
    return jsonify({"status": "reset", "message": "Pump reset to safe state"})

# ─── POST /medshield_block — called by Laptop 3 when it blocks an attack ─────
@app.route("/medshield_block", methods=["POST"])
def medshield_block():
    """
    Laptop 3 (MedShield AI) calls this endpoint when it intercepts and
    blocks an attack. This lets Laptop 1 UI show the block event without
    the pump ever being compromised.
    """
    data        = request.get_json(force=True) or {}
    attack_type = str(data.get("attack_type",  "Unknown Attack"))
    source      = str(data.get("source",       "UNKNOWN"))
    units       = float(data.get("units",       0))
    risk_score  = float(data.get("risk_score",  0.97))
    layer       = str(data.get("layer_trigger", "MedShield AI"))
    shap_reason = str(data.get("shap_reason",   "Anomaly detected"))
    trust_decay = float(data.get("trust_decay", 0.10))

    with state_lock:
        pump_state["medshield_blocked"]  = True
        pump_state["is_compromised"]     = False
        pump_state["status"]             = "PROTECTED"
        pump_state["risk_score"]         = risk_score
        pump_state["trust_score"]        = max(0.0, pump_state["trust_score"] - trust_decay)
        pump_state["blocked_count"]     += 1
        pump_state["block_reason"]       = (
            f"BLOCKED by MedShield AI\n"
            f"Attack: {attack_type}\n"
            f"Source: {source} | Dose: {units:.0f}U\n"
            f"Triggered: {layer}\n"
            f"Reason: {shap_reason}\n"
            f"Risk Score: {risk_score:.2f}"
        )
        pump_state["alert_message"]      = None

        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "source"   : f"[BLOCKED] {source}",
            "units"    : units,
            "is_attack": True,
            "blocked"  : True
        }
        pump_state["dose_history"].insert(0, entry)
        pump_state["dose_history"] = pump_state["dose_history"][:30]

    log_block(attack_type, source, units, risk_score, layer, shap_reason, "MedShield_L3")
    emit_state()

    return jsonify({
        "status"  : "acknowledged",
        "message" : "Block event received and displayed on Laptop 1",
        "blocked_count": pump_state["blocked_count"]
    })

# ─── POST /simulate_normal ────────────────────────────────────────────────────
@app.route("/simulate_normal", methods=["POST"])
def start_sim():
    global simulation_running
    if simulation_running:
        return jsonify({"status": "already_running"})
    simulation_running = True
    threading.Thread(target=run_simulation, daemon=True).start()
    return jsonify({"status": "simulation_started"})

@app.route("/simulate_stop", methods=["POST"])
def stop_sim():
    global simulation_running
    simulation_running = False
    return jsonify({"status": "stopped"})

def run_simulation():
    global simulation_running
    dose_timer = 0; basal_timer = 0
    while simulation_running:
        with state_lock:
            if not pump_state["is_compromised"]:
                delta = random.uniform(-2.0, 2.0)
                pump_state["glucose_level"] = round(
                    max(70.0, min(180.0, pump_state["glucose_level"] + delta)), 1)
                pump_state["battery_percent"] = max(
                    0.0, pump_state["battery_percent"] - 0.001)
        emit_state()
        time.sleep(2)
        dose_timer  += 2
        basal_timer += 2

        if dose_timer >= 300 and not pump_state["is_compromised"]:
            dose_timer = 0
            units = round(random.uniform(3.5, 6.0), 1)
            with state_lock:
                pump_state["current_dose"]       = units
                pump_state["total_dose_today"]  += units
                pump_state["last_command_time"]  = datetime.now().isoformat()
                pump_state["last_command_from"]  = "CGM_001"
                entry = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "source": "CGM_001", "units": units, "is_attack": False
                }
                pump_state["dose_history"].insert(0, entry)
                pump_state["dose_history"] = pump_state["dose_history"][:30]
            log_dose(units, "CGM_001", "AA:BB:CC:DD:EE:02", "valid", "SAFE")
            emit_state()

        if basal_timer >= 1800 and not pump_state["is_compromised"]:
            basal_timer = 0
            rate = round(random.uniform(1.0, 1.5), 2)
            with state_lock:
                pump_state["basal_rate"] = rate
            emit_state()

# ─── GET /history ─────────────────────────────────────────────────────────────
@app.route("/history", methods=["GET"])
def get_history():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT * FROM dose_log ORDER BY id DESC LIMIT 30")
    rows = c.fetchall(); conn.close()
    return jsonify([{
        "id":r[0],"timestamp":r[1],"units":r[2],"source":r[3],
        "source_mac":r[4],"auth_token":r[5],"status_after":r[6],
        "is_attack":bool(r[7]),"blocked_by":r[8]
    } for r in rows])

# ─── GET /blocks ──────────────────────────────────────────────────────────────
@app.route("/blocks", methods=["GET"])
def get_blocks():
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT * FROM block_log ORDER BY id DESC LIMIT 20")
    rows = c.fetchall(); conn.close()
    return jsonify([{
        "id":r[0],"timestamp":r[1],"attack_type":r[2],"source":r[3],
        "units":r[4],"risk_score":r[5],"layer_trigger":r[6],
        "shap_reason":r[7],"blocked_by":r[8]
    } for r in rows])

# ─── GET /ping ────────────────────────────────────────────────────────────────
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({
        "status"    : "online",
        "device"    : DEVICE_ID,
        "timestamp" : datetime.now().isoformat()
    })

# ─── WebSocket ────────────────────────────────────────────────────────────────
@socketio.on("connect")
def on_connect():
    with state_lock:
        emit("pump_update", pump_state)

@socketio.on("request_state")
def on_request():
    with state_lock:
        emit("pump_update", pump_state)

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    host = os.getenv("PUMP_IP", "0.0.0.0")
    port = int(os.getenv("PUMP_PORT", PUMP_PORT))
    print(f"""
╔══════════════════════════════════════════════════════╗
║          MedShield AI — Laptop 1 (Pump Server)       ║
╠══════════════════════════════════════════════════════╣
║  Device    : {DEVICE_ID}                  ║
║  Running   : http://{host}:{port}                    ║
║  Status    : SAFE ✅                                 ║
╠══════════════════════════════════════════════════════╣
║  Endpoints:                                          ║
║  POST /dose            ← receive commands            ║
║  POST /medshield_block ← Laptop 3 block notification ║
║  GET  /status          ← current pump state          ║
║  POST /reset           ← reset pump                  ║
╚══════════════════════════════════════════════════════╝
    """)
    socketio.run(app, host=host, port=port,
                 debug=False, allow_unsafe_werkzeug=True)
