from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap

from app.views.widgets.screen_fit import clamp_min_size
from app.utils.barcode_scanner import CV2_AVAILABLE

if CV2_AVAILABLE:
    import cv2


class PhotoCaptureDialog(QDialog):
    """Take a product photo directly from a connected camera.

    Live preview until "Capturer" freezes the current frame; the user then
    either keeps it or retakes it — the same capture-then-confirm flow as a
    phone camera app, so a blurry or mistimed frame is never saved by
    accident. Reuses the same OpenCV availability check and camera-opening
    strategy as BarcodeScannerDialog (DSHOW backend, index 0 then 1).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prendre une photo")
        clamp_min_size(self, 560, 520)
        self.setModal(True)

        self._cap = None
        self._image: QImage | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._process_frame)

        self._build_ui()

        if CV2_AVAILABLE:
            self._start_camera()
        else:
            self._show_unavailable("opencv-python non installé.\npip install opencv-contrib-python")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QFrame()
        hdr.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #059669, stop:1 #047857); }"
        )
        hdr.setFixedHeight(48)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        title = QLabel("Prendre une photo du produit")
        title.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: white; background: transparent; border: none;"
        )
        hl.addWidget(title)
        layout.addWidget(hdr)

        self._view = QLabel()
        self._view.setAlignment(Qt.AlignCenter)
        self._view.setMinimumSize(560, 380)
        self._view.setStyleSheet(
            "background: #111827; color: #9CA3AF; font-size: 13px; border: none;"
        )
        self._view.setText("Initialisation caméra…")
        layout.addWidget(self._view, 1)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setStyleSheet("color: #6B7280; font-size: 12px; padding: 6px; background: transparent; border: none;")
        layout.addWidget(self._status)

        footer = QFrame()
        footer.setStyleSheet("QFrame { background: #F9FAFB; border-top: 1px solid #E5E7EB; }")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)

        self._btn_cancel = QPushButton("Annuler")
        self._btn_cancel.setMinimumHeight(38)
        self._btn_cancel.setStyleSheet(
            "QPushButton { background: transparent; color: #6B7280;"
            "border: 1.5px solid #D1D5DB; border-radius: 8px; }"
            "QPushButton:hover { border-color: #DC2626; color: #DC2626; }"
        )
        self._btn_cancel.clicked.connect(self._on_cancel)

        self._btn_retake = QPushButton("Reprendre")
        self._btn_retake.setMinimumHeight(38)
        self._btn_retake.setObjectName("btnSecondary")
        self._btn_retake.clicked.connect(self._retake)
        self._btn_retake.hide()

        self._btn_capture = QPushButton("Capturer")
        self._btn_capture.setMinimumHeight(38)
        self._btn_capture.clicked.connect(self._capture)

        self._btn_use = QPushButton("Utiliser cette photo")
        self._btn_use.setMinimumHeight(38)
        self._btn_use.setObjectName("btnSuccess")
        self._btn_use.clicked.connect(self._confirm)
        self._btn_use.hide()

        fl.addWidget(self._btn_cancel)
        fl.addStretch()
        fl.addWidget(self._btn_retake)
        fl.addWidget(self._btn_capture)
        fl.addWidget(self._btn_use)
        layout.addWidget(footer)

    def _start_camera(self):
        for idx in (0, 1):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                self._cap = cap
                break
            cap.release()

        if not self._cap:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                self._cap = cap

        if not self._cap or not self._cap.isOpened():
            self._show_unavailable("Aucune caméra détectée.")
            return

        self._status.setText("Cadrez le produit puis cliquez sur Capturer")
        self._timer.start(40)  # 25 fps

    def _process_frame(self):
        if not self._cap or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return
        self._display_frame(frame)

    def _display_frame(self, frame) -> QImage:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        # .copy() so the QImage owns its bytes independently of *rgb*, which
        # goes out of scope (and can be reused/freed by OpenCV) right after
        # this call returns — needed here since, unlike the live-preview
        # path, a captured frame's QImage is kept around after this returns.
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
        self._view.setPixmap(
            QPixmap.fromImage(img).scaled(
                self._view.width(), self._view.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        )
        return img

    def _capture(self):
        if not self._cap or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret or frame is None:
            return
        self._timer.stop()
        self._image = self._display_frame(frame)
        self._btn_capture.hide()
        self._btn_retake.show()
        self._btn_use.show()
        self._status.setText("Photo capturée — utiliser ou reprendre ?")

    def _retake(self):
        self._image = None
        self._btn_retake.hide()
        self._btn_use.hide()
        self._btn_capture.show()
        self._status.setText("Cadrez le produit puis cliquez sur Capturer")
        self._timer.start(40)

    def _confirm(self):
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

    def _show_unavailable(self, message: str):
        self._view.setText(message)
        self._status.setText("")
        self._btn_capture.setEnabled(False)

    def captured_image(self) -> QImage | None:
        return self._image

    def closeEvent(self, event):
        self._stop_camera()
        super().closeEvent(event)
