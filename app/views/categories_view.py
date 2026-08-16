from __future__ import annotations
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog,
    QFormLayout, QLineEdit, QTextEdit, QLabel, QMessageBox,
    QColorDialog, QFrame, QFileDialog, QCheckBox, QSpinBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

from app.views.widgets.data_table import DataTable
from app.controllers.category_controller import CategoryController
from config import CATEGORY_IMAGES_DIR
from app.views.dialog_theme import apply_light_dialog_theme


class CategoriesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        toolbar = QHBoxLayout()
        btn_add = QPushButton("＋  Nouvelle catégorie")
        btn_add.clicked.connect(self._add)
        toolbar.addStretch()
        toolbar.addWidget(btn_add)
        layout.addLayout(toolbar)

        self._table = DataTable(["ID", "Nom", "Description", "Couleur", "Image"])
        self._table.itemDoubleClicked.connect(self._edit)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_edit = QPushButton("Modifier")
        btn_edit.setObjectName("btnSecondary")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("Supprimer")
        btn_del.setObjectName("btnDanger")
        btn_del.clicked.connect(self._delete)
        btn_row.addStretch()
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        layout.addLayout(btn_row)

    def refresh(self):
        cats = CategoryController.get_all()
        rows = []
        for c in cats:
            rows.append({**c, "_img_flag": "Oui" if c.get("image_path") else "—"})
        self._table.set_data(rows, ["id", "name", "description", "color", "_img_flag"])
        self._limit_table_height(len(rows))


    def _limit_table_height(self, total_rows: int) -> None:
        visible_rows = max(1, min(int(total_rows or 0), 10))
        header_h = self._table.horizontalHeader().height() or 38
        row_h = 48
        frame_h = 8
        target_h = header_h + (visible_rows * row_h) + frame_h
        self._table.setMinimumHeight(target_h)
        self._table.setMaximumHeight(target_h)

    def _add(self):
        dlg = CategoryDialog(self)
        if dlg.exec():
            self.refresh()

    def _edit(self):
        data = self._table.selected_row_data()
        if not data:
            return
        cat = CategoryController.get_by_id(data["id"])
        dlg = CategoryDialog(self, cat)
        if dlg.exec():
            self.refresh()

    def _delete(self):
        data = self._table.selected_row_data()
        if not data:
            return
        try:
            reply = QMessageBox.question(self, "Supprimer", f"Supprimer «{data['name']}» ?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                CategoryController.delete(data["id"])
                self.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "Impossible", str(e))


class CategoryDialog(QDialog):
    def __init__(self, parent=None, cat: dict = None):
        super().__init__(parent)
        apply_light_dialog_theme(self)
        self._cat = cat
        self._color = cat["color"] if cat else "#4CAF50"
        self._image_path: str | None = cat.get("image_path") if cat else None
        self.setWindowTitle("Modifier" if cat else "Nouvelle catégorie")
        self.setFixedWidth(420)
        self._build_ui()
        if cat:
            self._name.setText(cat["name"])
            self._desc.setPlainText(cat.get("description") or "")
            self._sensitive.setChecked(bool(cat.get("is_sensitive")))
            self._shelf_life.setValue(int(cat.get("shelf_life_days") or 0))
            self._update_color_btn()
            self._update_image_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(10)

        self._name = QLineEdit()
        self._name.setMinimumHeight(42)
        self._desc = QTextEdit()
        self._desc.setMaximumHeight(70)

        self._color_btn = QPushButton("  Choisir une couleur")
        self._color_btn.setObjectName("btnSecondary")
        self._color_btn.clicked.connect(self._pick_color)
        self._update_color_btn()

        # Image row
        img_row = QHBoxLayout()
        img_row.setSpacing(8)
        self._img_preview = QLabel()
        self._img_preview.setFixedSize(72, 72)
        self._img_preview.setAlignment(Qt.AlignCenter)
        self._img_preview.setStyleSheet(
            "border: 2px dashed #D1D5DB; border-radius: 8px; background: #F9FAFB;"
        )
        self._img_preview.setText("")
        self._img_preview.setStyleSheet(
            "QLabel { border: 2px dashed #D1D5DB; border-radius: 8px;"
            "background: #F9FAFB; font-size: 28px; }"
        )

        img_btns = QVBoxLayout()
        img_btns.setSpacing(6)
        btn_pick_img = QPushButton("Choisir image")
        btn_pick_img.setObjectName("btnSecondary")
        btn_pick_img.clicked.connect(self._pick_image)
        btn_clear_img = QPushButton("Supprimer image")
        btn_clear_img.setObjectName("btnDanger")
        btn_clear_img.clicked.connect(self._clear_image)
        img_btns.addWidget(btn_pick_img)
        img_btns.addWidget(btn_clear_img)

        img_row.addWidget(self._img_preview)
        img_row.addLayout(img_btns)
        img_row.addStretch()

        # ── Surveillance à la réception ──────────────────────
        # Configuré sur la catégorie plutôt que sur chaque produit : une règle
        # posée une fois couvre tous les produits laitiers, par exemple.
        self._sensitive = QCheckBox("Produits sensibles (alerte à la réception)")
        self._sensitive.setToolTip(
            "Affiche un rappel de vérification lors de l'ajout au stock d'une livraison."
        )

        self._shelf_life = QSpinBox()
        self._shelf_life.setRange(0, 3650)
        self._shelf_life.setSuffix(" jours")
        self._shelf_life.setSpecialValueText("Non définie")
        self._shelf_life.setMinimumHeight(38)
        self._shelf_life.setToolTip(
            "Durée de conservation après réception. Sert à proposer une date "
            "d'expiration et à signaler les produits qui se gardent peu."
        )

        form.addRow("Nom *:", self._name)
        form.addRow("Description:", self._desc)
        form.addRow("Couleur:", self._color_btn)
        form.addRow("Image:", img_row)
        form.addRow("Surveillance:", self._sensitive)
        form.addRow("Conservation:", self._shelf_life)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setObjectName("btnSecondary")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Enregistrer")
        btn_save.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name()
            self._update_color_btn()

    def _update_color_btn(self):
        self._color_btn.setStyleSheet(
            f"background: {self._color}; color: white; border-radius: 8px;"
        )

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"
        )
        if not path:
            return
        CATEGORY_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        dest = CATEGORY_IMAGES_DIR / Path(path).name
        if Path(path) != dest:
            shutil.copy2(path, dest)
        self._image_path = dest.name
        self._update_image_preview()

    def _clear_image(self):
        self._image_path = None
        self._update_image_preview()

    def _update_image_preview(self):
        if self._image_path:
            img_file = CATEGORY_IMAGES_DIR / self._image_path
            px = QPixmap(str(img_file))
            if not px.isNull():
                self._img_preview.setPixmap(
                    px.scaled(68, 68, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
                self._img_preview.setText("")
                return
        self._img_preview.setPixmap(QPixmap())
        self._img_preview.setText("")

    def _save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Erreur", "Le nom est obligatoire.")
            return
        is_sensitive = self._sensitive.isChecked()
        shelf_life_days = self._shelf_life.value() or None
        try:
            if self._cat:
                CategoryController.update(
                    self._cat["id"], name, self._desc.toPlainText(),
                    self._color, self._image_path,
                    is_sensitive=is_sensitive, shelf_life_days=shelf_life_days,
                )
            else:
                CategoryController.create(
                    name, self._desc.toPlainText(),
                    self._color, self._image_path,
                    is_sensitive=is_sensitive, shelf_life_days=shelf_life_days,
                )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))
