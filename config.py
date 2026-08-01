"""
MedShield AI — Central Network Config
Change IPs here ONLY. Everything else reads from this file.
"""

# ── Laptop IPs ────────────────────────────────────────────────────────────
# This copy is set up for a 2-machine test: run this Interface/ folder on
# your own laptop (Laptop 1 — the pump), while MedShield (Laptop 3) keeps
# running on the machine at MEDSHIELD_IP below, over the same WiFi/router.
PUMP_IP       = "127.0.0.1"       # Laptop 1 — this machine (yours)
ATTACKER_IP   = "127.0.0.1"       # Laptop 2 — not used in this handoff
MEDSHIELD_IP  = "10.251.160.169"   # Laptop 3 — the MedShield laptop's real LAN IP

# If MedShield's laptop reconnects to a different network (its IP
# changes), get its new one there via `ipconfig` and update MEDSHIELD_IP
# above to match. Both machines must be on the same WiFi/router.

# ── Ports ───────────────────────────────────────────────────────────────────
PUMP_PORT      = 5000
MEDSHIELD_PORT = 8000

# ── Derived URLs ─────────────────────────────────────────────────────────────
PUMP_URL       = f"http://{PUMP_IP}:{PUMP_PORT}"
MEDSHIELD_URL  = f"http://{MEDSHIELD_IP}:{MEDSHIELD_PORT}"

# ── Device identity ──────────────────────────────────────────────────────────
DEVICE_ID  = "InsulinPump_001"
DEVICE_MAC = "AA:BB:CC:DD:EE:01"
