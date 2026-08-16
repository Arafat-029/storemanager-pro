from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QFrame,
    QScrollArea,
    QPushButton,
    QSizePolicy,
    QToolTip,
)
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from app.views.widgets.stat_card import StatCard
from app.controllers.sale_controller import SaleController
from app.controllers.product_controller import ProductController
from app.controllers.stock_controller import StockController
from app.controllers.expense_controller import ExpenseController
from app.utils.helpers import format_price, today_str, first_day_of_month


class DailyProfitChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[dict] = []
        self._line_color = QColor("#1D4ED8")
        self._point_color = QColor("#1E3A8A")
        self._fill_color = QColor(30, 64, 175, 24)
        # Geometry captured during paintEvent so mouseMoveEvent can hit-test
        # against the exact same pixel positions the curve was drawn at,
        # instead of recomputing (and risking drift from) the layout twice.
        self._plot_points: list[QPointF] = []
        self._chart_rect = None
        self._hover_index: int | None = None
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)

    def set_data(self, points: list[dict], line_color: str = "#1D4ED8", point_color: str = "#1E3A8A") -> None:
        self._points = list(points or [])
        self._line_color = QColor(line_color)
        self._point_color = QColor(point_color)
        fill = QColor(line_color)
        fill.setAlpha(24)
        self._fill_color = fill
        self._hover_index = None
        self.update()

    def _tooltip_text(self, point: dict) -> str:
        label = str(point.get("label") or point.get("date") or "")
        profit = float(point.get("profit", 0) or 0)
        expenses = float(point.get("expenses", 0) or 0)
        losses = float(point.get("losses", 0) or 0)
        lines = [f"<b>{label}</b>", f"Gain net : {format_price(profit)}"]
        if expenses:
            lines.append(f"Dépenses : {format_price(expenses)}")
        if losses:
            lines.append(f"Pertes : {format_price(losses)}")
        return "<br>".join(lines)

    def mouseMoveEvent(self, event):
        if not self._plot_points:
            super().mouseMoveEvent(event)
            return
        x = event.position().x()
        nearest = min(range(len(self._plot_points)), key=lambda i: abs(self._plot_points[i].x() - x))
        if nearest != self._hover_index:
            self._hover_index = nearest
            self.update()
        QToolTip.showText(event.globalPosition().toPoint(), self._tooltip_text(self._points[nearest]), self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_index is not None:
            self._hover_index = None
            self.update()
        QToolTip.hideText()
        super().leaveEvent(event)

    @staticmethod
    def _format_axis_value(value: float) -> str:
        abs_value = abs(float(value))
        if abs_value >= 1000:
            return f"{value:,.0f}".replace(",", " ")
        if abs_value >= 100:
            return f"{value:.0f}"
        return f"{value:.1f}"

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self._plot_points = []
        self._chart_rect = None

        chart_rect = self.rect().adjusted(68, 16, -18, -34)
        if chart_rect.width() <= 0 or chart_rect.height() <= 0:
            return

        painter.fillRect(self.rect(), QColor("transparent"))

        if not self._points:
            painter.setPen(QColor("#94A3B8"))
            painter.drawText(chart_rect, Qt.AlignCenter, "Aucune donnée disponible")
            return

        values = [float(point.get("profit", 0) or 0) for point in self._points]
        min_value = min(values)
        max_value = max(values)

        if abs(max_value - min_value) < 0.001:
            max_value += 1.0
            min_value -= 1.0

        zero_ratio = (0.0 - min_value) / (max_value - min_value)
        zero_y = chart_rect.bottom() - (zero_ratio * chart_rect.height())
        zero_y = max(chart_rect.top(), min(chart_rect.bottom(), zero_y))

        grid_pen = QPen(QColor("#E5E7EB"))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)

        tick_count = 5
        for step in range(tick_count):
            y = chart_rect.top() + (chart_rect.height() * step / (tick_count - 1))
            painter.drawLine(chart_rect.left(), int(y), chart_rect.right(), int(y))

            value = max_value - ((max_value - min_value) * step / (tick_count - 1))
            label_rect = self.rect().adjusted(8, 0, 0, 0)
            painter.setPen(QColor("#64748B"))
            painter.drawText(8, int(y) - 10, 52, 20, Qt.AlignRight | Qt.AlignVCenter, self._format_axis_value(value))
            painter.setPen(grid_pen)

        painter.setPen(QPen(QColor("#CBD5E1"), 1))
        painter.drawLine(chart_rect.left(), int(zero_y), chart_rect.right(), int(zero_y))
        painter.drawLine(chart_rect.left(), chart_rect.top(), chart_rect.left(), chart_rect.bottom())

        if len(self._points) == 1:
            x_positions = [chart_rect.center().x()]
        else:
            x_positions = [
                chart_rect.left() + (chart_rect.width() * index / (len(self._points) - 1))
                for index in range(len(self._points))
            ]

        def y_for(value: float) -> float:
            return chart_rect.bottom() - ((value - min_value) / (max_value - min_value) * chart_rect.height())

        path = QPainterPath()
        area_path = QPainterPath()

        for index, point in enumerate(self._points):
            x = x_positions[index]
            y = y_for(float(point.get("profit", 0) or 0))
            current = QPointF(float(x), float(y))
            if index == 0:
                path.moveTo(current)
                area_path.moveTo(float(x), float(zero_y))
                area_path.lineTo(current)
            else:
                path.lineTo(current)
                area_path.lineTo(current)

        area_path.lineTo(float(x_positions[-1]), float(zero_y))
        area_path.closeSubpath()

        painter.fillPath(area_path, self._fill_color)
        painter.setPen(QPen(self._line_color, 3))
        painter.drawPath(path)

        point_pen = QPen(self._point_color)
        point_pen.setWidth(2)
        painter.setPen(point_pen)
        painter.setBrush(QColor("#FFFFFF"))
        for index, point in enumerate(self._points):
            x = x_positions[index]
            y = y_for(float(point.get("profit", 0) or 0))
            painter.drawEllipse(QPointF(float(x), float(y)), 3.5, 3.5)
            self._plot_points.append(QPointF(float(x), float(y)))

        painter.setPen(QColor("#64748B"))
        label_indexes = {0, len(self._points) - 1}
        if len(self._points) > 4:
            label_indexes.update({len(self._points) // 3, (2 * len(self._points)) // 3})
        for index in sorted(label_indexes):
            point = self._points[index]
            x = x_positions[index]
            label = str(point.get("label") or "")
            painter.drawText(int(x) - 28, chart_rect.bottom() + 8, 56, 18, Qt.AlignCenter, label)

        self._chart_rect = chart_rect

        # Hover feedback: a vertical guide line plus a bigger ring on the
        # nearest point, so the reader can see exactly which point the
        # tooltip currently describes.
        if self._hover_index is not None and 0 <= self._hover_index < len(self._plot_points):
            hovered = self._plot_points[self._hover_index]
            guide_pen = QPen(QColor("#94A3B8"))
            guide_pen.setStyle(Qt.DashLine)
            guide_pen.setWidth(1)
            painter.setPen(guide_pen)
            painter.drawLine(int(hovered.x()), chart_rect.top(), int(hovered.x()), chart_rect.bottom())

            painter.setPen(QPen(self._point_color, 2))
            painter.setBrush(self._line_color)
            painter.drawEllipse(hovered, 5.5, 5.5)


class DashboardView(QWidget):
    tile_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._primary_cards = []
        self._secondary_cards = []
        self._profit_period = "day"
        self._profit_buttons: dict[str, QPushButton] = {}
        self._profit_credit_scope = "non_credit"
        self._credit_scope_buttons: dict[str, QPushButton] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("dashboardScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._content.setObjectName("dashboardContent")
        main = QVBoxLayout(self._content)
        main.setContentsMargins(24, 20, 24, 24)
        main.setSpacing(20)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        greet_col = QVBoxLayout()
        greet_col.setSpacing(4)

        self._greeting = QLabel("Statistiques du magasin")
        self._greeting.setStyleSheet("font-size: 22px; font-weight: 700; color: #1B2A4A;")

        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet("color: #64748B; font-size: 13px;")

        greet_col.addWidget(self._greeting)
        greet_col.addWidget(self._date_lbl)
        greet_col.addStretch()
        top_row.addLayout(greet_col, 1)

        right_col = QHBoxLayout()
        right_col.setSpacing(12)

        banner = QFrame()
        banner.setObjectName("statCard")
        banner.setMinimumHeight(72)
        banner_layout = QVBoxLayout(banner)
        banner_layout.setContentsMargins(20, 10, 20, 10)
        banner_layout.setSpacing(2)

        company_name = QLabel("SOLUTIONS STOREMANAGER PRO")
        company_name.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")

        company_phone = QLabel("+216 XX XXX XXX")
        company_phone.setStyleSheet("font-size: 12px; color: #64748B;")

        banner_layout.addWidget(company_name)
        banner_layout.addWidget(company_phone)

        refresh_btn = QPushButton("Actualiser")
        refresh_btn.setObjectName("btnSecondary")
        refresh_btn.setFixedWidth(130)
        refresh_btn.setFixedHeight(38)
        refresh_btn.clicked.connect(self.refresh)

        right_col.addWidget(banner, 1)
        right_col.addWidget(refresh_btn, 0, Qt.AlignTop)
        top_row.addLayout(right_col, 1)

        main.addLayout(top_row)

        self._summary_title = QLabel("Vue rapide")
        self._summary_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #0F172A;")
        main.addWidget(self._summary_title)

        self._cards_grid = QGridLayout()
        self._cards_grid.setHorizontalSpacing(14)
        self._cards_grid.setVerticalSpacing(14)

        self._card_revenue = StatCard("Chiffre d'affaires (Aujourd'hui)", "0.000 TND", "#059669", colored=False)
        self._card_sales = StatCard("Ventes (Aujourd'hui)", "0", "#2563EB", colored=False)
        self._card_products = StatCard("Produits actifs", "0", "#D97706", colored=False)
        self._card_low = StatCard("Stock faible", "0", "#DC2626", colored=False)

        self._primary_cards = [
            self._card_revenue,
            self._card_sales,
            self._card_products,
            self._card_low,
        ]


        self._month_grid = QGridLayout()
        self._month_grid.setHorizontalSpacing(14)
        self._month_grid.setVerticalSpacing(14)

        self._card_profit_today = StatCard("Gain net du jour", "0.000 TND", "#0F766E", colored=False)
        self._card_month = StatCard("CA du mois", "0.000 TND", "#0891B2", colored=False)
        self._card_inv_val = StatCard("Valeur du stock", "0.000 TND", "#7C3AED", colored=False)
        self._card_expenses = StatCard("Dépenses du mois", "0.000 TND", "#EA580C", colored=False)

        self._secondary_cards = [
            self._card_profit_today,
            self._card_month,
            self._card_inv_val,
            self._card_expenses,
        ]


        self._bottom_grid = QGridLayout()
        self._bottom_grid.setHorizontalSpacing(16)
        self._bottom_grid.setVerticalSpacing(16)

        self._low_stock_frame = self._build_panel("Produits en stock faible")
        self._low_stock_scroll = QScrollArea()
        self._low_stock_scroll.setWidgetResizable(True)
        self._low_stock_scroll.setFrameShape(QFrame.NoFrame)
        self._low_stock_scroll.setMinimumHeight(440)
        self._low_stock_inner = QWidget()
        self._low_stock_layout = QVBoxLayout(self._low_stock_inner)
        self._low_stock_layout.setSpacing(6)
        self._low_stock_layout.setContentsMargins(0, 0, 0, 0)
        self._low_stock_scroll.setWidget(self._low_stock_inner)
        self._low_stock_frame.layout().addWidget(self._low_stock_scroll, 1)

        self._top_frame = self._build_panel("Top produits (quantité vendue)")
        self._top_scroll = QScrollArea()
        self._top_scroll.setWidgetResizable(True)
        self._top_scroll.setFrameShape(QFrame.NoFrame)
        self._top_scroll.setMinimumHeight(440)
        self._top_inner = QWidget()
        self._top_layout = QVBoxLayout(self._top_inner)
        self._top_layout.setSpacing(6)
        self._top_layout.setContentsMargins(0, 0, 0, 0)
        self._top_scroll.setWidget(self._top_inner)
        self._top_frame.layout().addWidget(self._top_scroll, 1)

        self._bottom_grid.addWidget(self._low_stock_frame, 0, 0)
        self._bottom_grid.addWidget(self._top_frame, 0, 1)

        self._profit_frame = self._build_panel("Courbe de gain")
        self._profit_title_lbl = self._profit_frame.layout().itemAt(0).widget()

        profit_period_row = QHBoxLayout()
        profit_period_row.setSpacing(8)
        profit_period_row.addStretch()

        # "Avec crédit" includes every payment received, including deposits
        # and later repayments on a customer's credit balance (today's full
        # formula, unchanged). "Sans crédit" only counts sales paid in full
        # on the spot, so the owner can see what profit looks like without
        # relying on the credit extended to customers.
        for scope_key, scope_label in (("all", "Avec crédit"), ("non_credit", "Sans crédit")):
            btn = QPushButton(scope_label)
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda checked=False, key=scope_key: self._set_profit_credit_scope(key))
            self._credit_scope_buttons[scope_key] = btn
            profit_period_row.addWidget(btn)

        profit_period_row.addSpacing(16)

        for period_key, period_label in (("day", "Jour"), ("month", "Mois"), ("year", "Année")):
            btn = QPushButton(period_label)
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda checked=False, key=period_key: self._set_profit_period(key))
            self._profit_buttons[period_key] = btn
            profit_period_row.addWidget(btn)

        self._profit_frame.layout().insertLayout(1, profit_period_row)

        self._profit_note_lbl = QLabel(
            "Marge encaissée moins toutes les dépenses (les dépenses récurrentes "
            "sont comptées à chaque échéance)"
        )
        self._profit_note_lbl.setStyleSheet("color: #64748B; font-size: 11px;")
        self._profit_frame.layout().insertWidget(2, self._profit_note_lbl)

        self._profit_chart = DailyProfitChart()
        self._profit_frame.layout().addWidget(self._profit_chart, 1)

        main.addLayout(self._bottom_grid)
        main.addWidget(self._profit_frame)
        main.addLayout(self._cards_grid)
        main.addLayout(self._month_grid)
        main.addStretch()

        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll)

        self._relayout_sections()

    def _build_panel(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-weight: 700; font-size: 15px;")
        layout.addWidget(title_lbl)

        return frame

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_sections()

    def _relayout_sections(self):
        width = max(760, self.width())

        primary_columns = 4 if width >= 1500 else 2 if width >= 980 else 1
        secondary_columns = 4 if width >= 1500 else 2 if width >= 920 else 1
        bottom_columns = 2 if width >= 1100 else 1

        self._rebuild_grid(self._cards_grid, self._primary_cards, primary_columns)
        self._rebuild_grid(self._month_grid, self._secondary_cards, secondary_columns)
        self._rebuild_grid(self._bottom_grid, [self._low_stock_frame, self._top_frame], bottom_columns)

    def _rebuild_grid(self, layout: QGridLayout, widgets: list[QWidget], columns: int) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                layout.removeWidget(widget)

        for index, widget in enumerate(widgets):
            row = index // columns
            column = index % columns
            layout.addWidget(widget, row, column)

        for column in range(columns):
            layout.setColumnStretch(column, 1)


    def _set_profit_period(self, period: str) -> None:
        period = (period or "day").strip().lower()
        if period not in {"day", "month", "year"}:
            period = "day"
        self._profit_period = period
        self._update_profit_period_buttons()
        self._refresh_profit_chart()

    def _set_profit_credit_scope(self, scope: str) -> None:
        scope = (scope or "all").strip().lower()
        if scope not in {"all", "non_credit"}:
            scope = "all"
        self._profit_credit_scope = scope
        self._update_profit_credit_buttons()
        self._refresh_profit_chart()

    def _update_profit_period_buttons(self) -> None:
        for period, btn in self._profit_buttons.items():
            active = period == self._profit_period
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    "font-size: 11px; font-weight: 800; padding: 0 12px;"
                    "background: #1D4ED8; color: white; border: none; border-radius: 8px;"
                )
            else:
                btn.setStyleSheet(
                    "font-size: 11px; font-weight: 700; padding: 0 12px;"
                    "background: #F8FAFC; color: #334155; border: 1px solid #CBD5E1; border-radius: 8px;"
                )

    def _update_profit_credit_buttons(self) -> None:
        # "Sans crédit" is the default view and mirrors the curve's default
        # blue; "Avec crédit" is flagged in red since it folds in money from
        # the credit ledger (deposits/repayments) on top of the baseline.
        active_colors = {
            "all": "background: #DC2626; color: white; border: none;",
            "non_credit": "background: #1D4ED8; color: white; border: none;",
        }
        for scope, btn in self._credit_scope_buttons.items():
            active = scope == self._profit_credit_scope
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    f"font-size: 11px; font-weight: 800; padding: 0 12px; border-radius: 8px; {active_colors[scope]}"
                )
            else:
                btn.setStyleSheet(
                    "font-size: 11px; font-weight: 700; padding: 0 12px;"
                    "background: #F8FAFC; color: #334155; border: 1px solid #CBD5E1; border-radius: 8px;"
                )

    def _refresh_profit_chart(self) -> None:
        labels = {
            "day": "Courbe de gain net par jour",
            "month": "Courbe de gain net par mois",
            "year": "Courbe de gain net par année",
        }
        title = labels.get(self._profit_period, labels["day"])
        note = (
            "Marge encaissée moins toutes les dépenses (les dépenses récurrentes "
            "sont comptées à chaque échéance)"
        )
        if self._profit_credit_scope == "all":
            title += " — avec crédit client"
            note += " — inclut les dépôts et règlements de crédit client en plus des ventes payées sur place."
        self._profit_title_lbl.setText(title)
        self._profit_note_lbl.setText(note)

        if self._profit_credit_scope == "all":
            line_color, point_color = "#DC2626", "#991B1B"
        else:
            line_color, point_color = "#1D4ED8", "#1E3A8A"

        series = SaleController.get_profit_series(self._profit_period, self._profit_credit_scope)
        self._profit_chart.set_data(series, line_color=line_color, point_color=point_color)

    def refresh(self):
        from datetime import datetime

        now = datetime.now()
        self._date_lbl.setText(now.strftime("%A %d %B %Y  %H:%M"))
        self._update_profit_period_buttons()
        self._update_profit_credit_buttons()

        _today = today_str()
        month_start = first_day_of_month()

        daily = SaleController.get_daily_summary()
        self._card_revenue.set_value(format_price(daily.get("revenue", 0)))
        self._card_sales.set_value(str(daily.get("total_sales", 0)))

        today_profit_points = SaleController.get_profit_series("day")
        today_profit = today_profit_points[-1].get("profit", 0) if today_profit_points else 0
        self._card_profit_today.set_value(format_price(today_profit))

        inv = StockController.get_inventory_value()
        self._card_products.set_value(str(inv.get("product_count") or 0))
        self._card_low.set_value(str(inv.get("low_stock_count") or 0))
        self._card_inv_val.set_value(format_price(inv.get("sale_value", 0)))

        from app.database.connection import db
        month_rev = db.fetchone(
            "SELECT COALESCE(SUM(total),0) AS r FROM sales WHERE date(created_at)>=? AND status='completed'",
            (month_start,),
        )
        self._card_month.set_value(format_price(month_rev.get("r", 0) if month_rev else 0))

        month_exp = ExpenseController.get_summary(date_from=month_start)
        self._card_expenses.set_value(format_price(month_exp.get("total", 0)))

        self._clear_layout(self._low_stock_layout)
        low = ProductController.get_low_stock()
        if not low:
            lbl = QLabel("Aucun produit en stock faible")
            lbl.setStyleSheet("color: #059669; padding: 8px;")
            self._low_stock_layout.addWidget(lbl)
        for product in low:
            self._low_stock_layout.addWidget(self._make_stock_row(product))
        self._low_stock_layout.addStretch()
        self._update_panel_height(self._low_stock_scroll, len(low))

        self._clear_layout(self._top_layout)
        top = SaleController.get_top_products(50, date_from=month_start)
        if not top:
            lbl = QLabel("Aucune vente ce mois.")
            lbl.setStyleSheet("color: #6B7280; padding: 8px;")
            self._top_layout.addWidget(lbl)
        for index, product in enumerate(top, start=1):
            self._top_layout.addWidget(self._make_top_row(index, product))
        self._top_layout.addStretch()
        self._update_panel_height(self._top_scroll, len(top))

        self._refresh_profit_chart()

    def _update_panel_height(self, scroll: QScrollArea, item_count: int) -> None:
        row_height = 42
        frame_padding = 8
        visible_rows = min(10, max(1, item_count))
        scroll.setMinimumHeight((visible_rows * row_height) + frame_padding)

    def _make_stock_row(self, product: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dashRow")

        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)

        name = QLabel(product["name"])
        name.setStyleSheet("font-weight: 600;")
        name.setWordWrap(True)

        qty_text = f"{product['stock_quantity']:.1f} / {product['min_stock']:.1f}"
        qty = QLabel(qty_text)
        qty.setObjectName("badge")
        qty.setAlignment(Qt.AlignCenter)

        row.addWidget(name, 1)
        row.addWidget(qty)
        return frame

    @staticmethod
    def _format_top_quantity(product: dict) -> str:
        quantity = float(product.get("total_qty") or 0.0)
        unit_type = product.get("unit_type") or "piece"
        if unit_type == "piece":
            return f"{int(round(quantity))} pcs"
        if unit_type == "litre":
            return f"{quantity:.3f} L"
        return f"{quantity:.3f} kg"

    def _make_top_row(self, rank: int, product: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dashRow")

        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 8, 12, 8)

        rank_lbl = QLabel(f"#{rank}")
        rank_lbl.setStyleSheet("font-weight: 700; min-width: 28px; color: #64748B;")

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name = QLabel(product["name"])
        name.setStyleSheet("font-weight: 600;")
        name.setWordWrap(True)

        revenue = QLabel(f"CA : {format_price(product.get('total_revenue', 0))}")
        revenue.setStyleSheet("color: #64748B; font-size: 11px;")

        info_col.addWidget(name)
        info_col.addWidget(revenue)

        qty = QLabel(self._format_top_quantity(product))
        qty.setObjectName("badgeSuccess")
        qty.setAlignment(Qt.AlignCenter)

        row.addWidget(rank_lbl)
        row.addLayout(info_col, 1)
        row.addWidget(qty)
        return frame

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                DashboardView._clear_layout(child_layout)
