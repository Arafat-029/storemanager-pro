from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QTabWidget, QWidget,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap

try:
    import cv2
    import numpy as np
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

# pyzbar: best for 1D codes — explicitly exclude PDF417 to avoid the
# "Assertion g[0]>=0" crash that occurs when pyzbar tries to decode PDF417.
try:
    from pyzbar.pyzbar import decode as _pyzbar_decode, ZBarSymbol as _ZBS
    _SAFE_SYMS = [
        getattr(_ZBS, n, None)
        for n in ("EAN8", "EAN13", "UPCA", "UPCE", "CODE128", "CODE39",
                  "I25", "CODABAR", "QRCODE", "ISBN10", "ISBN13", "CODE93")
    ]
    _SAFE_SYMS = [s for s in _SAFE_SYMS if s is not None]
    if _CV2_OK:
        _pyzbar_decode(np.zeros((10, 10, 3), dtype=np.uint8), symbols=_SAFE_SYMS)
    _PYZBAR_OK = True
except Exception:
    _PYZBAR_OK = False
    _SAFE_SYMS = []

_HAS_BARCODE = _CV2_OK and hasattr(cv2, "barcode")

SCANNER_AVAILABLE = _CV2_OK
CV2_AVAILABLE = _CV2_OK

# ── Detection helpers ──────────────────────────────────────────────────────────

def _decode_pyzbar(frame):
    if not _PYZBAR_OK:
        return []
    try:
        hits = _pyzbar_decode(frame, symbols=_SAFE_SYMS)
        return [(h.data.decode("utf-8", errors="replace").strip(),
                 [(p.x, p.y) for p in h.polygon])
                for h in hits if h.data]
    except Exception:
        return []


def _decode_cv_barcode(frame):
    if not _HAS_BARCODE:
        return []
    try:
        det = cv2.barcode.BarcodeDetector()
        ret, decoded_info, _, points = det.detectAndDecode(frame)
        if not ret or not decoded_info:
            return []
        results = []
        for i, text in enumerate(decoded_info):
            if not text:
                continue
            pts = [(int(p[0]), int(p[1])) for p in points[i]] if points is not None and i < len(points) else []
            results.append((text, pts))
        return results
    except Exception:
        return []


def _decode_qr(frame):
    if not _CV2_OK:
        return []
    try:
        data, bbox, _ = cv2.QRCodeDetector().detectAndDecode(frame)
        if data and bbox is not None:
            return [(data, [(int(p[0]), int(p[1])) for p in bbox[0]])]
    except Exception:
        pass
    return []


def _try_all(frame):
    return _decode_pyzbar(frame) or _decode_cv_barcode(frame) or _decode_qr(frame)


def _decode_frame(frame):
    results = _try_all(frame)
    if results:
        return results

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_bgr = cv2.cvtColor(clahe.apply(gray), cv2.COLOR_GRAY2BGR)
    results = _try_all(enhanced_bgr)
    if results:
        return results

    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharp_bgr = cv2.cvtColor(cv2.filter2D(clahe.apply(gray), -1, kernel), cv2.COLOR_GRAY2BGR)
    results = _try_all(sharp_bgr)
    if results:
        return results

    h, w = frame.shape[:2]
    big = cv2.resize(frame, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    return _try_all(big)


def _draw_overlay(frame, pts, text: str):
    if len(pts) >= 4:
        cv2.polylines(frame, [np.array(pts, dtype=np.int32)], True, (0, 150, 80), 3)
        x, y = pts[0]
    elif pts:
        x, y = pts[0]
    else:
        return
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(frame, (x, y - th - 14), (x + tw + 8, y - 2), (0, 150, 80), -1)
    cv2.putText(frame, text, (x + 4, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def _draw_viewfinder(frame):
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    rw, rh = int(w * 0.55), int(h * 0.45)
    x1, y1 = cx - rw // 2, cy - rh // 2
    x2, y2 = cx + rw // 2, cy + rh // 2
    color, t, corner = (0, 150, 80), 3, 22

    for (px, py, dx, dy) in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
        cv2.line(frame, (px, py), (px + dx * corner, py), color, t)
        cv2.line(frame, (px, py), (px, py + dy * corner), color, t)

    overlay = frame.copy()
    for rect in [(0,0,w,y1),(0,y2,w,h),(0,y1,x1,y2),(x2,y1,w,y2)]:
        cv2.rectangle(overlay, rect[:2], rect[2:], (0,0,0), -1)
    cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

    hint = "Centrez le code-barres dans le cadre"
    (tw, _), _ = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    cv2.putText(frame, hint, (cx - tw // 2, y2 + 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 200, 160), 1)


# ── Dialog ─────────────────────────────────────────────────────────────────────

class BarcodeScannerDialog(QDialog):
    """Camera barcode/QR scanner.
    Supports:
      - PC webcam (local camera index 0/1)
      - Smartphone via IP Webcam app (WiFi stream URL)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scanner code-barres / QR")
        self.setMinimumSize(640, 580)
        self.setModal(True)

        self._cap = None
        self._result = ""
        self._frame_count = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._process_frame)

        self._build_ui()

        if CV2_AVAILABLE:
            self._start_camera(source=0)
        else:
            self._show_fallback("opencv-python non installé.\npip install opencv-contrib-python")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #059669, stop:1 #047857); }"
        )
        hdr.setFixedHeight(52)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        title = QLabel("📷  Scanner code-barres / QR code")
        title.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: white; background: transparent; border: none;"
        )
        hl.addWidget(title)
        layout.addWidget(hdr)

        # Camera view
        self._camera_label = QLabel()
        self._camera_label.setAlignment(Qt.AlignCenter)
        self._camera_label.setMinimumSize(640, 360)
        self._camera_label.setStyleSheet(
            "background: #111827; color: #6B7280; font-size: 13px; border: none;"
        )
        self._camera_label.setText("Initialisation caméra…")
        layout.addWidget(self._camera_label, 1)

        # Status bar
        status_frame = QFrame()
        status_frame.setStyleSheet(
            "QFrame { background: #F9FAFB; border-top: 1px solid #E5E7EB; }"
        )
        status_frame.setFixedHeight(36)
        sl = QHBoxLayout(status_frame)
        sl.setContentsMargins(16, 0, 16, 0)
        self._status = QLabel("⏳  Initialisation…")
        self._status.setStyleSheet("color: #6B7280; font-size: 12px; background: transparent; border: none;")

        lib_txt = "✓ pyzbar" if _PYZBAR_OK else ("✓ cv2.barcode" if _HAS_BARCODE else "⚠ installer opencv-contrib-python")
        lib_color = "#059669" if (_PYZBAR_OK or _HAS_BARCODE) else "#D97706"
        lib_lbl = QLabel(lib_txt)
        lib_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lib_lbl.setStyleSheet(f"color: {lib_color}; font-size: 11px; background: transparent; border: none;")
        sl.addWidget(self._status, 1)
        sl.addWidget(lib_lbl)
        layout.addWidget(status_frame)

        # ── Source selector tabs ──────────────────────────────
        source_frame = QFrame()
        source_frame.setStyleSheet(
            "QFrame { background: #FFFFFF; border-top: 1px solid #E5E7EB; }"
        )
        src_layout = QVBoxLayout(source_frame)
        src_layout.setContentsMargins(16, 10, 16, 10)
        src_layout.setSpacing(8)

        src_title = QLabel("Source de la caméra :")
        src_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #374151; background: transparent; border: none;")
        src_layout.addWidget(src_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_pc = QPushButton("💻  Webcam PC")
        self._btn_pc.setMinimumHeight(36)
        self._btn_pc.setCheckable(True)
        self._btn_pc.setChecked(True)
        self._btn_pc.setStyleSheet(self._tab_style(True))
        self._btn_pc.clicked.connect(self._use_pc_camera)

        self._btn_phone = QPushButton("📱  Smartphone (WiFi)")
        self._btn_phone.setMinimumHeight(36)
        self._btn_phone.setCheckable(True)
        self._btn_phone.setStyleSheet(self._tab_style(False))
        self._btn_phone.clicked.connect(self._show_phone_row)

        btn_row.addWidget(self._btn_pc)
        btn_row.addWidget(self._btn_phone)
        btn_row.addStretch()
        src_layout.addLayout(btn_row)

        # Phone URL row (hidden by default)
        self._phone_row = QWidget()
        phone_layout = QHBoxLayout(self._phone_row)
        phone_layout.setContentsMargins(0, 0, 0, 0)
        phone_layout.setSpacing(8)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("http://192.168.1.100:8080/video  (IP Webcam)")
        self._url_input.setMinimumHeight(38)
        self._url_input.setStyleSheet(
            "background: #F9FAFB; border: 1.5px solid #D1D5DB; border-radius: 8px;"
            "padding: 8px 12px; color: #111827; font-size: 13px;"
        )
        self._url_input.returnPressed.connect(self._connect_phone)

        btn_connect = QPushButton("Connecter")
        btn_connect.setMinimumHeight(38)
        btn_connect.setMinimumWidth(100)
        btn_connect.clicked.connect(self._connect_phone)

        phone_layout.addWidget(QLabel("URL :"))
        phone_layout.addWidget(self._url_input, 1)
        phone_layout.addWidget(btn_connect)
        self._phone_row.hide()
        src_layout.addWidget(self._phone_row)

        layout.addWidget(source_frame)

        # Phone setup instructions (hidden by default)
        self._instructions = QFrame()
        self._instructions.setStyleSheet(
            "QFrame { background: #EFF6FF; border-top: 1px solid #BFDBFE; }"
            "QLabel { background: transparent; border: none; color: #1E40AF; }"
        )
        inst_layout = QVBoxLayout(self._instructions)
        inst_layout.setContentsMargins(16, 10, 16, 10)
        inst_layout.setSpacing(4)
        inst_lbl = QLabel(
            "📱  Configuration smartphone Android :\n"
            "1. Installez l'app  IP Webcam  (Play Store, gratuite)\n"
            "2. Lancez l'app → appuyez sur  Démarrer le serveur\n"
            "3. Notez l'URL affichée (ex: http://192.168.1.100:8080)\n"
            "4. Saisissez cette URL ci-dessus et cliquez  Connecter\n\n"
            "📱  iPhone : utilisez  EpocCam  ou  DroidCam  (App Store)"
        )
        inst_lbl.setStyleSheet("font-size: 12px; color: #1E40AF; background: transparent; border: none;")
        inst_lbl.setWordWrap(True)
        inst_layout.addWidget(inst_lbl)
        self._instructions.hide()
        layout.addWidget(self._instructions)

        # Manual entry
        manual_frame = QFrame()
        manual_frame.setStyleSheet(
            "QFrame { background: #F9FAFB; border-top: 1px solid #E5E7EB; }"
            "QLabel { background: transparent; border: none; color: #6B7280; }"
        )
        ml = QHBoxLayout(manual_frame)
        ml.setContentsMargins(16, 10, 16, 10)
        ml.setSpacing(8)

        manual_lbl = QLabel("Saisie manuelle :")
        manual_lbl.setFixedWidth(115)

        self._manual_input = QLineEdit()
        self._manual_input.setPlaceholderText("Code-barres ou référence produit…")
        self._manual_input.setMinimumHeight(40)
        self._manual_input.setStyleSheet(
            "background: #FFFFFF; border: 1.5px solid #D1D5DB; border-radius: 8px;"
            "padding: 8px 12px; color: #111827; font-size: 13px;"
        )
        self._manual_input.returnPressed.connect(self._manual_confirm)

        btn_ok = QPushButton("Valider")
        btn_ok.setMinimumHeight(40)
        btn_ok.setMinimumWidth(90)
        btn_ok.clicked.connect(self._manual_confirm)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(40)
        btn_close.setMinimumWidth(80)
        btn_close.setStyleSheet(
            "QPushButton { background: transparent; color: #6B7280;"
            "border: 1.5px solid #D1D5DB; border-radius: 8px; font-size: 13px; }"
            "QPushButton:hover { border-color: #DC2626; color: #DC2626; }"
        )
        btn_close.clicked.connect(self._on_cancel)

        ml.addWidget(manual_lbl)
        ml.addWidget(self._manual_input, 1)
        ml.addWidget(btn_ok)
        ml.addWidget(btn_close)
        layout.addWidget(manual_frame)

    @staticmethod
    def _tab_style(active: bool) -> str:
        if active:
            return (
                "QPushButton { background: #059669; color: white; border: none;"
                "border-radius: 8px; font-weight: 700; font-size: 13px; }"
            )
        return (
            "QPushButton { background: transparent; color: #6B7280;"
            "border: 1.5px solid #D1D5DB; border-radius: 8px; font-size: 13px; }"
            "QPushButton:hover { border-color: #059669; color: #059669; }"
        )

    def _use_pc_camera(self):
        self._btn_pc.setStyleSheet(self._tab_style(True))
        self._btn_phone.setStyleSheet(self._tab_style(False))
        self._btn_pc.setChecked(True)
        self._btn_phone.setChecked(False)
        self._phone_row.hide()
        self._instructions.hide()
        self.adjustSize()
        self._start_camera(source=0)

    def _show_phone_row(self):
        self._btn_phone.setStyleSheet(self._tab_style(True))
        self._btn_pc.setStyleSheet(self._tab_style(False))
        self._btn_phone.setChecked(True)
        self._btn_pc.setChecked(False)
        self._phone_row.show()
        self._instructions.show()
        self.adjustSize()
        self._stop_camera()
        self._camera_label.setText(
            "Entrez l'URL de votre smartphone ci-dessous\npuis cliquez sur  Connecter"
        )
        self._status.setText("📱  En attente de connexion smartphone…")

    def _connect_phone(self):
        url = self._url_input.text().strip()
        if not url:
            self._status.setText("⚠  Entrez l'URL de l'app IP Webcam")
            return
        # Accept base URL (add /video) or full URL
        if not url.endswith("/video") and not url.endswith("/shot.jpg"):
            url = url.rstrip("/") + "/video"
        self._status.setText(f"⏳  Connexion à {url}…")
        self._start_camera(source=url)

    def _start_camera(self, source):
        self._stop_camera()

        if isinstance(source, int):
            # Try local camera indices
            for idx in (source, 1) if source == 0 else (source,):
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                    self._cap = cap
                    break
            if not self._cap:
                cap = cv2.VideoCapture(0)
                if cap.isOpened():
                    self._cap = cap
        else:
            # IP stream (smartphone)
            cap = cv2.VideoCapture(source)
            if cap.isOpened():
                self._cap = cap

        if not self._cap or not self._cap.isOpened():
            self._camera_label.setText(
                "Caméra non disponible.\n\n"
                "Vérifiez la connexion ou utilisez la saisie manuelle."
            )
            self._status.setText("⚠  Caméra non disponible")
            return

        self._timer.start(40)  # 25 fps
        self._status.setText("🔍  Pointez un code-barres dans le cadre…")
        self._status.setStyleSheet(
            "color: #059669; font-size: 12px; background: transparent; border: none;"
        )

    def _process_frame(self):
        if not self._cap or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return

        self._frame_count += 1
        _draw_viewfinder(frame)

        results = _decode_frame(frame)
        if results:
            text, pts = results[0]
            _draw_overlay(frame, pts, text)
            self._status.setText(f"✅  Détecté : {text}")
            self._display_frame(frame)
            QTimer.singleShot(400, lambda: self._finish(text))
            return

        if self._frame_count % 15 == 0:
            dots = "." * ((self._frame_count // 15) % 4)
            self._status.setText(f"🔍  Scan en cours{dots}")

        self._display_frame(frame)

    def _display_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._camera_label.setPixmap(
            QPixmap.fromImage(img).scaled(
                self._camera_label.width(), self._camera_label.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        )

    def _show_fallback(self, message: str):
        self._camera_label.setText(message)
        self._status.setText("⚠  Saisie manuelle uniquement")

    def _manual_confirm(self):
        code = self._manual_input.text().strip()
        if code:
            self._finish(code)
        else:
            self._manual_input.setFocus()

    def _finish(self, code: str):
        self._result = code
        self._stop_camera()
        self.accept()

    def _on_cancel(self):
        self._stop_camera()
        self.reject()

    def _stop_camera(self):
        self._timer.stop()
        if self._cap:
            self._cap.release()
            self._cap = None

    def get_result(self) -> str:
        return self._result

    def closeEvent(self, event):
        self._stop_camera()
        super().closeEvent(event)
