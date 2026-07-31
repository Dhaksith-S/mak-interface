# MedShield AI — Laptop 1 (Pump Interface)

This is just the pump side of the MedShield AI demo: `app.py` (Flask backend
simulating the insulin pump) and `cvb.py` (PyQt6 desktop dashboard).

`config.py` is already set up to reach the MedShield defense server
(Laptop 3) at `10.64.194.169` over WiFi — both machines need to be on the
same network. If that laptop reconnects to a different network, get its
new IP there via `ipconfig` and update `MEDSHIELD_IP` in `config.py`.

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
