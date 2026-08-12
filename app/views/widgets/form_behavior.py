"""Application-wide guard against accidental form-field edits.

PriceSpinBox and QuantitySpinBox already ignore the mouse wheel "to prevent
accidental changes". This module extends the same protection to every
QComboBox and spin box in the application, so behaviour is identical in every
form for both the Administrateur and Utilisateur spaces.

Rules
-----
* Mouse wheel never changes a dropdown or a spin box value. The scroll goes
  to the enclosing scroll area instead, so long forms still scroll normally
  when the pointer happens to sit over a field.
* Up/Down/PageUp/PageDown never change a *closed* dropdown's value: a combo
  box may only be changed by opening it and picking an option.

Deliberately left alone
-----------------------
* Arrow keys on spin boxes (quantities, prices, dates) — there they are the
  normal way to type a value, not an accidental-change hazard.
* Everything once a dropdown is open: the popup list keeps full keyboard and
  wheel navigation, and Alt+Down / Enter / Space still open it.

Two mechanisms, on purpose
--------------------------
1. Patched virtuals on the widget classes. Costs nothing outside real wheel
   and key events, and covers every field built from Python — which includes
   the two heaviest screens (Caisse and Produits, which rebuild their card
   grids on every visit).
2. A per-widget event filter installed by the .ui loader. Widgets that
   QUiLoader builds are created on the C++ side, so Qt never routes their
   virtual calls back into Python and mechanism 1 is silently skipped for
   them (verified). Those forms are small dialogs, so a filter attached to
   their handful of fields costs nothing measurable.

An application-wide event filter would have covered both in one go, but it is
invoked for *every* event in the process; measured here it added ~14 ms to a
typical page change and ~165 ms to the heaviest one, on every visit.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QWidget,
)

_VALUE_STEP_KEYS = frozenset((Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown))


def _popup_is_open(widget) -> bool:
    view = getattr(widget, "view", None)
    if not callable(view):
        return False  # spin boxes have no popup
    popup = view()
    return popup is not None and popup.isVisible()


def _blocks_value_step(event) -> bool:
    # Alt+Down is the standard "open the list" shortcut — keep it working.
    return event.key() in _VALUE_STEP_KEYS and not (event.modifiers() & Qt.AltModifier)


def _scroll_enclosing_area(widget, event) -> None:
    """Hand a blocked wheel event to the nearest scrollable ancestor.

    Used by the event-filter path only: a filter that returns True drops the
    event outright, so without this the form would refuse to scroll whenever
    the cursor sits over a field. (The patched-virtual path just calls
    event.ignore() and lets Qt propagate normally.)
    """
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            QApplication.sendEvent(parent.viewport(), event)
            return
        parent = parent.parentWidget()


class _FieldEventGuard(QObject):
    """Per-widget filter for fields QUiLoader created on the C++ side."""

    def eventFilter(self, obj, event):
        event_type = event.type()

        if event_type == QEvent.Wheel:
            if _popup_is_open(obj):
                return False
            _scroll_enclosing_area(obj, event)
            return True

        if event_type == QEvent.KeyPress and isinstance(obj, QComboBox):
            if _popup_is_open(obj):
                return False  # the open list owns arrow navigation
            if _blocks_value_step(event):
                return True

        return False


_shared_guard: _FieldEventGuard | None = None
_classes_patched = False


def install_form_field_guard(app: QApplication | None = None) -> None:
    """Apply the class-level half of the guard. Safe to call more than once."""
    global _shared_guard, _classes_patched
    if _shared_guard is None:
        _shared_guard = _FieldEventGuard(app)

    if _classes_patched:
        return
    _classes_patched = True

    combo_key_press = QComboBox.keyPressEvent

    def combo_wheel_event(self, event):
        # ignore() (rather than swallowing) lets Qt hand the scroll to the
        # enclosing scroll area, so the form still scrolls under the cursor.
        event.ignore()

    def combo_key_press_event(self, event):
        if not _popup_is_open(self) and _blocks_value_step(event):
            event.ignore()
            return
        combo_key_press(self, event)

    def spinbox_wheel_event(self, event):
        event.ignore()

    QComboBox.wheelEvent = combo_wheel_event
    QComboBox.keyPressEvent = combo_key_press_event
    # QSpinBox/QDoubleSpinBox/QDateEdit inherit these; QDateTimeEdit defines
    # its own wheelEvent, so patching only the base class would miss dates.
    QAbstractSpinBox.wheelEvent = spinbox_wheel_event
    QDateTimeEdit.wheelEvent = spinbox_wheel_event


def guard_fields_in(root: QWidget) -> None:
    """Protect the fields of a widget tree Qt built on the C++ side.

    Called by the .ui loader; harmless (just redundant) for Python-built
    widgets, which the patched virtuals already cover.
    """
    if _shared_guard is None:
        install_form_field_guard()
    for field in root.findChildren(QComboBox):
        field.installEventFilter(_shared_guard)
    for field in root.findChildren(QAbstractSpinBox):
        field.installEventFilter(_shared_guard)
    if isinstance(root, (QComboBox, QAbstractSpinBox)):
        root.installEventFilter(_shared_guard)
