"""
MedShield AI — Hybrid Dashboard (Laptop 1)
Realistic pump animation + 9-layer defence + 3-laptop network integration
"""

import sys, math, random, threading, time
from datetime import datetime

import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGridLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy, QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, QPointF, QRectF, QPropertyAnimation,
    pyqtProperty, QThread, pyqtSignal, QEasingCurve, QRect, QEvent
)
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QFont,
    QLinearGradient, QRadialGradient, QPolygonF
)
import pyqtgraph as pg

from config import PUMP_URL, MEDSHIELD_URL, DEVICE_ID, DEVICE_MAC

# ─── Palette ─────────────────────────────────────────────────────────────────
# Shared with Laptop 3's dashboard (Laptop3/dashboard/index.html) so both
# machines read as one connected product rather than two different tools:
# same clinical-teal brand accent, same surfaces, same validated status colors.
BG_MAIN  = "#0a0e13"   # --surface-0
BG_PANEL = "#131a22"   # --surface-1
BG_CARD  = "#1a232c"   # --surface-2
BORDER   = "#232d38"
CYAN     = "#1fb3a3"   # brand accent (was neon cyan #00c8ff)
GREEN    = "#0ca30c"   # status: good (was acid green #30ff80)
YELLOW   = "#fab219"   # status: warning
ORANGE   = "#ec835a"   # status: serious
RED      = "#d03b3b"   # status: critical
MUTED    = "#56626c"
TDIM     = "#8394a1"

# Each scenario is built to land on ONE specific pipeline layer so every
# layer gets a real, reachable use case in the demo -- not just the fast
# rule/fingerprint checks. main.py only runs L3/L6 (the trained ML models)
# when L1/L2/L4/L5 all pass, and only lets L5 fire once a source has 5+
# prior ALLOWED requests recorded -- so a scenario using an invalid token
# or spoofed MAC can never reach the ML layers, and a one-shot spike can
# never reach L5. Credentials/units below are chosen so exactly one layer
# is responsible for each block:
#
#   Overdose         -> L2 Rule Engine (dosage cap) + ESC   [valid creds, 200U]
#   Rapid Repeat     -> L2 Rule Engine (rate limit)         [valid creds, burst of small doses]
#   Spoof Device     -> L4 Device Fingerprint (MAC mismatch)[valid token, wrong device's MAC]
#   Pairing Hijack   -> L1 Zero Trust Engine (no token)     [known device, empty token]
#   Cred Theft       -> L5 Behaviour Baseline (drift)       [valid creds, seeds a baseline then spikes it]
#   Stealth Injection-> L3 AI Anomaly + L6 Digital Twin     [fully valid/compliant, still model-flagged]
ATTACKS = [
    {
        "name": "Overdose", "kind": "single",
        "desc": "Overdose Command (200U)",
        "payload": {"units": 200, "source": "CGM_001", "auth_token": "valid_cgm_session",
                    "source_mac": "AA:BB:CC:DD:EE:02"},
    },
    {
        "name": "Rapid Repeat", "kind": "burst", "count": 42,
        "desc": "Rapid Repeat Attack (command flood)",
        "payload": {"units": 3, "source": "CGM_001", "auth_token": "valid_cgm_session",
                    "source_mac": "AA:BB:CC:DD:EE:02"},
    },
    {
        "name": "Spoof Device", "kind": "single",
        "desc": "Device Spoofing (MAC identity mismatch)",
        "payload": {"units": 4, "source": "CGM_001", "auth_token": "valid_cgm_session",
                    "source_mac": "AA:BB:CC:DD:EE:03"},  # real MAC belongs to DrApp_A, not CGM_001
    },
    {
        "name": "Pairing Hijack", "kind": "single",
        "desc": "BLE Pairing Hijack (missing credentials)",
        "payload": {"units": 5, "source": "PatientApp", "auth_token": "",
                    "source_mac": "AA:BB:CC:DD:EE:04"},
    },
    {
        "name": "Cred Theft", "kind": "seed_then_spike", "seed_count": 5,
        "desc": "Stolen Credentials -- Baseline Drift",
        "seed_payload": {"units": 2.5, "source": "DrApp_A", "auth_token": "valid_drapp_session",
                          "source_mac": "AA:BB:CC:DD:EE:03"},
        "spike_payload": {"units": 18, "source": "DrApp_A", "auth_token": "valid_drapp_session",
                           "source_mac": "AA:BB:CC:DD:EE:03"},
    },
    {
        "name": "Stealth Injection", "kind": "single",
        "desc": "AI-Evasion Attack (rule-compliant, model-caught)",
        "payload": {"units": 45, "source": "PatientApp", "auth_token": "valid_patient_session",
                    "source_mac": "AA:BB:CC:DD:EE:04"},
    },
]

LAYERS = [
    ("L1",  "Zero Trust Engine",       "ZTA · mTLS · JWT · RBAC"),
    ("L2",  "Rule Engine",             "Dosage cap · Rate limit · Whitelist"),
    ("L3",  "AI Anomaly Detection",    "Isolation Forest + Autoencoder"),
    ("L4",  "Device Fingerprint",      "MAC · RSSI · Timing · GPS"),
    ("L5",  "Behaviour Baseline",      "Z-score · Per-device · 3σ"),
    ("L6",  "Digital Twin Validator",  "LSTM · State divergence"),
    ("L7",  "Explainable AI (SHAP)",   "Feature importance · Human reason"),
    ("L8",  "Adaptive Trust Engine",   "Bayesian · Real-time decay"),
    ("ESC", "Emergency Safety Ctrl",   "IEC 62443 · FDA Failsafe"),
]

# ══════════════════════════════════════════════════════════════════════════════
#  GLUCOSE ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class GlucoseEngine:
    def __init__(self):
        self.current = 132.0
        self.active_insulin = 0.0
        self.history = [132.0] * 120

    def inject(self, units):
        self.active_insulin += min(units, 300.0)

    def tick(self):
        # No idle drift/random-walk here on purpose: self.current only ever
        # moves via an explicit server correction (_on_flask_state) or an
        # injected dose, so this display can never disagree with Laptop 1's
        # own /status -- and therefore never disagrees with Laptop 3 (or
        # anyone else) reading that same endpoint.
        if self.active_insulin > 0:
            drop = min(self.active_insulin * 0.5, 6.0)
            self.current -= drop
            self.active_insulin = max(0.0, self.active_insulin - drop * 0.8)
        self.current = max(20.0, min(380.0, self.current))
        self.history.append(self.current)
        self.history = self.history[-120:]

    def status(self):
        g = self.current
        if g < 54:  return "SEVERE HYPO",   RED
        if g < 70:  return "HYPOGLYCEMIA",  ORANGE
        if g < 100: return "LOW NORMAL",    YELLOW
        if g < 180: return "NORMAL",        GREEN
        if g < 250: return "HIGH",          ORANGE
        return             "HYPERGLYCEMIA", RED


# ══════════════════════════════════════════════════════════════════════════════
#  PARTICLE
# ══════════════════════════════════════════════════════════════════════════════
class Particle:
    def __init__(self):
        self.t       = random.uniform(-0.05, 0.0)
        self.opacity = random.uniform(0.5, 1.0)
        self.size    = random.uniform(1.8, 3.5)


# ══════════════════════════════════════════════════════════════════════════════
#  PUMP + PATIENT SCENE
# ══════════════════════════════════════════════════════════════════════════════
class PumpPatientScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(860, 285)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dose = 2.0; self.critical = False
        self.warning = False; self.blocked = False
        self._flash = 0.0; self._phase = 0.0
        self.particles: list[Particle] = []
        self._flash_anim = None

        # ── Attack packet state ────────────────────────────────────────────
        self._packets        = []      # list of {t, blocked}  (multiple packets)
        self._show_compromised_overlay = False
        self._show_blocked_overlay     = False
        self._explosion_t    = -1.0    # 0..1 while exploding at pump
        self._screen_flash_t = 0.0    # full-widget red flash countdown (frames)
        self._lightning_segs = []      # crackle lines along tube
        self._lightning_tmr  = 0

        t = QTimer(self); t.timeout.connect(self._tick); t.start(16)

    @pyqtProperty(float)
    def flash(self): return self._flash

    @flash.setter
    def flash(self, v):
        self._flash = v; self.update()

    def set_state(self, dose, blocked=False):
        prev = self.critical
        self.dose = dose; self.blocked = blocked
        self.warning  = 50 <= dose < 200
        self.critical = dose >= 200 or blocked
        if (self.critical or self.warning) and not prev:
            if self._flash_anim: self._flash_anim.stop()
            a = QPropertyAnimation(self, b"flash", self)
            a.setDuration(400); a.setStartValue(0.0)
            a.setKeyValueAt(0.5, 1.0); a.setEndValue(0.0)
            a.setLoopCount(-1); a.start()
            self._flash_anim = a
        elif not self.critical and not self.warning:
            if self._flash_anim: self._flash_anim.stop(); self._flash_anim = None
            self._flash = 0.0

    def start_attack_packet(self, blocked=False):
        """Launch a SWARM of red attack packets across the tube."""
        # 3 packets staggered
        self._packets = [
            {"t": 0.0,   "blocked": blocked},
            {"t": -0.15, "blocked": blocked},
            {"t": -0.30, "blocked": blocked},
        ]
        self._show_compromised_overlay = False
        self._show_blocked_overlay     = False
        self._explosion_t   = -1.0
        self._screen_flash_t = 0.0
        # start lightning immediately
        self._lightning_tmr = 999

    def reset_overlays(self):
        self._packets              = []
        self._show_compromised_overlay = False
        self._show_blocked_overlay     = False
        self._explosion_t          = -1.0
        self._screen_flash_t       = 0.0
        self._lightning_segs       = []

    def _speed(self):
        if self.blocked: return 0.0
        d = self.dose
        if d <= 0:  return 0.0
        if d <= 5:  return d * 0.06
        if d <= 20: return d * 0.04
        if d <= 50: return d * 0.025
        return min(d * 0.013, 1.8)

    def _regen_lightning(self, s, c1, c2, e):
        """Generate jagged lightning segments along tube path."""
        segs = []
        steps = 18
        for i in range(steps):
            t0 = i / steps
            t1 = (i + 1) / steps
            x0, y0 = self._bz(t0, s, c1, c2, e)
            x1, y1 = self._bz(t1, s, c1, c2, e)
            jitter = 14
            mx = (x0 + x1) / 2 + random.uniform(-jitter, jitter)
            my = (y0 + y1) / 2 + random.uniform(-jitter, jitter)
            segs.append(((x0, y0), (mx, my), (x1, y1)))
        self._lightning_segs = segs

    def _tick(self):
        self._phase = (self._phase + 0.04) % (2 * math.pi)

        # advance packets
        finished_blocked = False
        finished_attack  = False
        still_active = []
        for pkt in self._packets:
            pkt["t"] += 0.018   # speed — crosses in ~55 frames ≈ 0.9s
            if pkt["t"] >= 1.0:
                if pkt["blocked"]:
                    finished_blocked = True
                else:
                    finished_attack = True
                    self._explosion_t  = 0.0   # start explosion
                    self._screen_flash_t = 18  # ~18 frames of red flash
            else:
                still_active.append(pkt)
        self._packets = still_active

        if finished_blocked and not self._packets:
            self._show_blocked_overlay = True
        if finished_attack:
            pass  # explosion handles it

        # advance explosion
        if self._explosion_t >= 0:
            self._explosion_t += 0.04
            if self._explosion_t >= 1.0:
                self._explosion_t = -1.0
                if not any(not p["blocked"] for p in self._packets):
                    self._show_compromised_overlay = True

        # screen flash countdown
        if self._screen_flash_t > 0:
            self._screen_flash_t -= 1

        # lightning: regenerate every ~4 frames when active
        if self._packets or (self.critical and not self.blocked):
            self._lightning_tmr += 1
            if self._lightning_tmr >= 4:
                self._lightning_tmr = 0
                # We'll regen in paintEvent where we have bezier points
                self._need_lightning = True
        else:
            self._lightning_segs = []
            self._need_lightning  = False

        # particles
        spd = self._speed()
        if self.critical and not self.blocked:
            spd = max(spd, 1.4)
        for pp in self.particles: pp.t += spd * 0.016
        self.particles = [pp for pp in self.particles if pp.t < 1.05]
        if not self.blocked and self.dose > 0:
            rate = (1.2 if self.critical else
                    (0.5 if self.warning  else 0.2))
            while random.random() < rate and len(self.particles) < 80:
                self.particles.append(Particle())
        self.update()

    @staticmethod
    def _bz(t, p0, p1, p2, p3):
        u = 1-t
        return (u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        px, py, pw, ph = 32, h//2-85, 92, 148
        sx, sy = w-195, h//2-12

        self._body(p, w, h)
        t0 = (px+pw-2, py+20)
        c1 = (t0[0]+65, t0[1]-45)
        c2 = (sx-85, sy-65)
        te = (sx, sy)

        # ── regen lightning if needed ──────────────────────────────────────
        if getattr(self, "_need_lightning", False):
            self._regen_lightning(t0, c1, c2, te)
            self._need_lightning = False

        self._tube(p, t0, c1, c2, te)

        # ── lightning crackle ──────────────────────────────────────────────
        if self._lightning_segs:
            self._draw_lightning(p)

        self._particles(p, t0, c1, c2, te)

        # ── draw all attack packets ────────────────────────────────────────
        for pkt in self._packets:
            if pkt["t"] >= 0.0:
                self._draw_attack_packet(p, t0, c1, c2, te, pkt)

        # ── explosion at pump arrival ──────────────────────────────────────
        if self._explosion_t >= 0:
            self._draw_explosion(p, px, py, pw, ph)

        # ── full-widget red flash ──────────────────────────────────────────
        if self._screen_flash_t > 0:
            alpha = int(180 * (self._screen_flash_t / 18))
            p.setBrush(QBrush(QColor(220, 0, 0, alpha)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(0, 0, w, h)

        self._site(p, sx, sy)
        self._pump(p, px, py, pw, ph)
        self._port(p, px+pw//2, py)

        # ── overlays ──────────────────────────────────────────────────────
        if self.blocked or self._show_blocked_overlay:
            self._block_badge(p, t0, c1, c2, te)
            self._draw_shield_overlay(p, t0, c1, c2, te)
        if self._show_compromised_overlay and self.critical:
            self._draw_pump_compromised_badge(p, px, py, pw, ph, w, h)

    # ── NEW: lightning crackle along tube ─────────────────────────────────
    def _draw_lightning(self, p):
        for (x0, y0), (mx, my), (x1, y1) in self._lightning_segs:
            alpha = random.randint(120, 255)
            pen = QPen(QColor(255, 80, 80, alpha), random.uniform(0.8, 2.2),
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(x0, y0)
            path.quadTo(mx, my, x1, y1)
            p.drawPath(path)
            # white core on some segments
            if random.random() > 0.6:
                pen2 = QPen(QColor(255, 200, 200, alpha // 2), 0.5)
                p.setPen(pen2); p.drawPath(path)

    def _draw_attack_packet(self, p, s, c1, c2, e, pkt):
        """Large, impossible-to-miss red packet with massive glow."""
        t  = max(0.0, min(1.0, pkt["t"]))
        x, y = self._bz(t, s, c1, c2, e)

        # ── mega glow layers ───────────────────────────────────────────────
        for radius, alpha in [(55, 25), (38, 50), (24, 100), (14, 180)]:
            gr = QRadialGradient(QPointF(x, y), radius)
            gr.setColorAt(0, QColor(255, 20, 20, alpha))
            gr.setColorAt(1, QColor(255, 20, 20, 0))
            p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), radius, radius)

        # ── skull core (big) ───────────────────────────────────────────────
        size = 16
        p.setBrush(QBrush(QColor(255, 40, 40)))
        p.setPen(QPen(QColor(255, 160, 160), 2))
        pts = QPolygonF([
            QPointF(x,        y - size),
            QPointF(x + size*0.7, y),
            QPointF(x,        y + size),
            QPointF(x - size*0.7, y),
        ])
        p.drawPolygon(pts)

        # ── ☠ text ────────────────────────────────────────────────────────
        p.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255, 255, 255)))
        p.drawText(QRectF(x-12, y-10, 24, 20), Qt.AlignmentFlag.AlignCenter, "☠")

        # ── speed trail ───────────────────────────────────────────────────
        for i in range(1, 6):
            tt = max(0.0, t - i * 0.025)
            tx, ty = self._bz(tt, s, c1, c2, e)
            ta = int(120 - i * 22)
            tr = 10 - i * 1.5
            p.setBrush(QBrush(QColor(255, 50, 50, ta)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(tx, ty), tr, tr)

    def _draw_explosion(self, p, px, py, pw, ph):
        """Huge radial explosion burst at pump when packet arrives."""
        et = self._explosion_t  # 0..1
        cx = px + pw // 2
        cy = py + ph // 2

        # expanding ring
        max_r = 120 + 80 * et
        alpha = int(220 * (1.0 - et))
        for radius, col_alpha in [
            (max_r,       int(alpha * 0.3)),
            (max_r * 0.7, int(alpha * 0.6)),
            (max_r * 0.4, int(alpha * 0.9)),
        ]:
            gr = QRadialGradient(QPointF(cx, cy), radius)
            gr.setColorAt(0, QColor(255, 60, 0, col_alpha))
            gr.setColorAt(0.4, QColor(255, 20, 20, col_alpha // 2))
            gr.setColorAt(1, QColor(255, 0, 0, 0))
            p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

        # spiky rays
        if et < 0.6:
            ray_alpha = int(255 * (1.0 - et / 0.6))
            p.setPen(QPen(QColor(255, 100, 0, ray_alpha), 2.5))
            ray_len = (40 + 80 * et)
            for angle in range(0, 360, 30):
                rad = math.radians(angle + et * 90)
                ex_ = cx + ray_len * math.cos(rad)
                ey_ = cy + ray_len * math.sin(rad)
                p.drawLine(int(cx), int(cy), int(ex_), int(ey_))

        # HACKED text
        if et < 0.7:
            txt_alpha = int(255 * (1.0 - et / 0.7))
            p.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
            p.setPen(QPen(QColor(255, 50, 50, txt_alpha)))
            p.drawText(QRectF(cx - 80, cy - 16, 160, 32),
                       Qt.AlignmentFlag.AlignCenter, "☠ HACKED ☠")

    def _draw_shield_overlay(self, p, s, c1, c2, e):
        """Semi-transparent shield across the tube midpoint when blocked."""
        mx, my = self._bz(0.5, s, c1, c2, e)
        pulse = 0.55 + 0.45 * math.sin(self._phase * 3)
        gr = QRadialGradient(QPointF(mx, my), 55)
        gr.setColorAt(0, QColor(255, 140, 0, int(110 * pulse)))
        gr.setColorAt(1, QColor(255, 140, 0, 0))
        p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(mx, my), 55, 55)
        p.setBrush(QBrush(QColor(160, 80, 0, 220)))
        p.setPen(QPen(QColor(255, 160, 0), 2.5))
        p.drawRoundedRect(QRectF(mx-48, my-16, 96, 32), 8, 8)
        p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255, 230, 160)))
        p.drawText(QRectF(mx-48, my-16, 96, 32),
                   Qt.AlignmentFlag.AlignCenter, "🛡 INTERCEPTED")

    def _draw_pump_compromised_badge(self, p, x, y, w, h, sw, sh):
        """Full pump + big banner: COMPROMISED ☠."""
        sx, sy = x+7, y+18
        scw, sch = w-14, 64
        flash_a = int(200 * abs(math.sin(self._phase * 4)))
        p.setBrush(QBrush(QColor(220, 0, 0, flash_a)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(sx, sy, scw, sch), 5, 5)
        p.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255, 200, 200)))
        p.drawText(QRectF(sx, sy+8,  scw, 18), Qt.AlignmentFlag.AlignCenter, "COMPROMISED")
        p.drawText(QRectF(sx, sy+26, scw, 18), Qt.AlignmentFlag.AlignCenter, "☠")

        # big "PUMP COMPROMISED" banner across scene center
        bx, by_ = 0, sh // 2 - 22
        pulse = 0.5 + 0.5 * abs(math.sin(self._phase * 3))
        ba = int(200 * pulse)
        p.setBrush(QBrush(QColor(180, 0, 0, ba)))
        p.setPen(QPen(QColor(255, 60, 60), 2))
        p.drawRect(bx, by_, sw, 44)
        p.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255, 80, 80)))
        p.drawText(QRectF(bx, by_, sw, 44),
                   Qt.AlignmentFlag.AlignCenter, "⚠  PUMP COMPROMISED  ☠  PATIENT AT RISK  ⚠")




    def _body(self, p, w, h):
        g = QLinearGradient(w*.38, 0, w, 0)
        g.setColorAt(0,  QColor(5,10,18,0))
        g.setColorAt(.22,QColor(190,145,110,190))
        g.setColorAt(.65,QColor(220,175,140,255))
        g.setColorAt(1,  QColor(195,150,115,255))
        p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(w*.38, 0, w*.62, h))
        jy = h*.74
        j = QLinearGradient(0, jy, 0, h)
        j.setColorAt(0,  QColor(48,92,158,0))
        j.setColorAt(.12,QColor(48,92,158,210))
        j.setColorAt(1,  QColor(33,66,118,255))
        p.setBrush(QBrush(j))
        p.drawRect(QRectF(w*.38, jy, w*.62, h-jy))
        p.setPen(QPen(QColor(78,128,178,110), 1.5, Qt.PenStyle.DashLine))
        p.drawLine(int(w*.41), int(jy+9), int(w), int(jy+9))
        nx, ny = int(w*.52), int(h*.37)
        ng = QRadialGradient(QPointF(nx, ny), 10)
        ng.setColorAt(0,QColor(168,122,92)); ng.setColorAt(1,QColor(220,175,140,0))
        p.setBrush(QBrush(ng)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(nx, ny), 9, 7)

    def _tube(self, p, s, c1, c2, e):
        path = QPainterPath()
        path.moveTo(*s); path.cubicTo(c1[0],c1[1],c2[0],c2[1],e[0],e[1])
        if self.critical and not self.blocked:
            # dramatic red outer glow — pulsing
            pulse = 0.5 + 0.5 * math.sin(self._phase * 2)
            ga = int(60 + 60 * pulse)
            p.strokePath(path, QPen(QColor(255, 20, 20, ga),  20, cap=Qt.PenCapStyle.RoundCap))
            p.strokePath(path, QPen(QColor(255, 50, 50, 80),  12, cap=Qt.PenCapStyle.RoundCap))
            gc = QColor(255, 50, 50, 35)
        elif self.blocked:
            gc = QColor(255, 50, 50, 25)
        else:
            gc = QColor(31, 179, 163, 18)
        p.strokePath(path, QPen(gc, 10, cap=Qt.PenCapStyle.RoundCap))
        p.strokePath(path, QPen(QColor(200,220,230,155), 4, cap=Qt.PenCapStyle.RoundCap))
        p.strokePath(path, QPen(QColor(80,120,150,95), 1.5, cap=Qt.PenCapStyle.RoundCap))

    def _particles(self, p, s, c1, c2, e):
        if self.blocked: return
        bc = (QColor(255,50,50) if self.critical else
              QColor(255,195,0) if self.warning  else QColor(31,179,163))
        for pt in self.particles:
            t = max(0.0, min(1.0, pt.t))
            x, y = self._bz(t, s, c1, c2, e)
            a = int(255 * pt.opacity)
            col = QColor(bc.red(), bc.green(), bc.blue(), a)
            r = pt.size
            glow_r = r * 5.5 if self.critical else r * 3.2
            # stronger glow in attack mode
            gr = QRadialGradient(QPointF(x,y), glow_r)
            gr.setColorAt(0,QColor(col.red(),col.green(),col.blue(),int(a*.65 if self.critical else a*.55)))
            gr.setColorAt(1,QColor(col.red(),col.green(),col.blue(),0))
            p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x,y), glow_r, glow_r)
            core_r = r * 1.6 if self.critical else r
            p.setBrush(QBrush(col)); p.drawEllipse(QPointF(x,y), core_r, core_r)

    def _block_badge(self, p, s, c1, c2, e):
        mx, my = self._bz(0.5, s, c1, c2, e)
        gr = QRadialGradient(QPointF(mx,my), 30)
        gr.setColorAt(0,QColor(255,50,50,80)); gr.setColorAt(1,QColor(255,50,50,0))
        p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(mx,my), 30, 30)
        p.setBrush(QBrush(QColor(180,0,0,215)))
        p.setPen(QPen(QColor(255,80,80), 1.5))
        p.drawRoundedRect(QRectF(mx-34,my-14,68,28), 9, 9)
        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255,200,200)))
        p.drawText(QRectF(mx-34,my-14,68,28), Qt.AlignmentFlag.AlignCenter, "⛔ BLOCKED")

    def _site(self, p, cx, cy):
        ag = QRadialGradient(QPointF(cx,cy), 33)
        ag.setColorAt(0,QColor(230,195,162)); ag.setColorAt(.6,QColor(210,176,146)); ag.setColorAt(1,QColor(188,152,122))
        p.setBrush(QBrush(ag)); p.setPen(QPen(QColor(168,132,102), 1))
        p.drawEllipse(QPointF(cx,cy), 33, 33)
        p.setPen(QPen(QColor(158,122,96,55), 0.5))
        for i in range(-28,30,5):
            p.drawLine(int(cx+i),int(cy-28),int(cx+i),int(cy+28))
            p.drawLine(int(cx-28),int(cy+i),int(cx+28),int(cy+i))
        hg = QRadialGradient(QPointF(cx-3,cy-3), 16)
        hg.setColorAt(0,QColor(238,244,255)); hg.setColorAt(1,QColor(188,204,224))
        p.setBrush(QBrush(hg)); p.setPen(QPen(QColor(158,174,194), 1.5))
        p.drawEllipse(QPointF(cx,cy), 16, 16)
        lc = QColor(255,50,50) if self.critical else QColor(80,160,255)
        p.setPen(Qt.PenStyle.NoPen)
        for angle in [-35,35]:
            rad = math.radians(angle)
            lx = cx+10*math.cos(rad); ly = cy-10*math.sin(rad)-4
            lg = QRadialGradient(QPointF(lx,ly), 4)
            lg.setColorAt(0,QColor(lc.red(),lc.green(),lc.blue(),220))
            lg.setColorAt(1,QColor(lc.red(),lc.green(),lc.blue(),0))
            p.setBrush(QBrush(lg)); p.drawEllipse(QPointF(lx,ly), 4, 4)
            p.setBrush(QBrush(lc.lighter(140))); p.drawEllipse(QPointF(lx,ly), 2, 2)
        p.setBrush(QBrush(QColor(200,215,230)))
        p.setPen(QPen(QColor(140,155,170), 1))
        p.drawEllipse(QPointF(cx,cy), 4, 4)
        pa = int(55*(0.5+0.5*math.sin(self._phase)))
        pc = QColor(255,50,50) if self.critical else QColor(31,179,163)
        for rm in [1.4,1.9,2.5]:
            r = 33*rm
            p.setPen(QPen(QColor(pc.red(),pc.green(),pc.blue(),int(pa/rm)), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx,cy), r, r)
        p.setBrush(QBrush(QColor(178,193,210)))
        p.setPen(QPen(QColor(128,143,160), 1))
        p.drawEllipse(QPointF(cx-14,cy-6), 5, 5)

    def _pump(self, p, x, y, w, h):
        sg = QRadialGradient(QPointF(x+w/2,y+h), h*.65)
        sg.setColorAt(0,QColor(0,0,0,75)); sg.setColorAt(1,QColor(0,0,0,0))
        p.setBrush(QBrush(sg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(x-10,y+h-8,w+20,28))
        bg = QLinearGradient(x,y,x+w,y+h)
        bg.setColorAt(0,QColor(54,56,62)); bg.setColorAt(.3,QColor(40,42,48))
        bg.setColorAt(.7,QColor(30,32,38)); bg.setColorAt(1,QColor(22,24,30))
        p.setBrush(QBrush(bg)); p.setPen(QPen(QColor(66,70,80), 1.5))
        p.drawRoundedRect(QRectF(x,y,w,h), 12, 12)
        sx,sy,sw,sh = x+7,y+18,w-14,64
        sg2 = QLinearGradient(sx,sy,sx,sy+sh)
        sg2.setColorAt(0,QColor(8,22,36)); sg2.setColorAt(1,QColor(5,14,24))
        p.setBrush(QBrush(sg2)); p.setPen(QPen(QColor(0,105,155), 1.2))
        p.drawRoundedRect(QRectF(sx,sy,sw,sh), 5, 5)
        p.setFont(QFont("Courier New",6,QFont.Weight.Bold))
        p.setPen(QPen(QColor(155,178,198)))
        p.drawText(QRectF(sx+2,sy+3,sw-4,10), Qt.AlignmentFlag.AlignRight,
                   datetime.now().strftime("%H:%M"))
        sc = QColor(255,50,50) if self.critical else QColor(0,200,80)
        shield = QPainterPath()
        bx,by_ = sx+5,sy+7
        shield.moveTo(bx+6,by_); shield.lineTo(bx+12,by_+4)
        shield.lineTo(bx+12,by_+10)
        shield.quadTo(bx+6,by_+16,bx+6,by_+16)
        shield.quadTo(bx,by_+10,bx,by_+10)
        shield.lineTo(bx,by_+4); shield.closeSubpath()
        p.setBrush(QBrush(sc)); p.setPen(Qt.PenStyle.NoPen); p.drawPath(shield)
        vc = QColor(255,80,80) if self.critical else QColor(0,220,100)
        p.setFont(QFont("Courier New",13,QFont.Weight.Bold))
        p.setPen(QPen(vc))
        p.drawText(QRectF(sx,sy+22,sw,22), Qt.AlignmentFlag.AlignCenter,
                   f"{self.dose:.1f}")
        p.setFont(QFont("Courier New",6))
        p.setPen(QPen(QColor(100,140,162)))
        p.drawText(QRectF(sx,sy+43,sw,10), Qt.AlignmentFlag.AlignCenter,"U  Delivery")
        p.setFont(QFont("Courier New",6,QFont.Weight.Bold))
        p.setPen(QPen(QColor(0,180,255)))
        p.drawText(QRectF(sx,sy+54,sw,10), Qt.AlignmentFlag.AlignCenter,
                   f"{max(0.0,self.dose/60):.3f} U/min")
        gg = QLinearGradient(sx,sy,sx+sw,sy+sh*.5)
        gg.setColorAt(0,QColor(255,255,255,20)); gg.setColorAt(1,QColor(255,255,255,0))
        p.setBrush(QBrush(gg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(sx,sy,sw,sh*.5), 5, 5)
        ly = y+9
        for lxo, ok_c, bad_c, anim in [(18,QColor(0,255,80),QColor(255,60,60),False),
                                        (30,QColor(255,165,0,85),QColor(255,80,80),True)]:
            if anim:
                a = int(180*(0.5+0.5*math.sin(self._phase*2))) if (self.warning or self.critical) else 80
                lc = QColor(bad_c.red(),bad_c.green(),bad_c.blue(),a) if self.critical else QColor(ok_c.red(),ok_c.green(),ok_c.blue(),a)
            else:
                lc = bad_c if self.critical else ok_c
            lg = QRadialGradient(QPointF(x+lxo,ly), 5)
            lg.setColorAt(0,lc); lg.setColorAt(1,QColor(0,0,0,0))
            p.setBrush(QBrush(lg)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x+lxo,ly), 4, 4)
            p.setBrush(QBrush(lc.lighter(140))); p.drawEllipse(QPointF(x+lxo,ly), 2, 2)
        dx,dy_,dr = x+w//2,y+h-40,14
        dpg = QRadialGradient(QPointF(dx-2,dy_-2), dr+6)
        dpg.setColorAt(0,QColor(66,72,88)); dpg.setColorAt(1,QColor(42,46,57))
        p.setBrush(QBrush(dpg)); p.setPen(QPen(QColor(82,87,102), 1))
        p.drawEllipse(QPointF(dx,dy_), dr+5, dr+5)
        arm,aw = 9,6
        p.setBrush(QBrush(QColor(56,62,74))); p.setPen(QPen(QColor(76,82,97), 1))
        for ddx,ddy in [(0,-arm),(0,arm),(-arm,0),(arm,0)]:
            p.drawRoundedRect(QRectF(dx+ddx-aw//2,dy_+ddy-aw//2,aw,aw), 2, 2)
        cg = QRadialGradient(QPointF(dx-1,dy_-1), 6)
        cg.setColorAt(0,QColor(76,82,100)); cg.setColorAt(1,QColor(50,54,67))
        p.setBrush(QBrush(cg)); p.setPen(QPen(QColor(92,97,117), 1))
        p.drawEllipse(QPointF(dx,dy_), 6, 6)
        p.setPen(QPen(QColor(142,152,172), 1)); p.setFont(QFont("Arial",5))
        for txt,ddx,ddy in [("▲",0,-arm),("▼",0,arm),("◀",-arm,0),("▶",arm,0)]:
            p.drawText(QRectF(dx+ddx-5,dy_+ddy-4,10,8), Qt.AlignmentFlag.AlignCenter, txt)
        p.setBrush(QBrush(QColor(56,62,74))); p.setPen(QPen(QColor(82,87,102), 1))
        p.drawRoundedRect(QRectF(x+w-4,y+55,8,22), 3, 3)
        clg = QLinearGradient(x+w+1,y+20,x+w+11,y+20)
        clg.setColorAt(0,QColor(62,67,80)); clg.setColorAt(1,QColor(42,46,57))
        p.setBrush(QBrush(clg)); p.setPen(QPen(QColor(77,82,97), 1))
        p.drawRoundedRect(QRectF(x+w+1,y+20,9,90), 4, 4)
        p.setFont(QFont("Arial",5,QFont.Weight.Bold))
        p.setPen(QPen(QColor(92,102,122)))
        p.drawText(QRectF(x+4,y+h-14,w-8,12), Qt.AlignmentFlag.AlignCenter,"SmartPump X2")

    def _port(self, p, cx, ty):
        p.setBrush(QBrush(QColor(62,67,80))); p.setPen(QPen(QColor(82,90,107), 1.5))
        p.drawRoundedRect(QRectF(cx-7,ty-17,14,19), 3, 3)
        p.setBrush(QBrush(QColor(182,197,212))); p.setPen(QPen(QColor(142,157,172), 1))
        p.drawEllipse(QPointF(cx,ty-17), 4, 4)



# ══════════════════════════════════════════════════════════════════════════════
#  ATTACK BANNER OVERLAY  — slides in from top
# ══════════════════════════════════════════════════════════════════════════════
class AttackBanner(QLabel):
    """Full-width animated banner: slides from top and flashes."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(54)
        self.hide()
        self._slide_anim  = None
        self._flash_timer = None
        self._flash_state = False
        self._mode        = "attack"   # "attack" | "blocked"

    def _style(self, flash=False):
        if self._mode == "attack":
            bg  = "#cc0000" if flash else "#880000"
            fg  = "#ffffff"
            bdr = "#ff4444"
        else:
            bg  = "#995500" if flash else "#663300"
            fg  = "#ffdd88"
            bdr = "#ffaa00"
        self.setStyleSheet(
            f"background:{bg};color:{fg};font-size:22px;font-weight:bold;"
            f"font-family:'Courier New';border-bottom:3px solid {bdr};"
            f"letter-spacing:3px;")

    def show_attack(self):
        self._mode = "attack"
        self.setText("🚨  ATTACK DETECTED  🚨  SYSTEM COMPROMISED  🚨")
        self._launch()

    def show_blocked(self):
        self._mode = "blocked"
        self.setText("🛡  ATTACK INTERCEPTED  —  MedShield AI BLOCKED THREAT  🛡")
        self._launch()

    def _launch(self):
        self._style(False)
        self.show()
        self.raise_()
        w = self.parent().width()
        self.setGeometry(0, -54, w, 54)
        if self._slide_anim:
            self._slide_anim.stop()
        a = QPropertyAnimation(self, b"geometry", self)
        a.setDuration(380)
        a.setStartValue(QRect(0, -54, w, 54))
        a.setEndValue(QRect(0, 0,   w, 54))
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()
        self._slide_anim = a
        # flash loop
        if self._flash_timer:
            self._flash_timer.stop()
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._do_flash)
        self._flash_timer.start(220)
        # auto-hide after 4.5 s
        QTimer.singleShot(4500, self._hide_banner)

    def _do_flash(self):
        self._flash_state = not self._flash_state
        self._style(self._flash_state)

    def _hide_banner(self):
        if self._flash_timer:
            self._flash_timer.stop()
        if self._slide_anim:
            self._slide_anim.stop()
        w = self.parent().width()
        a = QPropertyAnimation(self, b"geometry", self)
        a.setDuration(300)
        a.setStartValue(QRect(0, 0,   w, 54))
        a.setEndValue(QRect(0, -54, w, 54))
        a.setEasingCurve(QEasingCurve.Type.InCubic)
        a.finished.connect(self.hide)
        a.start()
        self._slide_anim = a


# ══════════════════════════════════════════════════════════════════════════════
#  NETWORK POLLER — polls Flask every 1.5s
# ══════════════════════════════════════════════════════════════════════════════
class StatePoller(QThread):
    state_ready = pyqtSignal(dict)
    medshield_status = pyqtSignal(bool)  # True = Laptop 3 online

    def run(self):
        while True:
            # poll pump state
            try:
                r = requests.get(f"{PUMP_URL}/status", timeout=2)
                if r.ok: self.state_ready.emit(r.json())
            except: pass
            # check MedShield Laptop 3 online
            try:
                r2 = requests.get(f"{MEDSHIELD_URL}/ping", timeout=1)
                self.medshield_status.emit(r2.ok)
            except:
                self.medshield_status.emit(False)
            self.msleep(500)


# ══════════════════════════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _card(title=""):
    f = QFrame()
    f.setStyleSheet(f"QFrame{{background:{BG_CARD};border-radius:10px;border:1px solid {BORDER};}}")
    vl = QVBoxLayout(f); vl.setContentsMargins(12,10,12,10); vl.setSpacing(6)
    if title:
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{CYAN};font-size:10px;font-weight:bold;"
                          f"letter-spacing:1.4px;background:transparent;")
        vl.addWidget(lbl)
    return f, vl

def _lbl(text, col=TDIM, sz=11, bold=False):
    w = QLabel(text)
    w.setStyleSheet(f"color:{col};font-size:{sz}px;"
                    f"font-weight:{'bold' if bold else 'normal'};background:transparent;")
    return w

def _btn(text, bg="#005faa", fg="white", border=None, sz=12):
    b = f"border:2px solid {border};" if border else "border:none;"
    btn = QPushButton(text)
    # Font set natively rather than through QSS font-size -- QSS-driven
    # fonts on QPushButton go through a different Qt code path than QLabel
    # and, on this setup, come out of a maximize-state transition with the
    # label rendered at near-zero height (readable border, unreadable
    # text); a directly-set QFont isn't affected the same way.
    btn.setFont(QFont("Segoe UI", sz, QFont.Weight.Bold))
    btn.setStyleSheet(f"""
        QPushButton{{background:{bg};color:{fg};
            padding:8px 10px;border-radius:7px;{b}}}
        QPushButton:hover{{background:{QColor(bg).lighter(130).name()};}}
    """)
    return btn


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class MedShieldDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MedShield AI — Insulin Pump Security System")
        self.setGeometry(20, 20, 1720, 1020)
        self.setStyleSheet(f"QMainWindow,QWidget{{background:{BG_MAIN};color:white;}}")

        self.engine         = GlucoseEngine()
        self.current_dose   = 2.0
        self.reservoir      = 120.0
        self.battery        = 87.0
        self.risk_score     = 0.18
        self.trust_score    = 0.92
        self.medshield_on   = True
        self.medshield_l3   = False   # is Laptop 3 online?
        self.attack_active  = False
        self.commands       = [
            (datetime.now().strftime("%H:%M:%S"), "CGM_001",    "Glucose Reading","132 mg/dL","ALLOWED"),
            (datetime.now().strftime("%H:%M:%S"), "DrApp_A",    "Set Basal",      "1.20 U/hr","ALLOWED"),
            (datetime.now().strftime("%H:%M:%S"), "PatientApp", "Bolus",          "2.0 U",    "ALLOWED"),
        ]
        self.glucose_hist = [132.0] * 80
        self.dose_hist    = [2.0]   * 80
        self.risk_hist    = [0.18]  * 80

        self._build_ui()

        # Attack banner overlay (sits on top of root widget)
        self._banner = AttackBanner(self.centralWidget())

        # Border flash state
        self._border_flash       = False
        self._border_flash_timer = None

        # Timers
        self._sim_t = QTimer(self); self._sim_t.timeout.connect(self._tick); self._sim_t.start(1000)
        self._clk_t = QTimer(self)
        self._clk_t.timeout.connect(lambda: self._time_lbl.setText(
            datetime.now().strftime("%H:%M:%S")))
        self._clk_t.start(1000)

        # Network
        self._poller = StatePoller()
        self._poller.state_ready.connect(self._on_flask_state)
        self._poller.medshield_status.connect(self._on_medshield_status)
        self._poller.start()

        # Auto-start simulation
        threading.Thread(target=lambda: self._safe_post(f"{PUMP_URL}/simulate_normal"),
                         daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────
    def _safe_post(self, url, data=None):
        try: requests.post(url, json=data, timeout=3)
        except: pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "_banner"):
            w = self.centralWidget().width()
            if self._banner.isVisible():
                self._banner.setGeometry(0, 0, w, 54)

    def changeEvent(self, e):
        super().changeEvent(e)
        # The actual Qt.WindowMaximized state transition corrupts every
        # QSS-styled button's text (rendered at near-zero height -- border
        # fine, label unreadable) on this setup, confirmed to be specific
        # to that window state and not just "a big window": a plain
        # resize() to an equal or larger size renders every button
        # perfectly. Six different in-place remedies (style repolish, full
        # stylesheet clear+reapply, native QFont instead of QSS font-size,
        # a pinned HiDPI rounding policy, hide/show to force a backing-
        # store rebuild) all produced the exact same corrupted pixels,
        # which means whatever breaks it isn't reachable from here after
        # the fact. So: never actually enter that state -- catch the
        # transition and manually fill the screen instead, which gives the
        # same full-screen result through the code path already proven to
        # render correctly.
        if e.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMaximized:
                QTimer.singleShot(0, self._fill_screen_instead_of_maximize)

    def _fill_screen_instead_of_maximize(self):
        self.setWindowState(Qt.WindowState.WindowNoState)
        screen = self.screen() or QApplication.primaryScreen()
        self.setGeometry(screen.availableGeometry())

    def _start_border_flash(self):
        self._border_flash = True
        if self._border_flash_timer:
            return
        t = QTimer(self)
        t.timeout.connect(self._toggle_border)
        t.start(250)
        self._border_flash_timer = t

    def _toggle_border(self):
        self._border_flash_state = getattr(self, "_border_flash_state", False)
        self._border_flash_state = not self._border_flash_state
        col = RED if self._border_flash_state else "#550000"
        self.setStyleSheet(
            f"QMainWindow,QWidget{{background:{BG_MAIN};color:white;}}"
            f"QMainWindow{{border:4px solid {col};}}")

    def _stop_border_flash(self):
        self._border_flash = False
        if self._border_flash_timer:
            self._border_flash_timer.stop()
            self._border_flash_timer = None
        self.setStyleSheet(
            f"QMainWindow,QWidget{{background:{BG_MAIN};color:white;}}")

    # ─── BUILD UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        vb = QVBoxLayout(root); vb.setContentsMargins(13,13,13,13); vb.setSpacing(9)
        self.setCentralWidget(root)
        self._build_header(vb)
        mid = QHBoxLayout(); mid.setSpacing(9)
        self._build_left(mid); self._build_center(mid); self._build_right(mid)
        vb.addLayout(mid, stretch=3)
        self._build_graphs(vb)

    # ── HEADER ───────────────────────────────────────────────────────────
    def _build_header(self, parent):
        hdr = QFrame()
        hdr.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        row = QHBoxLayout(hdr); row.setContentsMargins(20,11,20,11)

        tl = QVBoxLayout()
        tl.addWidget(_lbl("🛡️  MedShield AI", CYAN, 26, True))
        tl.addWidget(_lbl("REAL-TIME INSULIN PUMP SECURITY SYSTEM  |  Laptop 1", MUTED, 10))
        row.addLayout(tl); row.addSpacing(16)

        self._sys_card   = self._hdr_kv(row, "SYSTEM",       "PROTECTED ✓",   GREEN,  "#0a2e1e")
        self._risk_card  = self._hdr_kv(row, "RISK SCORE",   "0.18",          CYAN,   "#0a2030")
        self._trust_card = self._hdr_kv(row, "TRUST SCORE",  "0.92",          GREEN,  "#0a2e1e")
        self._gluc_card  = self._hdr_kv(row, "GLUCOSE",      "132 mg/dL",     GREEN,  "#0a2e1e")
        self._blk_card   = self._hdr_kv(row, "BLOCKS TODAY", "0",             ORANGE, "#2a1800")
        self._l3_card    = self._hdr_kv(row, "LAPTOP 3",     "OFFLINE",       MUTED,  "#1a1a1a")

        row.addStretch()

        # MedShield toggle
        self._ms_btn = QPushButton("MedShield: ON")
        self._ms_btn.setCheckable(True); self._ms_btn.setChecked(True)
        self._ms_btn.setStyleSheet(f"""
            QPushButton{{background:#003a1a;color:{GREEN};font-size:12px;
                font-weight:bold;padding:8px 16px;border-radius:8px;
                border:2px solid {GREEN};}}
            QPushButton:!checked{{background:#3a0000;color:{RED};border-color:{RED};}}
        """)
        self._ms_btn.toggled.connect(self._toggle_ms)
        row.addWidget(self._ms_btn); row.addSpacing(12)

        self._time_lbl = _lbl(datetime.now().strftime("%H:%M:%S"), TDIM, 15)
        self._time_lbl.setStyleSheet(
            f"color:{TDIM};font-size:15px;font-family:'Courier New';background:transparent;")
        row.addWidget(self._time_lbl)
        parent.addWidget(hdr)

    def _hdr_kv(self, layout, title, value, col, bg):
        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{bg};border-radius:8px;padding:4px;}}")
        cl = QVBoxLayout(card); cl.setContentsMargins(13,6,13,6)
        cl.addWidget(_lbl(title, MUTED, 9, True))
        vl = _lbl(value, col, 16, True); cl.addWidget(vl)
        layout.addWidget(card); layout.addSpacing(5)
        return vl

    # ── LEFT ─────────────────────────────────────────────────────────────
    def _build_left(self, parent):
        col = QFrame()
        col.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        vl = QVBoxLayout(col); vl.setContentsMargins(12,12,12,12); vl.setSpacing(8)

        pi, pil = _card("PUMP INFORMATION")
        grid = QGridLayout(); grid.setSpacing(4)
        self._pump_rows = {}
        for i,(k,v) in enumerate([
            ("Device ID",  DEVICE_ID),
            ("MAC",        DEVICE_MAC),
            ("Reservoir",  f"{self.reservoir:.0f} U"),
            ("Battery",    f"{self.battery:.0f}%"),
            ("Basal Rate", "1.20 U/hr"),
            ("Status",     "Normal"),
            ("Connection", "BLE + WiFi"),
        ]):
            grid.addWidget(_lbl(k, MUTED, 10), i, 0)
            rv = _lbl(v, TDIM, 10, True)
            self._pump_rows[k] = rv
            grid.addWidget(rv, i, 1)
        pil.addLayout(grid); vl.addWidget(pi)

        gi, gil = _card("BLOOD GLUCOSE")
        gil.addWidget(_lbl("Current Reading", MUTED, 10))
        self._gluc_big = QLabel("132")
        self._gluc_big.setStyleSheet(
            f"color:{GREEN};font-size:52px;font-weight:bold;"
            f"font-family:'Courier New';background:transparent;")
        gil.addWidget(self._gluc_big)
        r2 = QHBoxLayout()
        r2.addWidget(_lbl("mg/dL", MUTED, 12))
        self._gluc_st = _lbl("NORMAL", GREEN, 12, True)
        r2.addWidget(self._gluc_st); r2.addStretch()
        gil.addLayout(r2); vl.addWidget(gi)

        di, dil = _card("CURRENT DOSE")
        self._dose_big = QLabel("2.0 U")
        self._dose_big.setStyleSheet(
            f"color:{CYAN};font-size:36px;font-weight:bold;"
            f"font-family:'Courier New';background:transparent;")
        dil.addWidget(self._dose_big)
        self._flow_lbl = _lbl("Flow: 0.120 U/s", MUTED, 10)
        dil.addWidget(self._flow_lbl); vl.addWidget(di)

        qc, qcl = _card("QUICK CONTROLS")
        for txt, fn, bg, bd in [
            ("Deliver 2U Bolus",  self._bolus,  "#004488", "#0088ff"),
            ("Start Simulation",  self._start_sim, "#004020","#008040"),
            ("Stop Simulation",   self._stop_sim,  "#2a1a00","#885500"),
            ("Reset Pump",        self._reset,  "#1e1530", "#4a3060"),
        ]:
            b = _btn(txt, bg=bg, border=bd, sz=11)
            b.clicked.connect(fn); qcl.addWidget(b)
        vl.addWidget(qc)
        vl.addStretch()
        parent.addWidget(col, stretch=1)

    # ── CENTER ────────────────────────────────────────────────────────────
    def _build_center(self, parent):
        col = QFrame()
        col.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        vl = QVBoxLayout(col); vl.setContentsMargins(13,13,13,13); vl.setSpacing(8)

        vl.addWidget(_lbl("LIVE INSULIN DELIVERY — REAL-TIME ANIMATION", CYAN, 12, True))

        pipe = QHBoxLayout(); pipe.setSpacing(3)
        for ic, lb in [("🔵","CGM"),("🧠","AI ENGINE"),("📟","PUMP"),("🩺","PATIENT")]:
            wf, wl = _card()
            wl.addWidget(_lbl(ic, sz=22), 0, Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(_lbl(lb, MUTED, 8, True), 0, Qt.AlignmentFlag.AlignCenter)
            pipe.addWidget(wf)
            if lb != "PATIENT":
                pipe.addWidget(_lbl("→", CYAN, 16, True), 0, Qt.AlignmentFlag.AlignCenter)
        vl.addLayout(pipe)

        self._scene = PumpPatientScene()
        vl.addWidget(self._scene)

        ss, ssl = _card()
        sr = QHBoxLayout(); sr.addStretch()
        sr.addWidget(_lbl("Patient:", MUTED, 12))
        sr.addSpacing(8)
        self._pt_st = _lbl("STABLE ✓", GREEN, 14, True)
        sr.addWidget(self._pt_st); sr.addStretch()
        ssl.addLayout(sr); vl.addWidget(ss)

        # SHAP explanation
        sb, sbl = _card("DETECTION REASONING  ·  Explainable AI (SHAP + LIME)")
        self._shap_lbl = QLabel(
            "All systems normal. No threats detected.\n"
            "Monitoring BLE + WiFi + MQTT channels.")
        self._shap_lbl.setStyleSheet(
            f"color:{TDIM};font-size:11px;font-family:'Courier New';"
            f"background:transparent;")
        self._shap_lbl.setWordWrap(True)
        sbl.addWidget(self._shap_lbl); vl.addWidget(sb)

        # Command history
        ch, chl = _card("COMMAND HISTORY  (last 20)")
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(5)
        self._tbl.setHorizontalHeaderLabels(["TIME","SOURCE","COMMAND","VALUE","STATUS"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.setMaximumHeight(148)
        self._tbl.setStyleSheet(f"""
            QTableWidget{{background:{BG_MAIN};color:{TDIM};
                gridline-color:{BORDER};border:none;font-size:10px;}}
            QHeaderView::section{{background:{BG_PANEL};color:{CYAN};
                padding:4px;border:none;font-size:10px;font-weight:bold;}}
            QTableWidget::item{{padding:3px;}}
        """)
        self._refresh_table(); chl.addWidget(self._tbl); vl.addWidget(ch)
        parent.addWidget(col, stretch=3)

    # ── RIGHT ─────────────────────────────────────────────────────────────
    def _build_right(self, parent):
        col = QFrame()
        col.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        vl = QVBoxLayout(col); vl.setContentsMargins(12,12,12,12); vl.setSpacing(7)

        af, afl = _card("ATTACK SIMULATION  ·  Laptop 2 → here")
        afl.addWidget(_lbl("Target: MedShield OFF → Laptop 1 direct", MUTED, 9))
        afl.addWidget(_lbl("Target: MedShield ON → via Laptop 3", MUTED, 9))
        for atk in ATTACKS:
            b = _btn(atk["name"], bg="#2a0808", fg="#ff8888", border="#5a1818", sz=11)
            b.clicked.connect(lambda _, a=atk: self._fire_attack(a))
            afl.addWidget(b)
        stop = _btn("Stop All Attacks", bg="#082808", fg=GREEN, border="#185818")
        stop.clicked.connect(self._stop_attack); afl.addWidget(stop)
        vl.addWidget(af)

        lf, lfl = _card("DEFENSE PIPELINE  ·  9 layers")
        self._layer_ws = []
        for tag, name, tech in LAYERS:
            row = QHBoxLayout(); row.setSpacing(5)
            tg = QLabel(tag)
            tg.setFixedWidth(32)
            tg.setStyleSheet(f"color:#050a12;background:{GREEN};font-size:8px;"
                             f"font-weight:bold;border-radius:4px;padding:2px 3px;")
            tg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(tg)
            info = QVBoxLayout(); info.setSpacing(0)
            nl = _lbl(name, GREEN, 10, True)
            tl = _lbl(tech, MUTED, 8)
            info.addWidget(nl); info.addWidget(tl); row.addLayout(info)
            st = _lbl("●", GREEN, 12, True); st.setFixedWidth(22)
            row.addWidget(st)
            lfl.addLayout(row)
            self._layer_ws.append((tg, nl, st))
        vl.addWidget(lf)

        ff, ffl = _card("FORENSIC LOG")
        self._forensic = QLabel("No incidents logged.")
        self._forensic.setStyleSheet(
            f"color:{MUTED};font-size:9px;font-family:'Courier New';"
            f"background:transparent;")
        self._forensic.setWordWrap(True)
        ffl.addWidget(self._forensic); vl.addWidget(ff)
        vl.addStretch()
        parent.addWidget(col, stretch=1)

    # ── GRAPHS ────────────────────────────────────────────────────────────
    def _build_graphs(self, parent):
        btm = QFrame()
        btm.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        row = QHBoxLayout(btm); row.setContentsMargins(12,10,12,10); row.setSpacing(10)
        pg.setConfigOption("background", BG_PANEL)
        pg.setConfigOption("foreground", MUTED)
        self._gc = self._graph(row, "GLUCOSE TREND (mg/dL)", GREEN)
        self._dc = self._graph(row, "DOSE TREND (U)",        CYAN)
        self._rc = self._graph(row, "RISK SCORE TREND",      RED)
        parent.addWidget(btm, stretch=2)

    def _graph(self, layout, title, color):
        pw = pg.PlotWidget(title=title)
        pw.setBackground(BG_PANEL); pw.showGrid(x=True,y=True,alpha=0.15)
        pw.setMenuEnabled(False)
        c = pw.plot(pen=pg.mkPen(color=color, width=2))
        layout.addWidget(pw); return c

    # ─────────────────────────────────────────────────────────────────────
    #  SIMULATION TICK
    # ─────────────────────────────────────────────────────────────────────
    def _tick(self):
        self.engine.tick()
        g, (s, sc) = self.engine.current, self.engine.status()
        flow = self._scene._speed()

        # ── glucose display always updates ────────────────────────────────
        self._gluc_big.setText(f"{g:.0f}")
        self._gluc_big.setStyleSheet(
            f"color:{sc};font-size:52px;font-weight:bold;"
            f"font-family:'Courier New';background:transparent;")
        self._gluc_st.setText(s)
        self._gluc_st.setStyleSheet(
            f"color:{sc};font-size:12px;font-weight:bold;background:transparent;")
        self._gluc_card.setText(f"{g:.0f} mg/dL")
        self._flow_lbl.setText(f"Flow: {flow:.3f} U/s")

        # ── only update dose display if NOT currently in attack state ─────
        is_attack = self.current_dose > 50
        if not is_attack:
            self._dose_big.setText(f"{self.current_dose:.1f} U")
            self._dose_big.setStyleSheet(
                f"color:{CYAN};font-size:36px;font-weight:bold;"
                f"font-family:'Courier New';background:transparent;")
            self._pt_st.setText("STABLE ✓")
            self._pt_st.setStyleSheet(
                f"color:{GREEN};font-size:14px;font-weight:bold;background:transparent;")
        else:
            # attack is active — keep showing the attack values
            dose_col = RED if self.current_dose >= 200 else ORANGE
            self._dose_big.setStyleSheet(
                f"color:{dose_col};font-size:36px;font-weight:bold;"
                f"font-family:'Courier New';background:transparent;")

        # ── risk + trust ──────────────────────────────────────────────────
        self._risk_card.setText(f"{self.risk_score:.2f}")
        self._trust_card.setText(f"{self.trust_score:.2f}")

        # ── reservoir ─────────────────────────────────────────────────────
        self.reservoir = max(0.0, self.reservoir - self.current_dose / 3600)
        self._pump_rows["Reservoir"].setText(f"{self.reservoir:.1f} U")

        # ── graph history ─────────────────────────────────────────────────
        self.glucose_hist.pop(0); self.glucose_hist.append(g)
        self.dose_hist.pop(0);    self.dose_hist.append(self.current_dose)
        self.risk_hist.pop(0);    self.risk_hist.append(self.risk_score)
        xs = list(range(80))
        self._gc.setData(xs, self.glucose_hist)
        self._dc.setData(xs, self.dose_hist)
        self._rc.setData(xs, self.risk_hist)

    # ─────────────────────────────────────────────────────────────────────
    #  FLASK STATE — from poller
    # ─────────────────────────────────────────────────────────────────────
    def _on_flask_state(self, state):
        dose        = float(state.get("current_dose",   self.current_dose))
        blocked     = bool(state.get("medshield_blocked", False))
        compromised = bool(state.get("is_compromised",  False))
        glucose     = float(state.get("glucose_level",  self.engine.current))

        # ── sync glucose engine with real flask state ─────────────────────
        self.engine.current = glucose

        # ── attack came in from Laptop 2 — inject glucose effect ─────────
        if compromised and dose > 50:
            self.engine.inject(dose * 0.3)

        # ── always sync dose + scene ──────────────────────────────────────
        self.current_dose = dose
        self._scene.set_state(dose, blocked=blocked)

        # ── update dose display immediately ──────────────────────────────
        dose_col = RED if dose > 50 else (YELLOW if dose > 15 else CYAN)
        self._dose_big.setText(f"{dose:.1f} U")
        self._dose_big.setStyleSheet(
            f"color:{dose_col};font-size:36px;font-weight:bold;"
            f"font-family:'Courier New';background:transparent;")

        # ── risk + trust scores ───────────────────────────────────────────
        if compromised:
            self.risk_score  = 0.99
            self.trust_score = max(0.0, self.trust_score - 0.2)
        elif blocked:
            self.risk_score  = 0.97
            self.trust_score = max(0.0, self.trust_score - 0.1)
        else:
            self.risk_score  = max(0.18, self.risk_score - 0.05)

        # ── push to header cards ──────────────────────────────────────────
        self._risk_card.setText(f"{self.risk_score:.2f}")
        self._trust_card.setText(f"{self.trust_score:.2f}")
        risk_col = RED if self.risk_score > 0.7 else (YELLOW if self.risk_score > 0.4 else CYAN)
        self._risk_card.setStyleSheet(
            f"color:{risk_col};font-size:16px;font-weight:bold;background:transparent;")

        # ── show the right UI state ───────────────────────────────────────
        if blocked:
            self._show_blocked(state)
        elif compromised:
            self._show_compromised(state)
        else:
            # back to safe — reset UI if it was previously in alert
            if hasattr(self, "_last_was_attack") and self._last_was_attack:
                self._stop_border_flash()
                self._sys_card.setText("PROTECTED ✓")
                self._sys_card.setStyleSheet(
                    f"color:{GREEN};font-size:16px;font-weight:bold;background:transparent;")
                self._set_layers("ok")

        self._last_was_attack = compromised or blocked

        # ── blocked count badge ───────────────────────────────────────────
        bc = int(state.get("blocked_count", 0))
        self._blk_card.setText(str(bc))
        if bc > 0:
            self._blk_card.setStyleSheet(
                f"color:{ORANGE};font-size:16px;font-weight:bold;background:transparent;")

        # ── add incoming command to history table ─────────────────────────
        history = state.get("dose_history", [])
        if history:
            latest = history[0]
            src    = latest.get("source",    "?")
            units  = latest.get("units",     0)
            ts     = latest.get("timestamp", "--:--:--")
            status = "BLOCKED" if blocked else ("ATTACK" if latest.get("is_attack") else "ALLOWED")
            # only add if it's new (different timestamp from last we saw)
            if ts != getattr(self, "_last_cmd_ts", ""):
                self._last_cmd_ts = ts
                self._add_cmd(src, "Dose Command", f"{units:.1f}U", status)

    def _on_medshield_status(self, online):
        self.medshield_l3 = online
        self._l3_card.setText("ONLINE ✓" if online else "OFFLINE")
        self._l3_card.setStyleSheet(
            f"color:{GREEN if online else MUTED};font-size:16px;"
            f"font-weight:bold;background:transparent;")

    def _show_blocked(self, state):
        reason = state.get("block_reason", "Attack intercepted by MedShield AI")
        # Determine which layer triggered based on reason text
        triggered = None
        for _, name, _ in LAYERS:
            if name.lower() in reason.lower():
                triggered = name
                break
        # ── banner ────────────────────────────────────────────────────────
        self._banner.show_blocked()
        self._stop_border_flash()
        self._sys_card.setText("BLOCKED")
        self._sys_card.setStyleSheet(
            f"color:{ORANGE};font-size:16px;font-weight:bold;background:transparent;")
        self._shap_lbl.setText(reason)
        self._shap_lbl.setStyleSheet(
            f"color:{ORANGE};font-size:11px;font-family:'Courier New';background:transparent;")
        self._set_layers("blocked", triggered_layer=triggered)
        self._forensic.setText(f"[{datetime.now().strftime('%H:%M:%S')}] "
                               f"BLOCKED by MedShield\n{reason}")
        self._forensic.setStyleSheet(
            f"color:{ORANGE};font-size:9px;font-family:'Courier New';background:transparent;")

    def _show_compromised(self, state):
        msg   = state.get("alert_message", "Attack succeeded!")
        dose  = float(state.get("current_dose", 200))
        src   = state.get("last_command_from", "ATTACKER")

        # ── banner + border flash ─────────────────────────────────────────
        self._banner.show_attack()
        self._start_border_flash()

        # ── header ────────────────────────────────────────────────────────
        self._sys_card.setText("COMPROMISED")
        self._sys_card.setStyleSheet(
            f"color:{RED};font-size:16px;font-weight:bold;background:transparent;")

        # ── force scene into attack mode ──────────────────────────────────
        self._scene.set_state(dose, blocked=False)

        # ── patient status cascade ────────────────────────────────────────
        self._pt_st.setText("WARNING")
        self._pt_st.setStyleSheet(
            f"color:{ORANGE};font-size:13px;font-weight:bold;background:transparent;")
        QTimer.singleShot(900,  lambda: self._pt_st.setText("CRITICAL — PATIENT AT RISK") or
                          self._pt_st.setStyleSheet(
            f"color:{RED};font-size:13px;font-weight:bold;background:transparent;"))

        # ── dose display ──────────────────────────────────────────────────
        self._dose_big.setText(f"{dose:.1f} U")
        self._dose_big.setStyleSheet(
            f"color:{RED};font-size:36px;font-weight:bold;"
            f"font-family:'Courier New';background:transparent;")

        # ── SHAP explanation ──────────────────────────────────────────────
        self._shap_lbl.setText(
            f"ATTACK SUCCEEDED — MedShield was OFF\n"
            f"Source  : {src}\n"
            f"Dose    : {dose:.0f} U injected (safe max = 50U)\n"
            f"Impact  : Patient glucose will drop critically\n"
            f"Action  : ENABLE MedShield to prevent this!"
        )
        self._shap_lbl.setStyleSheet(
            f"color:{RED};font-size:11px;font-family:'Courier New';background:transparent;")

        # ── forensic log ──────────────────────────────────────────────────
        self._forensic.setText(
            f"[{datetime.now().strftime('%H:%M:%S')}] ATTACK SUCCEEDED\n"
            f"  Source : {src}\n"
            f"  Units  : {dose:.0f} U\n"
            f"  Result : Pump COMPROMISED\n"
            f"  Status : No protection active"
        )
        self._forensic.setStyleSheet(
            f"color:{RED};font-size:9px;font-family:'Courier New';background:transparent;")

        # ── layers all red ────────────────────────────────────────────────
        self._set_layers("compromised")

    # ─────────────────────────────────────────────────────────────────────
    #  ATTACK ACTIONS
    # ─────────────────────────────────────────────────────────────────────
    def _announce_attack(self, payload, desc):
        """Shared UI feedback for any attack scenario -- banner/labels/risk
        score/command-log row. Returns the URL the caller should POST to."""
        self.attack_active = True

        if self.medshield_on:
            # Route through Laptop 3 (MedShield)
            url = f"{MEDSHIELD_URL}/dose"
            action = "ROUTED → Laptop 3 (MedShield)"
            self._shap_lbl.setText(
                f"Attack sent via MedShield AI (Laptop 3)\n"
                f"Type: {desc}\nWaiting for intercept...")
            self._shap_lbl.setStyleSheet(
                f"color:{YELLOW};font-size:11px;"
                f"font-family:'Courier New';background:transparent;")
            # Launch blocked packet
            self._scene.start_attack_packet(blocked=True)
        else:
            # Route directly to pump
            url = f"{PUMP_URL}/dose"
            action = "DIRECT → Laptop 1 pump"
            self._shap_lbl.setText(
                f"No MedShield active — attack sent directly to pump.\n"
                f"Type: {desc}")
            self._shap_lbl.setStyleSheet(
                f"color:{RED};font-size:11px;"
                f"font-family:'Courier New';background:transparent;")
            # Launch attack packet (not blocked)
            self._scene.start_attack_packet(blocked=False)

        self._add_cmd(payload.get("source","?"), desc,
                      f"{payload.get('units',0):.0f}U", action)
        self.risk_score = 0.95
        return url

    def _fire_attack(self, atk):
        """Dispatches a button click to the right firing pattern -- some
        scenarios need more than one request to reach the layer they're
        meant to demonstrate (a rate-limit flood, or a baseline that has to
        be seeded before a spike against it means anything)."""
        kind = atk["kind"]
        if kind == "burst":
            url = self._announce_attack(atk["payload"], atk["desc"])
            threading.Thread(target=self._fire_burst,
                              args=(url, atk["payload"], atk["count"]), daemon=True).start()
        elif kind == "seed_then_spike":
            url = self._announce_attack(atk["spike_payload"], atk["desc"])
            threading.Thread(target=self._fire_seed_then_spike,
                              args=(url, atk["seed_payload"], atk["seed_count"], atk["spike_payload"]),
                              daemon=True).start()
        else:
            self._attack(atk["payload"], atk["desc"])

    def _attack(self, payload, desc):
        url = self._announce_attack(payload, desc)
        threading.Thread(target=self._safe_post, args=(url, payload), daemon=True).start()

    def _fire_burst(self, url, payload, count):
        """Fires `count` copies of `payload` in quick succession -- e.g. to
        exceed L2's per-minute rate limit, which a single request never can.
        Tight interval so the whole burst (and the demo) stays snappy --
        the 60s rate-limit window doesn't care how fast they arrive."""
        for _ in range(count):
            self._safe_post(url, payload)
            time.sleep(0.02)

    def _fire_seed_then_spike(self, url, seed_payload, seed_count, spike_payload):
        """L5's behaviour baseline only evaluates once a source has 5+ prior
        ALLOWED requests on record, so this seeds a believable baseline with
        small legitimate-looking doses first, then fires the real spike that
        the now-established baseline flags as an outlier. Seed units are
        jittered slightly so the baseline has real (nonzero) variance rather
        than leaning on check_behaviour's zero-stdev fallback. seed_count is
        exactly 5 (the minimum check_behaviour requires) and the intervals
        are kept tight so this reads as one fast sequence in a live demo,
        not a visible pause."""
        base_units = seed_payload["units"]
        for _ in range(seed_count):
            jittered = dict(seed_payload, units=round(base_units + random.uniform(-0.4, 0.4), 1))
            self._safe_post(url, jittered)
            time.sleep(0.06)
        time.sleep(0.05)
        self._safe_post(url, spike_payload)

    def _stop_attack(self):
        self.attack_active = False
        self.risk_score    = 0.18
        self.trust_score   = min(1.0, self.trust_score + 0.05)
        self.current_dose  = 2.0
        self.engine        = GlucoseEngine()
        self._scene.set_state(2.0, blocked=False)
        self._scene.reset_overlays()
        self._stop_border_flash()
        self._set_layers("ok")
        self._sys_card.setText("PROTECTED ✓")
        self._sys_card.setStyleSheet(
            f"color:{GREEN};font-size:16px;font-weight:bold;background:transparent;")
        self._shap_lbl.setText(
            "All systems normal. No threats detected.\n"
            "Monitoring BLE + WiFi + MQTT channels.")
        self._shap_lbl.setStyleSheet(
            f"color:{TDIM};font-size:11px;font-family:'Courier New';background:transparent;")
        self._pt_st.setText("STABLE ✓")
        self._pt_st.setStyleSheet(
            f"color:{GREEN};font-size:14px;font-weight:bold;background:transparent;")
        threading.Thread(target=self._safe_post,
                         args=(f"{PUMP_URL}/reset",), daemon=True).start()

    def _set_layers(self, mode="ok", triggered_layer=None):
        color = GREEN if mode == "ok" else (ORANGE if mode == "blocked" else RED)
        for i, (tg, nl, st) in enumerate(self._layer_ws):
            # If blocked, highlight the triggered layer extra bright
            is_triggered = (mode == "blocked" and triggered_layer is not None
                            and LAYERS[i][1] == triggered_layer)
            if is_triggered:
                tg.setStyleSheet(f"color:#050a12;background:{YELLOW};font-size:8px;"
                                 f"font-weight:bold;border-radius:4px;padding:2px 3px;")
                nl.setStyleSheet(f"color:{YELLOW};font-size:10px;"
                                 f"font-weight:bold;background:transparent;")
                st.setText("●")
                st.setStyleSheet(f"color:{YELLOW};font-size:12px;"
                                 f"font-weight:bold;background:transparent;")
            else:
                tg.setStyleSheet(f"color:#050a12;background:{color};font-size:8px;"
                                 f"font-weight:bold;border-radius:4px;padding:2px 3px;")
                nl.setStyleSheet(f"color:{color};font-size:10px;"
                                 f"font-weight:bold;background:transparent;")
                st.setText("●")
                st.setStyleSheet(f"color:{color};font-size:12px;"
                                 f"font-weight:bold;background:transparent;")

    # ─────────────────────────────────────────────────────────────────────
    #  CONTROLS
    # ─────────────────────────────────────────────────────────────────────
    def _toggle_ms(self, on):
        self.medshield_on = on
        self._ms_btn.setText("MedShield: ON" if on else "MedShield: OFF")
        self._set_layers("ok" if on else "compromised")

    def _bolus(self):
        self.current_dose = 2.0
        self.engine.inject(2.0)
        self._scene.set_state(2.0, blocked=False)
        self._add_cmd("PatientApp", "Bolus Delivered", "2.0U", "ALLOWED")
        threading.Thread(target=self._safe_post, args=(
            f"{PUMP_URL}/dose",
            {"units":2.0,"source":"PatientApp",
             "auth_token":"valid","source_mac":"AA:BB:CC:DD:EE:04"}),
            daemon=True).start()

    def _start_sim(self):
        threading.Thread(target=self._safe_post,
                         args=(f"{PUMP_URL}/simulate_normal",), daemon=True).start()

    def _stop_sim(self):
        threading.Thread(target=self._safe_post,
                         args=(f"{PUMP_URL}/simulate_stop",), daemon=True).start()

    def _reset(self):
        self._stop_attack()
        self.reservoir = 120.0
        self.glucose_hist = [132.0]*80
        self.dose_hist    = [2.0]*80
        self.risk_hist    = [0.18]*80
        self._pump_rows["Reservoir"].setText("120.0 U")
        self._forensic.setText("No incidents logged.")
        self._forensic.setStyleSheet(
            f"color:{MUTED};font-size:9px;font-family:'Courier New';background:transparent;")
        self.commands = [(datetime.now().strftime("%H:%M:%S"),
                          "SYSTEM","Pump Reset","--","OK")]
        self._refresh_table()

    def _add_cmd(self, src, cmd, val, status):
        self.commands.append((datetime.now().strftime("%H:%M:%S"), src, cmd, val, status))
        self.commands = self.commands[-30:]
        self._refresh_table()

    def _refresh_table(self):
        self._tbl.setRowCount(len(self.commands))
        for i, (ts, src, cmd, val, st) in enumerate(reversed(self.commands)):
            self._tbl.setItem(i, 0, QTableWidgetItem(ts))
            self._tbl.setItem(i, 1, QTableWidgetItem(src))
            self._tbl.setItem(i, 2, QTableWidgetItem(cmd))
            self._tbl.setItem(i, 3, QTableWidgetItem(val))
            si = QTableWidgetItem(st)
            c  = (GREEN  if st == "ALLOWED" else
                  ORANGE if "BLOCK" in st   else
                  RED    if "COMP"  in st   else TDIM)
            si.setForeground(QColor(c))
            self._tbl.setItem(i, 4, si)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # Fractional Windows display scaling (125%/150%, common on laptops)
    # recalculating mid-session -- e.g. across a maximize's window-state
    # change -- is a well-known source of PyQt6 text rendering breaking
    # while widget geometry stays correct. Pinning a rounding policy before
    # QApplication exists stops Qt from renegotiating that scale factor
    # after startup.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MedShieldDashboard()
    win.show()
    sys.exit(app.exec())