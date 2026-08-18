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
    QCheckBox,
)
from PySide6.QtCore import Qt

from app.views.widgets.data_table import DataTable
from app.database.connection import db
from app.database.backup import create_backup, list_backups, restore_backup
from app.controllers.auth_controller import AuthController
from app.utils import receipt_printer


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

        # ── Impression des tickets ────────────────────────────────────────
        print_group = self._make_group("Impression des tickets")

        print_note = QLabel(
            "Le ticket part directement à l'imprimante après chaque vente, "
            "sans fenêtre à valider. Laissez « Imprimante par défaut de "
            "Windows » si vous n'avez qu'une seule imprimante."
        )
        print_note.setWordWrap(True)
        print_note.setStyleSheet("color: #6B7280; font-size: 11px;")
        print_group.layout().addWidget(print_note)

        print_form = QFormLayout()
        self._auto_print = QCheckBox("Imprimer le ticket automatiquement après chaque vente")
        print_form.addRow("", self._auto_print)

        self._printer = QComboBox()
        self._printer.setMinimumHeight(42)
        self._printer.currentIndexChanged.connect(self._check_printer_kind)
        print_form.addRow("Imprimante :", self._printer)
        print_group.layout().addLayout(print_form)

        self._printer_warning = QLabel()
        self._printer_warning.setWordWrap(True)
        self._printer_warning.setVisible(False)
        self._printer_warning.setStyleSheet(
            "background: #FEF3C7; color: #92400E; border: 1px solid #FCD34D;"
            "border-radius: 8px; padding: 10px 12px; font-size: 12px;"
        )
        print_group.layout().addWidget(self._printer_warning)

        print_buttons = QHBoxLayout()
        btn_refresh_printers = QPushButton("Rechercher les imprimantes")
        btn_refresh_printers.setObjectName("btnSecondary")
        btn_refresh_printers.clicked.connect(self._load_printers)
        btn_test_print = QPushButton("Imprimer une page de test")
        btn_test_print.setObjectName("btnSecondary")
        btn_test_print.clicked.connect(self._test_print)
        btn_save_print = QPushButton("Enregistrer")
        btn_save_print.clicked.connect(self._save_print_settings)
        print_buttons.addWidget(btn_refresh_printers)
        print_buttons.addWidget(btn_test_print)
        print_buttons.addStretch()
        print_buttons.addWidget(btn_save_print)
        print_group.layout().addLayout(print_buttons)
        layout.addWidget(print_group)

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

        # Impression activée par défaut : une caisse qui n'imprime pas ne
        # rend pas service, mieux vaut que ce soit à désactiver qu'à trouver.
        self._auto_print.setChecked(self._settings.get("receipt_auto_print", "1") != "0")
        self._load_printers(self._settings.get("receipt_printer", ""))

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

    # ── Impression ────────────────────────────────────────────────────

    def _load_printers(self, selected: str | None = None) -> None:
        """Remplit la liste des imprimantes du poste.

        L'entrée vide en tête correspond à « imprimante par défaut de
        Windows » : c'est le choix qui survit à un changement de matériel,
        puisqu'il ne fige aucun nom.
        """
        wanted = selected if selected is not None else (self._printer.currentData() or "")
        self._printer.blockSignals(True)
        self._printer.clear()
        defaut = receipt_printer.default_printer_name()
        self._printer.addItem(
            f"Imprimante par défaut de Windows ({defaut})" if defaut
            else "Imprimante par défaut de Windows (aucune détectée)",
            "",
        )
        for name in receipt_printer.available_printers():
            self._printer.addItem(name, name)

        index = self._printer.findData(wanted)
        if index < 0 and wanted:
            # L'imprimante enregistrée n'est plus branchée : on la garde
            # visible plutôt que de la remplacer en douce par une autre.
            self._printer.addItem(f"{wanted}  (non détectée)", wanted)
            index = self._printer.count() - 1
        self._printer.setCurrentIndex(max(0, index))
        self._printer.blockSignals(False)
        self._check_printer_kind()

    def _check_printer_kind(self) -> None:
        """Prévient si l'imprimante retenue produit un fichier au lieu de papier.

        Sur un PC neuf, l'imprimante par défaut de Windows est souvent
        « Microsoft Print to PDF ». Sans cet avertissement, le caissier
        découvre le problème en production, avec une fenêtre
        « Enregistrer sous » à chaque vente.
        """
        used = receipt_printer.effective_printer_name(self._printer.currentData() or "")
        if not used:
            self._printer_warning.setText(
                "Aucune imprimante n'est installée sur ce poste : le ticket "
                "ne pourra pas s'imprimer."
            )
            self._printer_warning.setVisible(True)
            return
        if receipt_printer.is_virtual_printer(used):
            self._printer_warning.setText(
                f"« {used} » n'imprime pas sur papier : elle enregistre un "
                "fichier PDF et demande où le ranger à chaque vente.\n\n"
                "Pour une vraie caisse, branchez l'imprimante à tickets et "
                "sélectionnez-la ci-dessus (ou définissez-la comme imprimante "
                "par défaut dans Windows)."
            )
            self._printer_warning.setVisible(True)
            return
        self._printer_warning.setVisible(False)

    def _save_print_settings(self):
        self._save_setting("receipt_auto_print", "1" if self._auto_print.isChecked() else "0")
        self._save_setting("receipt_printer", self._printer.currentData() or "")
        QMessageBox.information(self, "Succès", "Réglages d'impression enregistrés.")

    def _test_print(self):
        """Imprime le dernier ticket réel, ou une page de test à défaut."""
        printer_name = self._printer.currentData() or ""
        try:
            from app.controllers.sale_controller import SaleController
            from app.utils.exporter import generate_thermal_receipt

            row = db.fetchone("SELECT MAX(id) AS id FROM sales WHERE status='completed'")
            sale_id = (row or {}).get("id")
            if not sale_id:
                QMessageBox.information(
                    self,
                    "Impression de test",
                    "Aucune vente n'existe encore : enregistrez une vente, "
                    "puis relancez le test.",
                )
                return

            settings = {r["key"]: r["value"]
                        for r in db.fetchall("SELECT `key` AS `key`, value FROM settings")}
            pdf_path = generate_thermal_receipt(SaleController.get_by_id(sale_id), settings)
            used = receipt_printer.print_pdf(pdf_path, printer_name)
        except Exception as exc:
            QMessageBox.critical(self, "Impression impossible", str(exc))
            return

        QMessageBox.information(
            self,
            "Impression lancée",
            f"Le ticket a été envoyé à « {used} ».\n\n"
            "S'il ne sort pas, vérifiez que l'imprimante est allumée, "
            "chargée en papier et sélectionnée ci-dessus.",
        )

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
