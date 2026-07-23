from __future__ import annotations
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt


class DataTable(QTableWidget):
    def __init__(self, columns: list[str], parent=None):
        super().__init__(parent)
        self._columns = columns
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        self.setSortingEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(200)

    def set_data(self, rows: list[dict], keys: list[str]):
        self.setRowCount(0)
        for row_data in rows:
            r = self.rowCount()
            self.insertRow(r)
            for c, key in enumerate(keys):
                val = row_data.get(key, "")
                item = QTableWidgetItem(str(val) if val is not None else "")
                item.setData(Qt.UserRole, row_data)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.setItem(r, c, item)
            self.setRowHeight(r, 48)

    def selected_row_data(self) -> dict | None:
        selected = self.selectedItems()
        if not selected:
            return None
        return selected[0].data(Qt.UserRole)
