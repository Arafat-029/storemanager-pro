from __future__ import annotations
from PySide6.QtWidgets import QApplication, QWidget


def clamp_min_size(widget: QWidget, ideal_width: int, ideal_height: int, ratio: float = 0.92) -> None:
    """Cap a widget's minimum size to what the current screen can actually show.

    Dialogs and the main window were sized against a normal desktop monitor;
    on a smaller or more heavily DPI-scaled screen (a laptop panel at 125%,
    say), a hardcoded minimumSize forces the window past the visible work
    area instead of shrinking to fit it. *ideal_width*/*ideal_height* stay
    the ceiling on spacious screens, but never exceed *ratio* of the
    available screen geometry.
    """
    screen = widget.screen() or QApplication.primaryScreen()
    if screen is None:
        widget.setMinimumSize(ideal_width, ideal_height)
        return
    avail = screen.availableGeometry()
    width = min(ideal_width, max(1, int(avail.width() * ratio)))
    height = min(ideal_height, max(1, int(avail.height() * ratio)))
    widget.setMinimumSize(width, height)
