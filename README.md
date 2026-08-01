# MedShield AI — Laptop 1 (Pump Interface)

This is just the pump side of the MedShield AI demo: `app.py` (Flask backend
simulating the insulin pump) and `cvb.py` (PyQt6 desktop dashboard).

`config.py` is already set up to reach the MedShield defense server
(Laptop 3) at `10.200.65.134` over WiFi — both machines need to be on the
same network. **This IP changes often** (it's been different almost every
sync) whenever that laptop reconnects to WiFi — if "MedShield: ON" attacks
don't show up as BLOCKED (Laptop 3's Live Command Feed stays empty), this
is the first thing to check: get the current IP there via `ipconfig` and
update `MEDSHIELD_IP` in `config.py` to match, then restart `app.py` and
`cvb.py`.

## Setup

```powershell
pip install -r requirements.txt
```

## Run (two terminals)

**Terminal 1 — pump backend:**
```powershell
$env:PYTHONIOENCODING = "utf-8"
python app.py
```
Runs on `http://127.0.0.1:5000`.

**Terminal 2 — GUI dashboard:**
```powershell
$env:PYTHONIOENCODING = "utf-8"
python cvb.py
```

`PYTHONIOENCODING=utf-8` is required each time — Windows' console defaults
to an encoding that crashes on the startup banner otherwise.

`cvb.py` is the current dashboard; `dashboard.py` / `dashboard_base.py` are
earlier versions kept for reference, not needed to run the demo.
