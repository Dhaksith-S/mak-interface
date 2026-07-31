"""
MedShield AI — Hybrid Dashboard (Laptop 1)
Realistic insulin pump animation + 9-layer security system
Connects to Flask backend at localhost:5000
"""

import sys, math, random, threading
from datetime import datetime

import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QGridLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy, QScrollArea,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, QPointF, QRectF, QPropertyAnimation,
    pyqtProperty, QThread, pyqtSignal, QEasingCurve
)
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QFont,
    QLinearGradient, QRadialGradient, QPolygonF
)
import pyqtgraph as pg

# ─── Palette ─────────────────────────────────────────────────────────────────
BG_MAIN   = "#050a12"
BG_PANEL  = "#0a1020"
BG_CARD   = "#0d1525"
BORDER    = "#1a2535"
CYAN      = "#00c8ff"
GREEN     = "#30ff80"
YELLOW    = "#ffcc00"
ORANGE    = "#ff8800"
RED       = "#ff3030"
PURPLE    = "#c040ff"
MUTED     = "#607090"
TDIM      = "#8090b0"
BACKEND   = "http://localhost:5000"

ATTACKS = [
    ("☠ Overdose",        {"units": 200,  "source": "UNKNOWN_DEVICE",   "auth_token": "fake",        "source_mac": "00:00:00:00:00:FF"}, "200U Overdose Command"),
    ("⚡ Rapid Repeat",   {"units": 10,   "source": "CGM_SPOOFED",      "auth_token": "fake",        "source_mac": "AA:BB:CC:DD:EE:99"}, "10U × Rapid Repeat"),
    ("👻 Spoof Device",   {"units": 8,    "source": "CGM_001",          "auth_token": "spoof_token", "source_mac": "AA:BB:CC:DD:EE:02"}, "Cloned CGM Identity"),
    ("🔓 Pairing Hijack", {"units": 5,    "source": "UNKNOWN_PAIR",     "auth_token": "",            "source_mac": "DE:AD:BE:EF:00:01"}, "BLE Pairing Hijack"),
    ("🕵 Cred Theft",     {"units": 95,   "source": "DrApp_A",          "auth_token": "stolen_jwt",  "source_mac": "AA:BB:CC:DD:EE:03"}, "Stolen Doctor Credentials"),
]

LAYERS = [
    ("L1",  "Zero Trust Engine",        "ZTA · mTLS · JWT · RBAC"),
    ("L2",  "Rule Engine",              "Dosage cap · Rate limit · Whitelist"),
    ("L3",  "AI Anomaly Detection",     "Isolation Forest + Autoencoder"),
    ("L4",  "Device Fingerprint",       "MAC · RSSI · Timing · GPS"),
    ("L5",  "Behaviour Baseline",       "Z-score · Per-device · 3σ"),
    ("L6",  "Digital Twin Validator",   "LSTM · State divergence"),
    ("L7",  "Explainable AI (SHAP)",    "Feature importance · Human reason"),
    ("L8",  "Adaptive Trust Engine",    "Bayesian · Real-time decay"),
    ("ESC", "Emergency Safety Ctrl",    "IEC 62443 · FDA Failsafe"),
]

# ══════════════════════════════════════════════════════════════════════════════
#  GLUCOSE ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class GlucoseEngine:
    def __init__(self):
        self.current        = 132.0
        self.base           = 132.0
        self.active_insulin = 0.0
        self.history        = [132.0] * 120

    def inject(self, units: float):
        self.active_insulin += min(units, 300.0)

    def tick(self):
        if self.active_insulin > 0:
            drop = min(self.active_insulin * 0.5, 6.0)
            self.current        -= drop
            self.active_insulin  = max(0.0, self.active_insulin - drop * 0.8)
        elif self.current < self.base:
            self.current += 0.6
        else:
            self.current += random.uniform(-0.9, 0.9)
        self.current = max(20.0, min(380.0, self.current))
        self.history.append(self.current)
        self.history = self.history[-120:]

    def status(self):
        g = self.current
        if g < 54:  return "SEVERE HYPO",    RED
        if g < 70:  return "HYPOGLYCEMIA",   ORANGE
        if g < 100: return "LOW NORMAL",     YELLOW
        if g < 180: return "NORMAL",         GREEN
        if g < 250: return "HIGH",           ORANGE
        return             "HYPERGLYCEMIA",  RED


# ══════════════════════════════════════════════════════════════════════════════
#  INSULIN PARTICLE
# ══════════════════════════════════════════════════════════════════════════════
class InsulinParticle:
    def __init__(self, t=0.0):
        self.t       = t
        self.opacity = random.uniform(0.5, 1.0)
        self.size    = random.uniform(1.8, 3.5)


# ══════════════════════════════════════════════════════════════════════════════
#  PUMP + PATIENT SCENE
# ══════════════════════════════════════════════════════════════════════════════
class PumpPatientScene(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(900, 290)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dose        = 2.0
        self.critical    = False
        self.warning     = False
        self.blocked     = False
        self._flash      = 0.0
        self._phase      = 0.0
        self.particles   : list[InsulinParticle] = []
        self._flash_anim = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    @pyqtProperty(float)
    def flash(self): return self._flash

    @flash.setter
    def flash(self, v):
        self._flash = v
        self.update()

    def set_dose(self, dose: float, blocked: bool = False):
        prev = self.critical
        self.dose     = dose
        self.blocked  = blocked
        self.warning  = 50  <= dose < 200
        self.critical = dose >= 200 or blocked

        if (self.critical or self.warning) and not prev:
            if self._flash_anim:
                self._flash_anim.stop()
            a = QPropertyAnimation(self, b"flash", self)
            a.setDuration(400)
            a.setStartValue(0.0)
            a.setKeyValueAt(0.5, 1.0)
            a.setEndValue(0.0)
            a.setLoopCount(-1)
            a.start()
            self._flash_anim = a
        elif not self.critical and not self.warning:
            if self._flash_anim:
                self._flash_anim.stop()
                self._flash_anim = None
            self._flash = 0.0

    def particle_speed(self):
        if self.blocked: return 0.0
        d = self.dose
        if d <= 0:   return 0.0
        if d <= 5:   return d * 0.06
        if d <= 20:  return d * 0.04
        if d <= 50:  return d * 0.025
        return min(d * 0.013, 1.8)

    def _tick(self):
        self._phase = (self._phase + 0.04) % (2 * math.pi)
        spd = self.particle_speed()
        for p in self.particles:
            p.t += spd * 0.016
        self.particles = [p for p in self.particles if p.t < 1.05]
        if not self.blocked and self.dose > 0:
            rate = 0.5 if self.critical else (0.3 if self.warning else 0.2)
            if random.random() < rate:
                self.particles.append(InsulinParticle(random.uniform(-0.05, 0.0)))
        self.update()

    @staticmethod
    def _bezier(t, p0, p1, p2, p3):
        u = 1 - t
        return (u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0],
                u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1])

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        # layout anchors
        px, py = 32, h // 2 - 85
        pw, ph = 92, 148
        sx, sy = w - 195, h // 2 - 12   # infusion site

        self._draw_body(p, w, h, sx, sy)

        # tube bezier points
        t0 = (px + pw - 2, py + 20)
        c1 = (t0[0] + 65, t0[1] - 45)
        c2 = (sx - 85,    sy - 65)
        te = (sx, sy)

        self._draw_tube(p, t0, c1, c2, te)
        self._draw_particles(p, t0, c1, c2, te)
        self._draw_infusion_site(p, sx, sy)
        self._draw_pump(p, px, py, pw, ph)
        self._draw_reservoir_port(p, px + pw // 2, py)

        # BLOCKED overlay shield
        if self.blocked:
            self._draw_block_shield(p, w, h, t0, c1, c2, te)

    def _draw_body(self, p, w, h, sx, sy):
        skin = QLinearGradient(w * 0.38, 0, w, 0)
        skin.setColorAt(0.0,  QColor(5,   10,  18,  0))
        skin.setColorAt(0.22, QColor(190, 145, 110, 190))
        skin.setColorAt(0.65, QColor(220, 175, 140, 255))
        skin.setColorAt(1.0,  QColor(195, 150, 115, 255))
        p.setBrush(QBrush(skin)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(w * 0.38, 0, w * 0.62, h))

        hi = QLinearGradient(w * 0.48, 0, w * 0.66, 0)
        hi.setColorAt(0, QColor(255, 220, 190, 0))
        hi.setColorAt(0.4, QColor(255, 220, 190, 55))
        hi.setColorAt(1, QColor(255, 220, 190, 0))
        p.setBrush(QBrush(hi))
        p.drawRect(QRectF(w * 0.38, 0, w * 0.62, h))

        jy = h * 0.74
        jeans = QLinearGradient(0, jy, 0, h)
        jeans.setColorAt(0, QColor(48, 92, 158, 0))
        jeans.setColorAt(0.12, QColor(48, 92, 158, 210))
        jeans.setColorAt(1.0, QColor(33, 66, 118, 255))
        p.setBrush(QBrush(jeans))
        p.drawRect(QRectF(w * 0.38, jy, w * 0.62, h - jy))

        p.setPen(QPen(QColor(78, 128, 178, 110), 1.5, Qt.PenStyle.DashLine))
        p.drawLine(int(w * 0.41), int(jy + 9), int(w), int(jy + 9))

        p.setPen(QPen(QColor(38, 72, 128), 2))
        p.setBrush(QBrush(QColor(52, 98, 152)))
        p.drawRoundedRect(QRectF(w * 0.60, jy - 7, 19, 19), 3, 3)

        nav_x, nav_y = int(w * 0.52), int(h * 0.37)
        ng = QRadialGradient(QPointF(nav_x, nav_y), 10)
        ng.setColorAt(0, QColor(168, 122, 92))
        ng.setColorAt(1, QColor(220, 175, 140, 0))
        p.setBrush(QBrush(ng)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(nav_x, nav_y), 9, 7)

    def _draw_tube(self, p, s, c1, c2, e):
        path = QPainterPath()
        path.moveTo(*s)
        path.cubicTo(c1[0], c1[1], c2[0], c2[1], e[0], e[1])

        if self.blocked:
            gc = QColor(255, 50, 50, 25)
        elif self.critical:
            gc = QColor(255, 100, 0, 22)
        else:
            gc = QColor(0, 200, 255, 18)

        p.strokePath(path, QPen(gc, 10, cap=Qt.PenCapStyle.RoundCap))
        tc = QColor(200, 220, 230, 155)
        p.strokePath(path, QPen(tc, 4,  cap=Qt.PenCapStyle.RoundCap))
        p.strokePath(path, QPen(QColor(80, 120, 150, 95), 1.5, cap=Qt.PenCapStyle.RoundCap))

    def _draw_particles(self, p, s, c1, c2, e):
        if self.blocked:
            return
        if self.critical:
            bc = QColor(255, 50, 50)
        elif self.warning:
            bc = QColor(255, 195, 0)
        else:
            bc = QColor(0, 210, 255)

        for part in self.particles:
            t = max(0.0, min(1.0, part.t))
            x, y = self._bezier(t, s, c1, c2, e)
            alpha = int(255 * part.opacity)
            col   = QColor(bc.red(), bc.green(), bc.blue(), alpha)
            r     = part.size
            grad  = QRadialGradient(QPointF(x, y), r * 3.2)
            grad.setColorAt(0, QColor(col.red(), col.green(), col.blue(), int(alpha * 0.55)))
            grad.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
            p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), r * 3.2, r * 3.2)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(x, y), r, r)

    def _draw_block_shield(self, p, w, h, s, c1, c2, e):
        # Red X across the tube midpoint
        mx, my = self._bezier(0.5, s, c1, c2, e)
        shield_col = QColor(255, 50, 50, 180)

        # Glow circle
        grad = QRadialGradient(QPointF(mx, my), 28)
        grad.setColorAt(0, QColor(255, 50, 50, 80))
        grad.setColorAt(1, QColor(255, 50, 50, 0))
        p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(mx, my), 28, 28)

        # BLOCK badge
        p.setBrush(QBrush(QColor(180, 0, 0, 210)))
        p.setPen(QPen(QColor(255, 80, 80), 1.5))
        p.drawRoundedRect(QRectF(mx - 30, my - 13, 60, 26), 8, 8)
        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255, 200, 200)))
        p.drawText(QRectF(mx - 30, my - 13, 60, 26),
                   Qt.AlignmentFlag.AlignCenter, "⛔ BLOCKED")

    def _draw_infusion_site(self, p, cx, cy):
        ag = QRadialGradient(QPointF(cx, cy), 33)
        ag.setColorAt(0.0, QColor(230, 195, 162))
        ag.setColorAt(0.6, QColor(210, 176, 146))
        ag.setColorAt(1.0, QColor(188, 152, 122))
        p.setBrush(QBrush(ag))
        p.setPen(QPen(QColor(168, 132, 102), 1))
        p.drawEllipse(QPointF(cx, cy), 33, 33)

        p.setPen(QPen(QColor(158, 122, 96, 55), 0.5))
        for i in range(-28, 30, 5):
            p.drawLine(int(cx+i), int(cy-28), int(cx+i), int(cy+28))
            p.drawLine(int(cx-28), int(cy+i), int(cx+28), int(cy+i))

        hg = QRadialGradient(QPointF(cx-3, cy-3), 16)
        hg.setColorAt(0, QColor(238, 244, 255))
        hg.setColorAt(1, QColor(188, 204, 224))
        p.setBrush(QBrush(hg))
        p.setPen(QPen(QColor(158, 174, 194), 1.5))
        p.drawEllipse(QPointF(cx, cy), 16, 16)

        p.setPen(Qt.PenStyle.NoPen)
        for angle in [-35, 35]:
            rad = math.radians(angle)
            lx  = cx + 10 * math.cos(rad)
            ly  = cy - 10 * math.sin(rad) - 4
            led_col = QColor(255, 50, 50) if self.critical else QColor(80, 160, 255)
            lg = QRadialGradient(QPointF(lx, ly), 4)
            lg.setColorAt(0, QColor(led_col.red(), led_col.green(), led_col.blue(), 220))
            lg.setColorAt(1, QColor(led_col.red(), led_col.green(), led_col.blue(), 0))
            p.setBrush(QBrush(lg))
            p.drawEllipse(QPointF(lx, ly), 4, 4)
            p.setBrush(QBrush(led_col.lighter(140)))
            p.drawEllipse(QPointF(lx, ly), 2, 2)

        p.setBrush(QBrush(QColor(200, 215, 230)))
        p.setPen(QPen(QColor(140, 155, 170), 1))
        p.drawEllipse(QPointF(cx, cy), 4, 4)

        pulse_alpha = int(55 * (0.5 + 0.5 * math.sin(self._phase)))
        pulse_col   = QColor(255, 50, 50) if self.critical else QColor(0, 200, 255)
        for rm in [1.4, 1.9, 2.5]:
            r = 33 * rm
            p.setPen(QPen(QColor(pulse_col.red(), pulse_col.green(),
                                 pulse_col.blue(), int(pulse_alpha / rm)), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r, r)

        p.setBrush(QBrush(QColor(178, 193, 210)))
        p.setPen(QPen(QColor(128, 143, 160), 1))
        p.drawEllipse(QPointF(cx - 14, cy - 6), 5, 5)

    def _draw_pump(self, p, x, y, w, h):
        # Shadow
        sg = QRadialGradient(QPointF(x+w/2, y+h), h * 0.65)
        sg.setColorAt(0, QColor(0,0,0,75)); sg.setColorAt(1, QColor(0,0,0,0))
        p.setBrush(QBrush(sg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(x-10, y+h-8, w+20, 28))

        # Body
        bg = QLinearGradient(x, y, x+w, y+h)
        bg.setColorAt(0.0, QColor(54, 56, 62))
        bg.setColorAt(0.3, QColor(40, 42, 48))
        bg.setColorAt(0.7, QColor(30, 32, 38))
        bg.setColorAt(1.0, QColor(22, 24, 30))
        p.setBrush(QBrush(bg))
        p.setPen(QPen(QColor(66, 70, 80), 1.5))
        p.drawRoundedRect(QRectF(x, y, w, h), 12, 12)

        p.setPen(QPen(QColor(82, 87, 102, 125), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x+0.5, y+0.5, w-1, h-1), 12, 12)

        # OLED screen
        sx, sy = x+7, y+18
        sw, sh = w-14, 64
        scrg = QLinearGradient(sx, sy, sx, sy+sh)
        scrg.setColorAt(0, QColor(8, 22, 36))
        scrg.setColorAt(1, QColor(5, 14, 24))
        p.setBrush(QBrush(scrg))
        p.setPen(QPen(QColor(0, 105, 155), 1.2))
        p.drawRoundedRect(QRectF(sx, sy, sw, sh), 5, 5)

        # Time
        p.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        p.setPen(QPen(QColor(155, 178, 198)))
        p.drawText(QRectF(sx+2, sy+3, sw-4, 10),
                   Qt.AlignmentFlag.AlignRight, datetime.now().strftime("%H:%M"))

        # Shield icon
        scol = QColor(255, 50, 50) if self.critical else QColor(0, 200, 80)
        shield = QPainterPath()
        bx, by_ = sx+5, sy+7
        shield.moveTo(bx+6, by_); shield.lineTo(bx+12, by_+4)
        shield.lineTo(bx+12, by_+10)
        shield.quadTo(bx+6, by_+16, bx+6, by_+16)
        shield.quadTo(bx, by_+10, bx, by_+10)
        shield.lineTo(bx, by_+4); shield.closeSubpath()
        p.setBrush(QBrush(scol)); p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(shield)

        # Glucose / dose value
        vcol = QColor(255, 80, 80) if self.critical else QColor(0, 220, 100)
        p.setFont(QFont("Courier New", 13, QFont.Weight.Bold))
        p.setPen(QPen(vcol))
        p.drawText(QRectF(sx, sy+22, sw, 22), Qt.AlignmentFlag.AlignCenter,
                   f"{self.dose:.1f}")
        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(QColor(100, 140, 162)))
        p.drawText(QRectF(sx, sy+43, sw, 10), Qt.AlignmentFlag.AlignCenter,
                   "U  Delivery")
        p.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
        p.setPen(QPen(QColor(0, 180, 255)))
        p.drawText(QRectF(sx, sy+54, sw, 10), Qt.AlignmentFlag.AlignCenter,
                   f"{max(0.0, self.dose/60.0):.3f} U/min")

        # Glare
        gg = QLinearGradient(sx, sy, sx+sw, sy+sh*0.5)
        gg.setColorAt(0, QColor(255,255,255,20)); gg.setColorAt(1, QColor(255,255,255,0))
        p.setBrush(QBrush(gg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(sx, sy, sw, sh*0.5), 5, 5)

        # LEDs
        led_y = y + 9
        for lx_off, col_ok, col_bad, animate in [
            (18, QColor(0,255,80), QColor(255,60,60), False),
            (30, QColor(255,165,0,85), QColor(255,80,80), True),
        ]:
            if animate:
                alpha = int(180*(0.5+0.5*math.sin(self._phase*2))) \
                        if (self.warning or self.critical) else 80
                lc = QColor(col_bad.red(), col_bad.green(), col_bad.blue(), alpha) \
                     if self.critical else QColor(col_ok.red(), col_ok.green(),
                                                  col_ok.blue(), alpha)
            else:
                lc = col_bad if self.critical else col_ok
            lg = QRadialGradient(QPointF(x+lx_off, led_y), 5)
            lg.setColorAt(0, lc); lg.setColorAt(1, QColor(0,0,0,0))
            p.setBrush(QBrush(lg)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x+lx_off, led_y), 4, 4)
            p.setBrush(QBrush(lc.lighter(140)))
            p.drawEllipse(QPointF(x+lx_off, led_y), 2, 2)

        # D-pad
        dx, dy_ = x+w//2, y+h-40
        dr = 14
        dpg = QRadialGradient(QPointF(dx-2, dy_-2), dr+6)
        dpg.setColorAt(0, QColor(66,72,88)); dpg.setColorAt(1, QColor(42,46,57))
        p.setBrush(QBrush(dpg)); p.setPen(QPen(QColor(82,87,102), 1))
        p.drawEllipse(QPointF(dx, dy_), dr+5, dr+5)
        arm, aw = 9, 6
        p.setBrush(QBrush(QColor(56,62,74)))
        p.setPen(QPen(QColor(76,82,97), 1))
        for ddx, ddy in [(0,-arm),(0,arm),(-arm,0),(arm,0)]:
            p.drawRoundedRect(QRectF(dx+ddx-aw//2, dy_+ddy-aw//2, aw, aw), 2, 2)
        cg = QRadialGradient(QPointF(dx-1, dy_-1), 6)
        cg.setColorAt(0, QColor(76,82,100)); cg.setColorAt(1, QColor(50,54,67))
        p.setBrush(QBrush(cg)); p.setPen(QPen(QColor(92,97,117), 1))
        p.drawEllipse(QPointF(dx, dy_), 6, 6)
        p.setPen(QPen(QColor(142,152,172), 1))
        p.setFont(QFont("Arial", 5))
        for txt, ddx, ddy in [("▲",0,-arm),("▼",0,arm),("◀",-arm,0),("▶",arm,0)]:
            p.drawText(QRectF(dx+ddx-5, dy_+ddy-4, 10, 8),
                       Qt.AlignmentFlag.AlignCenter, txt)

        # Side button
        p.setBrush(QBrush(QColor(56,62,74)))
        p.setPen(QPen(QColor(82,87,102), 1))
        p.drawRoundedRect(QRectF(x+w-4, y+55, 8, 22), 3, 3)

        # Clip
        clg = QLinearGradient(x+w+1, y+20, x+w+11, y+20)
        clg.setColorAt(0, QColor(62,67,80)); clg.setColorAt(1, QColor(42,46,57))
        p.setBrush(QBrush(clg)); p.setPen(QPen(QColor(77,82,97), 1))
        p.drawRoundedRect(QRectF(x+w+1, y+20, 9, 90), 4, 4)
        p.drawRoundedRect(QRectF(x+w+2, y+105, 7, 14), 3, 3)

        p.setFont(QFont("Arial", 5, QFont.Weight.Bold))
        p.setPen(QPen(QColor(92,102,122)))
        p.drawText(QRectF(x+4, y+h-14, w-8, 12),
                   Qt.AlignmentFlag.AlignCenter, "SmartPump X2")

    def _draw_reservoir_port(self, p, cx, ty):
        p.setBrush(QBrush(QColor(62,67,80)))
        p.setPen(QPen(QColor(82,90,107), 1.5))
        p.drawRoundedRect(QRectF(cx-7, ty-17, 14, 19), 3, 3)
        sg = QLinearGradient(cx-7, ty-17, cx+7, ty-17)
        sg.setColorAt(0,   QColor(102,110,130,75))
        sg.setColorAt(0.5, QColor(152,162,182,38))
        sg.setColorAt(1,   QColor(82,90,107,55))
        p.setBrush(QBrush(sg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(cx-7, ty-17, 14, 19), 3, 3)
        p.setBrush(QBrush(QColor(182,197,212)))
        p.setPen(QPen(QColor(142,157,172), 1))
        p.drawEllipse(QPointF(cx, ty-17), 4, 4)


# ══════════════════════════════════════════════════════════════════════════════
#  NETWORK WORKER
# ══════════════════════════════════════════════════════════════════════════════
class NetworkWorker(QThread):
    state_received = pyqtSignal(dict)

    def run(self):
        while True:
            try:
                r = requests.get(f"{BACKEND}/status", timeout=2)
                if r.status_code == 200:
                    self.state_received.emit(r.json())
            except Exception:
                pass
            self.msleep(1500)


# ══════════════════════════════════════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _card(title=""):
    f = QFrame()
    f.setStyleSheet(f"QFrame{{background:{BG_CARD};border-radius:10px;border:1px solid {BORDER};}}")
    vl = QVBoxLayout(f)
    vl.setContentsMargins(13,11,13,11); vl.setSpacing(7)
    if title:
        lbl = QLabel(title)
        lbl.setStyleSheet(f"color:{CYAN};font-size:10px;font-weight:bold;"
                          f"letter-spacing:1.5px;background:transparent;")
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
    btn.setStyleSheet(f"""
        QPushButton{{background:{bg};color:{fg};font-size:{sz}px;
            font-weight:bold;padding:8px 10px;border-radius:7px;{b}}}
        QPushButton:hover{{background:{QColor(bg).lighter(130).name()};}}
        QPushButton:disabled{{opacity:0.4;}}
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

        self.engine        = GlucoseEngine()
        self.current_dose  = 2.0
        self.reservoir     = 120.0
        self.battery       = 87
        self.attack_active = False
        self.medshield_on  = True
        self.risk_score    = 0.18
        self.trust_score   = 0.92
        self.commands      = [
            ("--:--:--", "CGM_001",    "Glucose Reading", "132 mg/dL", "ALLOWED"),
            ("--:--:--", "DrApp_A",    "Set Basal",       "1.20 U/hr", "ALLOWED"),
            ("--:--:--", "PatientApp", "Bolus",           "2.0 U",     "ALLOWED"),
        ]
        self.glucose_hist  = [132.0] * 80
        self.dose_hist     = [2.0]   * 80
        self.risk_hist     = [0.18]  * 80

        self._build_ui()

        # sim timer
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._sim_tick)
        self._sim_timer.start(1000)

        # network worker
        self._net = NetworkWorker()
        self._net.state_received.connect(self._on_state)
        self._net.start()

        # time timer
        self._clk = QTimer(self)
        self._clk.timeout.connect(lambda: self._time_lbl.setText(
            datetime.now().strftime("%H:%M:%S")))
        self._clk.start(1000)

    # ─────────────────────────────────────────────────────────────────────
    #  BUILD UI
    # ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(14,14,14,14); vbox.setSpacing(10)
        self.setCentralWidget(root)

        self._build_header(vbox)

        mid = QHBoxLayout(); mid.setSpacing(10)
        self._build_left(mid)
        self._build_center(mid)
        self._build_right(mid)
        vbox.addLayout(mid, stretch=3)

        self._build_bottom(vbox)

    # ── HEADER ───────────────────────────────────────────────────────────
    def _build_header(self, parent):
        hdr = QFrame()
        hdr.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        row = QHBoxLayout(hdr); row.setContentsMargins(22,12,22,12)

        tl = QVBoxLayout()
        tl.addWidget(_lbl("🛡️  MedShield AI", CYAN, 26, True))
        tl.addWidget(_lbl("REAL-TIME INSULIN PUMP SECURITY SYSTEM", MUTED, 10))
        row.addLayout(tl); row.addSpacing(20)

        self._sys_card   = self._hdr_card(row, "SYSTEM",      "PROTECTED",   GREEN,  "#0a2e1e")
        self._risk_card  = self._hdr_card(row, "RISK SCORE",  "0.18",        CYAN,   "#0a2030")
        self._trust_card = self._hdr_card(row, "TRUST SCORE", "0.92",        GREEN,  "#0a2e1e")
        self._gluc_card  = self._hdr_card(row, "GLUCOSE",     "132 mg/dL",   GREEN,  "#0a2e1e")
        self._layer_card = self._hdr_card(row, "LAYERS",      "9 / 9 ACTIVE",GREEN,  "#0a2e1e")

        row.addStretch()

        ms_btn = QPushButton("🛡 MedShield: ON")
        ms_btn.setCheckable(True); ms_btn.setChecked(True)
        ms_btn.setStyleSheet(f"""
            QPushButton{{background:#003a1a;color:{GREEN};font-size:12px;font-weight:bold;
                padding:8px 16px;border-radius:8px;border:2px solid {GREEN};}}
            QPushButton:checked{{background:#003a1a;color:{GREEN};border-color:{GREEN};}}
            QPushButton:!checked{{background:#3a0000;color:{RED};border-color:{RED};}}
        """)
        ms_btn.toggled.connect(self._toggle_medshield)
        self._ms_btn = ms_btn
        row.addWidget(ms_btn); row.addSpacing(12)

        self._time_lbl = _lbl(datetime.now().strftime("%H:%M:%S"), TDIM, 15)
        self._time_lbl.setStyleSheet(f"color:{TDIM};font-size:15px;"
                                     f"font-family:'Courier New';background:transparent;")
        row.addWidget(self._time_lbl)
        parent.addWidget(hdr)

    def _hdr_card(self, layout, title, value, col, bg):
        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{bg};border-radius:8px;padding:4px;}}")
        cl = QVBoxLayout(card); cl.setContentsMargins(14,7,14,7)
        cl.addWidget(_lbl(title, MUTED, 9, True))
        vl = _lbl(value, col, 17, True)
        cl.addWidget(vl)
        layout.addWidget(card); layout.addSpacing(6)
        return vl

    # ── LEFT PANEL ───────────────────────────────────────────────────────
    def _build_left(self, parent):
        col = QFrame()
        col.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        vl = QVBoxLayout(col); vl.setContentsMargins(13,13,13,13); vl.setSpacing(9)

        # Pump info
        pi, pil = _card("PUMP INFORMATION")
        grid = QGridLayout(); grid.setSpacing(4)
        self._pump_rows = {}
        for i, (k, v) in enumerate([
            ("Model",     "SmartPump X2"),
            ("Device ID", "InsulinPump_001"),
            ("MAC",       "AA:BB:CC:DD:EE:01"),
            ("Reservoir", f"{self.reservoir:.0f} U"),
            ("Battery",   f"{self.battery}%"),
            ("Basal Rate","1.20 U/hr"),
            ("Status",    "Normal"),
            ("Connection","BLE + WiFi"),
        ]):
            grid.addWidget(_lbl(k, MUTED, 10), i, 0)
            rv = _lbl(v, TDIM, 10, True)
            self._pump_rows[k] = rv
            grid.addWidget(rv, i, 1)
        pil.addLayout(grid)
        vl.addWidget(pi)

        # Glucose reading
        gi, gil = _card("CURRENT GLUCOSE")
        gil.addWidget(_lbl("Blood Glucose Level", MUTED, 10))
        self._gluc_big = QLabel("132")
        self._gluc_big.setStyleSheet(f"color:{GREEN};font-size:52px;font-weight:bold;"
                                     f"font-family:'Courier New';background:transparent;")
        gil.addWidget(self._gluc_big)
        r2 = QHBoxLayout()
        r2.addWidget(_lbl("mg/dL", MUTED, 13))
        self._gluc_status = _lbl("NORMAL", GREEN, 13, True)
        r2.addWidget(self._gluc_status)
        r2.addStretch()
        gil.addLayout(r2)
        vl.addWidget(gi)

        # Dose info
        di, dil = _card("CURRENT DOSE")
        self._dose_big = QLabel("2.0 U")
        self._dose_big.setStyleSheet(f"color:{CYAN};font-size:36px;font-weight:bold;"
                                     f"font-family:'Courier New';background:transparent;")
        dil.addWidget(self._dose_big)
        self._flow_lbl = _lbl("Flow: 0.120 U/s", MUTED, 10)
        dil.addWidget(self._flow_lbl)
        vl.addWidget(di)

        # Quick control
        qc, qcl = _card("QUICK CONTROLS")
        bolus_btn = _btn("💉  Deliver 2U Bolus", bg="#004488", border="#0088ff")
        bolus_btn.clicked.connect(self._deliver_bolus)
        qcl.addWidget(bolus_btn)
        reset_btn = _btn("↺  Reset Pump", bg="#1e1530", fg="#c0b0d0", border="#4a3060")
        reset_btn.clicked.connect(self._reset)
        qcl.addWidget(reset_btn)
        vl.addWidget(qc)

        vl.addStretch()
        parent.addWidget(col, stretch=1)

    # ── CENTER PANEL ─────────────────────────────────────────────────────
    def _build_center(self, parent):
        col = QFrame()
        col.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        vl = QVBoxLayout(col); vl.setContentsMargins(14,14,14,14); vl.setSpacing(9)

        vl.addWidget(_lbl("LIVE INSULIN DELIVERY SIMULATION", CYAN, 12, True))

        # Pipeline strip
        pipe = QHBoxLayout(); pipe.setSpacing(3)
        for icon, lbl_txt in [("🔵","CGM SENSOR"),("🧠","AI ENGINE"),
                               ("📟","PUMP"),("🩺","PATIENT")]:
            wf, wl = _card()
            wl.addWidget(_lbl(icon, sz=24), 0, Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(_lbl(lbl_txt, MUTED, 8, True), 0, Qt.AlignmentFlag.AlignCenter)
            pipe.addWidget(wf)
            if lbl_txt != "PATIENT":
                pipe.addWidget(_lbl("→", CYAN, 16, True), 0, Qt.AlignmentFlag.AlignCenter)
        vl.addLayout(pipe)

        # Main animation scene
        self._scene = PumpPatientScene()
        vl.addWidget(self._scene)

        # Status strip
        ss, ssl = _card()
        sr = QHBoxLayout(); sr.addStretch()
        sr.addWidget(_lbl("Patient Status:", MUTED, 12))
        sr.addSpacing(8)
        self._pt_status = _lbl("STABLE", GREEN, 14, True)
        sr.addWidget(self._pt_status)
        sr.addStretch()
        ssl.addLayout(sr)
        vl.addWidget(ss)

        # SHAP Explanation box
        sb, sbl = _card("⚡ LAST DETECTION REASON  (Explainable AI — SHAP)")
        self._shap_lbl = QLabel("No alerts detected. All commands within safe parameters.")
        self._shap_lbl.setStyleSheet(f"color:{TDIM};font-size:11px;"
                                     f"font-family:'Courier New';background:transparent;")
        self._shap_lbl.setWordWrap(True)
        sbl.addWidget(self._shap_lbl)
        vl.addWidget(sb)

        # Command history
        ch, chl = _card("COMMAND HISTORY")
        self._cmd_tbl = QTableWidget()
        self._cmd_tbl.setColumnCount(5)
        self._cmd_tbl.setHorizontalHeaderLabels(
            ["TIME", "SOURCE", "COMMAND", "VALUE", "STATUS"])
        self._cmd_tbl.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._cmd_tbl.setMaximumHeight(140)
        self._cmd_tbl.setStyleSheet(f"""
            QTableWidget{{background:{BG_MAIN};color:{TDIM};
                gridline-color:{BORDER};border:none;font-size:10px;}}
            QHeaderView::section{{background:{BG_PANEL};color:{CYAN};
                padding:4px;border:none;font-size:10px;font-weight:bold;}}
            QTableWidget::item{{padding:3px;}}
        """)
        self._refresh_table()
        chl.addWidget(self._cmd_tbl)
        vl.addWidget(ch)

        parent.addWidget(col, stretch=3)

    # ── RIGHT PANEL ──────────────────────────────────────────────────────
    def _build_right(self, parent):
        col = QFrame()
        col.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        vl = QVBoxLayout(col); vl.setContentsMargins(13,13,13,13); vl.setSpacing(8)

        # 5 attack buttons
        af, afl = _card("☠  ATTACK SIMULATION")
        afl.addWidget(_lbl("Select attack type and launch:", MUTED, 10))
        self._atk_btns = []
        for name, payload, desc in ATTACKS:
            b = _btn(name, bg="#2a0a0a", fg="#ff8080", border="#5a1a1a", sz=11)
            b.clicked.connect(lambda _, pay=payload, d=desc: self._launch_attack(pay, d))
            afl.addWidget(b)
            self._atk_btns.append(b)

        stop_btn = _btn("🛑  STOP ALL ATTACKS", bg="#0a2a0a", fg=GREEN, border="#1a5a1a")
        stop_btn.clicked.connect(self._stop_attack)
        afl.addWidget(stop_btn)
        vl.addWidget(af)

        # 9 security layers
        lf, lfl = _card("🛡  MEDSHIELD AI — 9 LAYERS")
        self._layer_widgets = []
        for tag, name, tech in LAYERS:
            row = QHBoxLayout(); row.setSpacing(6)
            tag_lbl = QLabel(tag)
            tag_lbl.setFixedWidth(32)
            tag_lbl.setStyleSheet(f"color:#050a12;background:{GREEN};"
                                  f"font-size:8px;font-weight:bold;border-radius:4px;"
                                  f"padding:2px 3px;")
            tag_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(tag_lbl)
            info = QVBoxLayout(); info.setSpacing(0)
            nl = _lbl(name, GREEN, 10, True)
            tl = _lbl(tech, MUTED, 8)
            info.addWidget(nl); info.addWidget(tl)
            row.addLayout(info)
            status = _lbl("✅", GREEN, 12, True)
            status.setFixedWidth(22)
            row.addWidget(status)
            lfl.addLayout(row)
            self._layer_widgets.append((tag_lbl, nl, status))
        vl.addWidget(lf)

        # Forensic log
        ff, ffl = _card("🔍  FORENSIC LOG")
        self._forensic_lbl = QLabel("No incidents logged.")
        self._forensic_lbl.setStyleSheet(
            f"color:{MUTED};font-size:9px;font-family:'Courier New';"
            f"background:transparent;")
        self._forensic_lbl.setWordWrap(True)
        ffl.addWidget(self._forensic_lbl)
        vl.addWidget(ff)

        vl.addStretch()
        parent.addWidget(col, stretch=1)

    # ── BOTTOM GRAPHS ────────────────────────────────────────────────────
    def _build_bottom(self, parent):
        btm = QFrame()
        btm.setStyleSheet(f"QFrame{{background:{BG_PANEL};border-radius:12px;"
                          f"border:1px solid {BORDER};}}")
        row = QHBoxLayout(btm); row.setContentsMargins(12,10,12,10); row.setSpacing(10)
        pg.setConfigOption("background", BG_PANEL)
        pg.setConfigOption("foreground", MUTED)
        self._g_curve = self._graph(row, "GLUCOSE TREND (mg/dL)", GREEN,  [70, 140])
        self._d_curve = self._graph(row, "DOSAGE TREND (U)",       CYAN,   [0, 15])
        self._r_curve = self._graph(row, "RISK SCORE TREND",       RED,    [0, 1])
        parent.addWidget(btm, stretch=2)

    def _graph(self, layout, title, color, ref_lines=None):
        pw = pg.PlotWidget(title=title)
        pw.setBackground(BG_PANEL)
        pw.showGrid(x=True, y=True, alpha=0.15)
        pw.setMenuEnabled(False)
        if ref_lines:
            for rv in ref_lines:
                pw.addLine(y=rv, pen=pg.mkPen(color=color, width=1,
                           style=Qt.PenStyle.DashLine))
        c = pw.plot(pen=pg.mkPen(color=color, width=2))
        layout.addWidget(pw)
        return c

    # ─────────────────────────────────────────────────────────────────────
    #  SIMULATION TICK
    # ─────────────────────────────────────────────────────────────────────
    def _sim_tick(self):
        self.engine.tick()
        g      = self.engine.current
        s, sc  = self.engine.status()
        flow   = self._scene.particle_speed()

        self._gluc_big.setText(f"{g:.0f}")
        self._gluc_big.setStyleSheet(f"color:{sc};font-size:52px;font-weight:bold;"
                                     f"font-family:'Courier New';background:transparent;")
        self._gluc_status.setText(s)
        self._gluc_status.setStyleSheet(f"color:{sc};font-size:13px;"
                                        f"font-weight:bold;background:transparent;")
        self._gluc_card.setText(f"{g:.0f} mg/dL")
        self._dose_big.setText(f"{self.current_dose:.1f} U")
        self._flow_lbl.setText(f"Flow: {flow:.3f} U/s")

        if self.current_dose >= 200:  ps, pc = "CRITICAL ⚠",  RED
        elif self.current_dose >= 50: ps, pc = "WARNING ⚠",   ORANGE
        elif self.current_dose >= 10: ps, pc = "MONITORING",  YELLOW
        else:                         ps, pc = "STABLE ✓",    GREEN
        self._pt_status.setText(ps)
        self._pt_status.setStyleSheet(f"color:{pc};font-size:14px;"
                                      f"font-weight:bold;background:transparent;")

        if self.current_dose > 0:
            self.reservoir = max(0.0, self.reservoir - self.current_dose / 3600)
            self._pump_rows["Reservoir"].setText(f"{self.reservoir:.1f} U")

        self.glucose_hist.pop(0); self.glucose_hist.append(g)
        self.dose_hist.pop(0);    self.dose_hist.append(self.current_dose)
        self.risk_hist.pop(0);    self.risk_hist.append(self.risk_score)
        xs = list(range(80))
        self._g_curve.setData(xs, self.glucose_hist)
        self._d_curve.setData(xs, self.dose_hist)
        self._r_curve.setData(xs, self.risk_hist)

    # ─────────────────────────────────────────────────────────────────────
    #  NETWORK STATE
    # ─────────────────────────────────────────────────────────────────────
    def _on_state(self, state):
        if state.get("is_compromised"):
            if not self.attack_active:
                self._show_attack_detected(state)
        else:
            if self.attack_active:
                self._stop_attack()
        dose = float(state.get("current_dose", self.current_dose))
        self.current_dose = dose
        self._scene.set_dose(dose, blocked=False)
        self.engine.inject(dose * 0.05)

    # ─────────────────────────────────────────────────────────────────────
    #  ATTACK ACTIONS
    # ─────────────────────────────────────────────────────────────────────
    def _launch_attack(self, payload, desc):
        self.attack_active = True
        blocked = self.medshield_on

        if blocked:
            # MedShield intercepts — pump stays safe
            self.risk_score  = 0.97
            self.trust_score = max(0.0, self.trust_score - 0.15)
            self._sys_card.setText("BLOCKED 🛡")
            self._sys_card.setStyleSheet(f"color:{ORANGE};font-size:17px;"
                                         f"font-weight:bold;background:transparent;")
            self._risk_card.setText("0.97")
            self._risk_card.setStyleSheet(f"color:{RED};font-size:17px;"
                                          f"font-weight:bold;background:transparent;")
            self._scene.set_dose(self.current_dose, blocked=True)
            self._set_layers(mode="blocked")
            self._shap_lbl.setText(
                f"BLOCKED — Risk: 0.97\n"
                f"Attack: {desc}\n"
                f"Reason: {self._shap_reason(payload)}\n"
                f"Triggered: {self._triggered_layer(payload)}\n"
                f"Action: Command dropped. Doctor + Patient notified."
            )
            self._shap_lbl.setStyleSheet(f"color:{RED};font-size:11px;"
                                         f"font-family:'Courier New';background:transparent;")
            self._add_command(payload.get("source","UNKNOWN"),
                              desc, f"{payload.get('units',0):.0f}U", "BLOCKED")
            self._write_forensic(desc, payload)
            self._layer_card.setText("9 / 9 ACTIVE")

            # Send to backend but MedShield would normally intercept
            threading.Thread(target=self._post_safe, args=(payload,), daemon=True).start()

        else:
            # No MedShield — attack hits pump directly
            self.risk_score = 0.99
            self._sys_card.setText("COMPROMISED ☠")
            self._sys_card.setStyleSheet(f"color:{RED};font-size:17px;"
                                         f"font-weight:bold;background:transparent;")
            self._risk_card.setText("0.99")
            self._risk_card.setStyleSheet(f"color:{RED};font-size:17px;"
                                          f"font-weight:bold;background:transparent;")
            units = float(payload.get("units", 200))
            self.current_dose = units
            self.engine.inject(units)
            self._scene.set_dose(units, blocked=False)
            self._set_layers(mode="compromised")
            self._shap_lbl.setText(
                f"⚠ ATTACK SUCCEEDED — No MedShield protection!\n"
                f"Injected: {units:.0f} U — Patient at critical risk!"
            )
            self._shap_lbl.setStyleSheet(f"color:{RED};font-size:12px;"
                                         f"font-family:'Courier New';background:transparent;")
            self._add_command(payload.get("source","UNKNOWN"),
                              desc, f"{units:.0f}U", "INJECTED ☠")
            threading.Thread(target=self._post_attack, args=(payload,), daemon=True).start()

    def _post_safe(self, payload):
        try: requests.post(f"{BACKEND}/reset", timeout=2)
        except: pass

    def _post_attack(self, payload):
        try: requests.post(f"{BACKEND}/dose", json=payload, timeout=2)
        except: pass

    def _shap_reason(self, payload):
        units = float(payload.get("units", 0))
        src   = payload.get("source", "")
        tok   = payload.get("auth_token", "")
        mac   = payload.get("source_mac", "")
        parts = []
        if units > 50:   parts.append(f"Dose {units:.0f}U exceeds safe limit (50U)")
        if not tok or tok == "fake": parts.append("Invalid/missing auth token")
        if "UNKNOWN" in src: parts.append("Unknown source device")
        if "SPOOF"   in src.upper(): parts.append("Device identity mismatch")
        if "stolen"  in tok.lower(): parts.append("Token flagged as stolen credential")
        return "; ".join(parts) if parts else "Behavioural anomaly detected"

    def _triggered_layer(self, payload):
        units = float(payload.get("units", 0))
        tok   = payload.get("auth_token", "")
        src   = payload.get("source", "")
        if units > 50:             return "L2 Rule Engine (dosage cap)"
        if not tok or tok=="fake": return "L1 Zero Trust (invalid token)"
        if "UNKNOWN" in src:       return "L4 Device Fingerprint"
        if "stolen" in tok:        return "L5 Behaviour Baseline"
        return "L3 AI Anomaly Detection"

    def _write_forensic(self, desc, payload):
        ts  = datetime.now().strftime("%H:%M:%S")
        txt = (f"[{ts}] BLOCKED\n"
               f"  Attack  : {desc}\n"
               f"  Source  : {payload.get('source','?')}\n"
               f"  MAC     : {payload.get('source_mac','?')}\n"
               f"  Units   : {payload.get('units','?')} U\n"
               f"  Token   : {'VALID' if payload.get('auth_token') not in ['','fake'] else 'INVALID'}\n"
               f"  Risk    : 0.97\n"
               f"  Action  : DROPPED + ALERT")
        self._forensic_lbl.setText(txt)
        self._forensic_lbl.setStyleSheet(
            f"color:{RED};font-size:9px;font-family:'Courier New';"
            f"background:transparent;")

    def _show_attack_detected(self, state):
        self._sys_card.setText("COMPROMISED ☠")
        self._sys_card.setStyleSheet(f"color:{RED};font-size:17px;"
                                     f"font-weight:bold;background:transparent;")

    def _stop_attack(self):
        self.attack_active = False
        self.risk_score    = 0.18
        self.trust_score   = min(1.0, self.trust_score + 0.05)
        self.current_dose  = 2.0
        self.engine        = GlucoseEngine()
        self._scene.set_dose(2.0, blocked=False)
        self._set_layers(mode="ok")
        self._sys_card.setText("PROTECTED ✓")
        self._sys_card.setStyleSheet(f"color:{GREEN};font-size:17px;"
                                     f"font-weight:bold;background:transparent;")
        self._risk_card.setText("0.18")
        self._risk_card.setStyleSheet(f"color:{CYAN};font-size:17px;"
                                      f"font-weight:bold;background:transparent;")
        self._shap_lbl.setText("No alerts detected. All commands within safe parameters.")
        self._shap_lbl.setStyleSheet(f"color:{TDIM};font-size:11px;"
                                     f"font-family:'Courier New';background:transparent;")
        self._forensic_lbl.setText("No incidents logged.")
        self._forensic_lbl.setStyleSheet(
            f"color:{MUTED};font-size:9px;font-family:'Courier New';background:transparent;")
        threading.Thread(target=lambda: requests.post(f"{BACKEND}/reset",
                         timeout=2), daemon=True).start()

    def _set_layers(self, mode="ok"):
        for tag_lbl, nl, status in self._layer_widgets:
            if mode == "ok":
                tag_lbl.setStyleSheet(f"color:#050a12;background:{GREEN};"
                                      f"font-size:8px;font-weight:bold;"
                                      f"border-radius:4px;padding:2px 3px;")
                nl.setStyleSheet(f"color:{GREEN};font-size:10px;"
                                 f"font-weight:bold;background:transparent;")
                status.setText("✅")
                status.setStyleSheet(f"color:{GREEN};font-size:12px;"
                                     f"font-weight:bold;background:transparent;")
            elif mode == "blocked":
                tag_lbl.setStyleSheet(f"color:#050a12;background:{ORANGE};"
                                      f"font-size:8px;font-weight:bold;"
                                      f"border-radius:4px;padding:2px 3px;")
                nl.setStyleSheet(f"color:{ORANGE};font-size:10px;"
                                 f"font-weight:bold;background:transparent;")
                status.setText("🛡")
                status.setStyleSheet(f"color:{ORANGE};font-size:12px;"
                                     f"font-weight:bold;background:transparent;")
            else:
                tag_lbl.setStyleSheet(f"color:#050a12;background:{RED};"
                                      f"font-size:8px;font-weight:bold;"
                                      f"border-radius:4px;padding:2px 3px;")
                nl.setStyleSheet(f"color:{RED};font-size:10px;"
                                 f"font-weight:bold;background:transparent;")
                status.setText("🚨")
                status.setStyleSheet(f"color:{RED};font-size:12px;"
                                     f"font-weight:bold;background:transparent;")

    # ─────────────────────────────────────────────────────────────────────
    #  OTHER ACTIONS
    # ─────────────────────────────────────────────────────────────────────
    def _toggle_medshield(self, on: bool):
        self.medshield_on = on
        txt = "🛡 MedShield: ON" if on else "⚠ MedShield: OFF"
        self._ms_btn.setText(txt)
        self._layer_card.setText("9 / 9 ACTIVE" if on else "0 / 9 ACTIVE")
        self._set_layers("ok" if on else "compromised")

    def _deliver_bolus(self):
        self.current_dose = 2.0
        self.engine.inject(2.0)
        self._scene.set_dose(2.0, blocked=False)
        self._add_command("PatientApp", "Bolus Delivered", "2.0U", "ALLOWED")
        threading.Thread(target=lambda: requests.post(
            f"{BACKEND}/dose",
            json={"units":2.0,"source":"PatientApp",
                  "auth_token":"valid","source_mac":"AA:BB:CC:DD:EE:04"},
            timeout=2), daemon=True).start()

    def _reset(self):
        self.attack_active = False
        self.current_dose  = 2.0
        self.reservoir     = 120.0
        self.engine        = GlucoseEngine()
        self.glucose_hist  = [132.0] * 80
        self.dose_hist     = [2.0]   * 80
        self.risk_hist     = [0.18]  * 80
        self._scene.set_dose(2.0, blocked=False)
        self._set_layers("ok")
        self._sys_card.setText("PROTECTED ✓")
        self._sys_card.setStyleSheet(f"color:{GREEN};font-size:17px;"
                                     f"font-weight:bold;background:transparent;")
        self._shap_lbl.setText("No alerts detected. All commands within safe parameters.")
        self._shap_lbl.setStyleSheet(f"color:{TDIM};font-size:11px;"
                                     f"font-family:'Courier New';background:transparent;")
        self._forensic_lbl.setText("No incidents logged.")
        self._pump_rows["Reservoir"].setText("120.0 U")
        self.commands = [
            (datetime.now().strftime("%H:%M:%S"), "SYSTEM", "Pump Reset", "--", "OK"),
        ]
        self._refresh_table()
        threading.Thread(target=lambda: requests.post(
            f"{BACKEND}/reset", timeout=2), daemon=True).start()

    def _add_command(self, source, cmd, value, status):
        ts = datetime.now().strftime("%H:%M:%S")
        self.commands.append((ts, source, cmd, value, status))
        self.commands = self.commands[-30:]
        self._refresh_table()

    def _refresh_table(self):
        self._cmd_tbl.setRowCount(len(self.commands))
        for i, row in enumerate(reversed(self.commands)):
            ts, src, cmd, val, stat = row
            self._cmd_tbl.setItem(i, 0, QTableWidgetItem(ts))
            self._cmd_tbl.setItem(i, 1, QTableWidgetItem(src))
            self._cmd_tbl.setItem(i, 2, QTableWidgetItem(cmd))
            self._cmd_tbl.setItem(i, 3, QTableWidgetItem(val))
            si = QTableWidgetItem(stat)
            col = (GREEN  if stat == "ALLOWED" else
                   ORANGE if stat == "BLOCKED"  else
                   RED)
            si.setForeground(QColor(col))
            self._cmd_tbl.setItem(i, 4, si)


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MedShieldDashboard()
    win.show()
    sys.exit(app.exec())
