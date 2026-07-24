from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

LIGHT_DIALOG_QSS = """
QDialog {
    background: #FFFFFF;
    color: #1B2A4A;
    border: 1px solid #E0E6EF;
    border-radius: 14px;
}
QDialog > QWidget,
QDialog QWidget,
QDialog QFrame,
QDialog QScrollArea,
QDialog QScrollArea > QWidget,
QDialog QScrollArea > QWidget > QWidget {
    background: transparent;
    color: #111827;
}
QLabel, QDialog QLabel {
    background: transparent;
    color: #1B2A4A;
    border: none;
    font-size: 12px;
    font-weight: 600;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QDateEdit, QListWidget {
    background: #F8FAFC;
    color: #1B2A4A;
    border: 1.5px solid #CBD5E1;
    border-radius: 10px;
    padding: 10px 12px;
    min-height: 40px;
    selection-background-color: #2196F3;
    selection-color: #FFFFFF;
}
QComboBox {
    padding-right: 52px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 40px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    width: 12px;
    height: 12px;
    margin-right: 14px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QDateEdit:focus, QListWidget:focus {
    border-color: #2196F3;
    background: #FFFFFF;
}
QLineEdit::placeholder-text, QTextEdit {
    color: #111827;
}
QPushButton {
    background: #2563EB;
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 700;
    min-height: 40px;
}
QPushButton:hover {
    background: #1D4ED8;
}
QPushButton:pressed {
    background: #1E40AF;
}
QPushButton:disabled {
    background: #E5E7EB;
    color: #9CA3AF;
}
QPushButton#btnSecondary, QPushButton[cssClass="btnSecondary"] {
    background: transparent;
    border: 1.5px solid #CBD5E1;
    color: #475569;
}
QPushButton#btnSecondary:hover, QPushButton[cssClass="btnSecondary"]:hover {
    background: #F8FAFC;
    border-color: #2196F3;
    color: #1B2A4A;
}
QPushButton#btnDanger, QPushButton[cssClass="btnDanger"] {
    background: #E91E63;
    color: #FFFFFF;
}
QPushButton#btnDanger:hover, QPushButton[cssClass="btnDanger"]:hover {
    background: #F43F5E;
}
QPushButton#btnSuccess, QPushButton[cssClass="btnSuccess"] {
    background: #2563EB;
    color: #FFFFFF;
}
QPushButton#btnWarning, QPushButton[cssClass="btnWarning"] {
    background: #D97706;
    color: #FFFFFF;
}
QTableWidget, QListWidget {
    background: #FFFFFF;
    color: #111827;
    border: 1.5px solid #E5E7EB;
    border-radius: 10px;
    alternate-background-color: #F9FAFB;
    gridline-color: #F3F4F6;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #111827;
    border: 1.5px solid #E5E7EB;
    border-radius: 10px;
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 28px;
    padding: 4px 10px;
    border-radius: 6px;
    background: #FFFFFF;
    color: #111827;
}
QComboBox QAbstractItemView::item:hover {
    background: #E0F2FE;
    color: #0F172A;
}
QComboBox QAbstractItemView::item:selected {
    background: #DBEAFE;
    color: #1D4ED8;
}
QTableWidget::item, QListWidget::item {
    background: transparent;
    color: #111827;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background: rgba(16, 185, 129, 0.12);
    color: #111827;
}
QHeaderView::section {
    background: #F9FAFB;
    color: #6B7280;
    border: none;
    border-bottom: 1px solid #E5E7EB;
    padding: 8px 10px;
    font-size: 11px;
    font-weight: 700;
}
QMessageBox,
QMessageBox QWidget {
    background: #162447;
    color: #F8FAFC;
}
QMessageBox QLabel {
    color: #F8FAFC;
    font-size: 13px;
    font-weight: 600;
}
QMessageBox QPushButton {
    min-width: 96px;
    min-height: 36px;
    padding: 8px 16px;
    background: #2563EB;
    color: #FFFFFF;
    border: 1px solid #60A5FA;
    border-radius: 8px;
}
QMessageBox QPushButton:hover {
    background: #3B82F6;
}
QMessageBox QPushButton:pressed {
    background: #1D4ED8;
}
"""

DARK_DIALOG_QSS = """
QDialog {
    background: #0D1525;
    color: #E2E8F0;
    border: 1px solid #1A2744;
    border-radius: 14px;
}
QDialog > QWidget,
QDialog QWidget,
QDialog QFrame,
QDialog QScrollArea,
QDialog QScrollArea > QWidget,
QDialog QScrollArea > QWidget > QWidget {
    background: transparent;
    color: #E5E7EB;
}
QLabel, QDialog QLabel {
    background: transparent;
    color: #E2E8F0;
    border: none;
    font-size: 12px;
    font-weight: 600;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QDateEdit, QListWidget {
    background: #111B2E;
    color: #F8FAFC;
    border: 1.5px solid #1A2744;
    border-radius: 10px;
    padding: 10px 12px;
    min-height: 40px;
    selection-background-color: #1E88E5;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QDateEdit:focus, QListWidget:focus {
    border-color: #1E88E5;
    background: #152238;
}
QPushButton {
    background: #2563EB;
    color: #FFFFFF;
    border: none;
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 700;
    min-height: 40px;
}
QPushButton:hover {
    background: #1D4ED8;
}
QPushButton:pressed {
    background: #1E40AF;
}
QPushButton#btnSecondary, QPushButton[cssClass="btnSecondary"] {
    background: transparent;
    border: 1.5px solid #334155;
    color: #CBD5E1;
}
QPushButton#btnSecondary:hover, QPushButton[cssClass="btnSecondary"]:hover {
    background: #111B2E;
    border-color: #1E88E5;
    color: #F8FAFC;
}
QPushButton#btnDanger, QPushButton[cssClass="btnDanger"] {
    background: #DC2626;
    color: #FFFFFF;
}
QPushButton#btnSuccess, QPushButton[cssClass="btnSuccess"] {
    background: #2563EB;
    color: #FFFFFF;
}
"""


def apply_dialog_theme(dialog: QDialog, dark: bool = False) -> None:
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.setStyleSheet(DARK_DIALOG_QSS if dark else LIGHT_DIALOG_QSS)


def apply_light_dialog_theme(dialog: QDialog) -> None:
    apply_dialog_theme(dialog, False)


def apply_light_messagebox_theme(box: QMessageBox) -> QMessageBox:
    box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    box.setStyleSheet(LIGHT_DIALOG_QSS)
    return box

def light_messagebox(
    parent,
    icon: QMessageBox.Icon,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.Ok,
    default_button: QMessageBox.StandardButton = QMessageBox.NoButton,
) -> QMessageBox.StandardButton:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    if default_button != QMessageBox.NoButton:
        box.setDefaultButton(default_button)
    apply_light_messagebox_theme(box)
    return QMessageBox.StandardButton(box.exec())

def light_question(
    parent,
    title: str,
    text: str,
    buttons: QMessageBox.StandardButton = QMessageBox.Yes | QMessageBox.No,
    default_button: QMessageBox.StandardButton = QMessageBox.No,
) -> QMessageBox.StandardButton:
    return light_messagebox(parent, QMessageBox.Question, title, text, buttons, default_button)

def light_information(parent, title: str, text: str) -> QMessageBox.StandardButton:
    return light_messagebox(parent, QMessageBox.Information, title, text)

def light_warning(parent, title: str, text: str) -> QMessageBox.StandardButton:
    return light_messagebox(parent, QMessageBox.Warning, title, text)

def light_critical(parent, title: str, text: str) -> QMessageBox.StandardButton:
    return light_messagebox(parent, QMessageBox.Critical, title, text)
