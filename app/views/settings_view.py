from __future__ import annotations
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QMessageBox,
    QFrame,
    QScrollArea,
    QGroupBox,
    QFileDialog,
    QApplication,
)
from PySide6.QtCore import Qt

from app.views.widgets.data_table import DataTable
from app.database.connection import db
from app.database.backup import create_backup, list_backups, restore_backup
from app.controllers.auth_controller import AuthController


class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = {}
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(24)
        layout.setContentsMargins(0, 0, 0, 0)

        store_group = self._make_group("Informations du magasin")
        store_form = QFormLayout()

        self._store_name = QLineEdit()
        self._store_address = QLineEdit()
        self._store_phone = QLineEdit()
        self._currency = QLineEdit()
        self._tax_rate = QLineEdit()
        self._receipt_footer = QLineEdit()
        self._theme = QComboBox()
        self._theme.addItem("Clair", "light")
        self._theme.addItem("Sombre", "dark")

        for widget in [
            self._store_name,
            self._store_address,
            self._store_phone,
            self._currency,
            self._tax_rate,
            self._receipt_footer,
            self._theme,
        ]:
            widget.setMinimumHeight(42)

        store_form.addRow("Nom du magasin:", self._store_name)
        store_form.addRow("Adresse:", self._store_address)
        store_form.addRow("Téléphone:", self._store_phone)
        store_form.addRow("Devise:", self._currency)
        store_form.addRow("Taux TVA (%):", self._tax_rate)
        store_form.addRow("Pied de ticket:", self._receipt_footer)
        store_form.addRow("Thème:", self._theme)
        store_group.layout().addLayout(store_form)

        btn_save_store = QPushButton("Sauvegarder")
        btn_save_store.clicked.connect(self._save_store)
        store_group.layout().addWidget(btn_save_store, 0, Qt.AlignRight)
        layout.addWidget(store_group)

        backup_group = self._make_group("Sauvegardes")

        backup_note = QLabel(
            "Les sauvegardes sont stockées sur cet ordinateur (data/backups). "
            "Si le PC est perdu, volé ou en panne, ces fichiers le sont aussi — "
            "copiez-les régulièrement sur une clé USB ou un cloud pour être "
            "vraiment protégé."
        )
        backup_note.setWordWrap(True)
        backup_note.setStyleSheet("color: #6B7280; font-size: 11px;")
        backup_group.layout().addWidget(backup_note)

        btn_backup = QPushButton("Créer une sauvegarde maintenant")
        btn_backup.setObjectName("btnSuccess")
        btn_backup.clicked.connect(self._do_backup)
        backup_group.layout().addWidget(btn_backup, 0, Qt.AlignLeft)

        self._backup_table = DataTable(["Date", "Nom", "Taille"])
        self._backup_table.setMinimumHeight(180)
        self._backup_table.setMaximumHeight(220)
        backup_group.layout().addWidget(self._backup_table)

        restore_row = QHBoxLayout()
        restore_row.setSpacing(8)
        btn_restore_selected = QPushButton("Restaurer la sauvegarde sélectionnée")
        btn_restore_selected.setObjectName("btnDanger")
        btn_restore_selected.clicked.connect(self._restore_selected)
        btn_restore_file = QPushButton("Restaurer depuis un fichier…")
        btn_restore_file.setObjectName("btnSecondary")
        btn_restore_file.clicked.connect(self._restore_from_file)
        restore_row.addWidget(btn_restore_selected)
        restore_row.addWidget(btn_restore_file)
        restore_row.addStretch()
        backup_group.layout().addLayout(restore_row)

        layout.addWidget(backup_group)

        layout.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        self._refresh_backup_list()

    def _make_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        return group

    def _load_settings(self):
        rows = db.fetchall("SELECT `key` AS `key`, value FROM settings")
        self._settings = {row["key"]: row["value"] for row in rows}

        self._store_name.setText(self._settings.get("store_name", ""))
        self._store_address.setText(self._settings.get("store_address", ""))
        self._store_phone.setText(self._settings.get("store_phone", ""))
        self._currency.setText(self._settings.get("currency", "TND"))
        self._tax_rate.setText(self._settings.get("tax_rate", "0"))
        self._receipt_footer.setText(self._settings.get("receipt_footer", "Merci pour votre visite !"))

        theme_value = self._settings.get("theme", "light")
        index = self._theme.findData(theme_value)
        self._theme.setCurrentIndex(max(0, index))

    def _save_setting(self, key: str, value: str):
        if db.is_mysql():
            db.execute(
                "INSERT INTO settings (`key`, value) VALUES (?, ?) ON DUPLICATE KEY UPDATE value=VALUES(value), updated_at=NOW()",
                (key, value),
            )
        else:
            db.execute("INSERT OR REPLACE INTO settings (`key`, value) VALUES (?, ?)", (key, value))
        AuthController.log("SETTINGS_UPDATE", f"{key} = {value}")

    def _save_store(self):
        self._save_setting("store_name", self._store_name.text())
        self._save_setting("store_address", self._store_address.text())
        self._save_setting("store_phone", self._store_phone.text())
        self._save_setting("currency", self._currency.text() or "TND")
        self._save_setting("tax_rate", self._tax_rate.text() or "0")
        self._save_setting("receipt_footer", self._receipt_footer.text())

        selected_theme = self._theme.currentData()
        self._save_setting("theme", selected_theme)

        window = self.window()
        if hasattr(window, "_apply_theme"):
            window._apply_theme(selected_theme)

        QMessageBox.information(self, "Succès", "Paramètres sauvegardés.")

    def _do_backup(self):
        try:
            path = create_backup()
            QMessageBox.information(self, "Sauvegarde", f"Sauvegarde créée :\n{path}")
            self._refresh_backup_list()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    def _refresh_backup_list(self):
        backups = list_backups()
        rows = [{**b, "size": b["size_label"]} for b in backups]
        self._backup_table.set_data(rows, ["date", "name", "size"])

    def _restore_selected(self):
        row = self._backup_table.selected_row_data()
        if not row:
            QMessageBox.information(self, "Restauration", "Sélectionnez d'abord une sauvegarde dans la liste.")
            return
        self._confirm_and_restore(row["path"], row["name"])

    def _restore_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un fichier de sauvegarde",
            "",
            "Sauvegardes (*.db *.sql);;Tous les fichiers (*)",
        )
        if not path:
            return
        self._confirm_and_restore(path, Path(path).name)

    def _confirm_and_restore(self, backup_path: str, backup_name: str):
        reply = QMessageBox.warning(
            self,
            "Confirmer la restauration",
            f"Restaurer « {backup_name} » va remplacer TOUTES les données "
            "actuelles (produits, ventes, clients, stock...) par celles de "
            "cette sauvegarde. Cette action est irréversible.\n\n"
            "Si des ventes ou modifications ont eu lieu depuis cette "
            "sauvegarde, elles seront perdues.\n\n"
            "Continuer ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            restore_backup(backup_path)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"La restauration a échoué :\n{e}")
            return

        QMessageBox.information(
            self,
            "Restauration terminée",
            "Les données ont été restaurées. L'application va maintenant se "
            "fermer — relancez-la pour utiliser les données restaurées.",
        )
        QApplication.instance().quit()
