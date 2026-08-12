from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt, QTimer

from app.controllers.auth_controller import AuthController
from app.views.dashboard_view import DashboardView
from app.views.pos_view import POSView
from app.views.products_view import ProductsView
from app.views.categories_view import CategoriesView
from app.views.suppliers_view import SuppliersView
from app.views.stock_view import StockView
from app.views.sales_view import SalesView
from app.views.customers_view import CustomersView
from app.views.users_view import UsersView
from app.views.expenses_view import ExpensesView
from app.views.settings_view import SettingsView
from app.views.dialog_theme import apply_dialog_theme, apply_light_messagebox_theme, light_information, light_warning
from config import APP_NAME, APP_VERSION, ASSETS_DIR


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1280, 800)

        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._current_page = ""

        self._build_ui()
        self._apply_role()

        self._backup_timer = QTimer(self)
        self._backup_timer.timeout.connect(self._auto_backup)
        self._backup_timer.start(86_400_000)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("mainCentralWidget")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._topnav = QFrame()
        self._topnav.setObjectName("topNavBar")

        topnav_layout = QVBoxLayout(self._topnav)
        topnav_layout.setContentsMargins(16, 10, 16, 10)
        topnav_layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        logo = QLabel("🏪")
        logo.setObjectName("appLogo")
        header_row.addWidget(logo)

        app_title = QLabel(APP_NAME)
        app_title.setObjectName("appTitle")
        header_row.addWidget(app_title)

        header_row.addStretch()

        self._clock_lbl = QLabel()
        self._clock_lbl.setObjectName("clockLabel")
        header_row.addWidget(self._clock_lbl)

        self._user_info_lbl = QLabel()
        self._user_info_lbl.setObjectName("userInfoLabel")
        header_row.addWidget(self._user_info_lbl)

        self._btn_logout = QPushButton("⏻  Déconnexion")
        self._btn_logout.setObjectName("btnLogout")
        self._btn_logout.setFixedHeight(36)
        self._btn_logout.setStyleSheet(
            "font-size: 11px; font-weight: 700; padding: 0 14px;"
            "background: #DC2626; color: white; border: 1px solid #B91C1C; border-radius: 10px;"
            "selection-background-color: #FCA5A5;"
        )
        self._btn_logout.clicked.connect(self._handle_logout_action)
        header_row.addWidget(self._btn_logout)

        topnav_layout.addLayout(header_row)

        self._nav_items = [
            ("dashboard", "📊", "Dashboard"),
            ("pos", "🛒", "Caisse"),
            ("products", "📦", "Produits"),
            ("categories", "🏷️", "Catégories"),
            ("suppliers", "🚚", "Fournisseurs"),
            ("stock", "📋", "Stock"),
            ("sales", "💰", "Ventes"),
            ("customers", "👥", "Clients"),
            ("expenses", "💸", "Dépenses"),
            ("users", "👤", "Utilisateurs"),
            ("settings", "⚙️", "Paramètres"),
        ]

        self._nav_container = QWidget()
        self._nav_container.setObjectName("topNavLinksRow")
        self._nav_hlayout = QHBoxLayout(self._nav_container)
        self._nav_hlayout.setContentsMargins(0, 0, 0, 0)
        self._nav_hlayout.setSpacing(6)

        topnav_layout.addWidget(self._nav_container)
        root.addWidget(self._topnav)

        self._topbar = QFrame()
        self._topbar.setObjectName("topBar")
        self._topbar.setFixedHeight(50)

        topbar_layout = QHBoxLayout(self._topbar)
        self._topbar_layout = topbar_layout
        topbar_layout.setContentsMargins(24, 0, 24, 0)
        topbar_layout.setSpacing(10)

        self._page_title = QLabel("Tableau de bord")
        self._page_title.setObjectName("pageTitle")
        topbar_layout.addWidget(self._page_title)

        self._pos_cash_lbl = QLabel("")
        self._pos_cash_lbl.setVisible(False)
        self._pos_cash_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 800; color: #0F172A;"
            "background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 5px 10px;"
        )
        topbar_layout.addWidget(self._pos_cash_lbl)

        topbar_layout.addStretch()

        root.addWidget(self._topbar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("mainStack")
        root.addWidget(self._stack, 1)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()


    def _allowed_pages(self) -> set[str]:
        if AuthController.is_admin():
            return {
                "dashboard",
                "pos",
                "products",
                "categories",
                "suppliers",
                "stock",
                "sales",
                "customers",
                "expenses",
                "users",
                "settings",
            }
        return {"pos"}

    def _can_access_page(self, page_id: str) -> bool:
        return page_id in self._allowed_pages()

    def navigate(self, page_id: str):
        if not self._can_access_page(page_id):
            page_id = "pos"

        if page_id not in self._pages:
            self._pages[page_id] = self._create_page(page_id)
            self._stack.addWidget(self._pages[page_id])

        page_widget = self._pages[page_id]
        self._stack.setCurrentWidget(page_widget)
        self._current_page = page_id

        titles = {
            "dashboard": "📊  Tableau de bord",
            "pos": "🛒  Caisse — Point de Vente",
            "products": "📦  Gestion des produits",
            "categories": "🏷️  Catégories",
            "suppliers": "🚚  Fournisseurs",
            "stock": "📋  Gestion du stock",
            "sales": "💰  Historique des ventes",
            "customers": "👥  Clients & Crédits",
            "expenses": "💸  Dépenses",
            "users": "👤  Gestion des utilisateurs",
            "settings": "⚙️  Paramètres",
        }
        self._page_title.setText(titles.get(page_id, page_id))

        for pid, btn in self._nav_buttons.items():
            btn.setChecked(pid == page_id)

        self._pos_cash_lbl.setVisible(page_id == "pos" and not AuthController.is_admin())

        if page_id != "customers":
            self._refresh_page_widget(page_widget)

    def _update_pos_cash_label(self, text: str, tooltip: str = ""):
        self._pos_cash_lbl.setText(text)
        self._pos_cash_lbl.setToolTip(tooltip or "")

    def _apply_cashier_topbar_style(self, compact: bool):
        if compact:
            self._topbar.setFixedHeight(42)
            self._topbar.setStyleSheet("QFrame#topBar { background: transparent; border: none; }")
            self._topbar_layout.setContentsMargins(0, 4, 24, 2)
        else:
            self._topbar.setFixedHeight(50)
            self._topbar.setStyleSheet("")
            self._topbar_layout.setContentsMargins(24, 0, 24, 0)

    def _refresh_page_widget(self, page_widget: QWidget):
        target = self._extract_page_content(page_widget)
        refresh = getattr(target, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    def refresh_pages(self, page_ids: set[str] | None = None, include_current: bool = True):
        for pid, page_widget in self._pages.items():
            if page_ids is not None and pid not in page_ids:
                continue
            if not include_current and pid == self._current_page:
                continue
            self._refresh_page_widget(page_widget)

    def _extract_page_content(self, page_widget: QWidget) -> QWidget:
        if isinstance(page_widget, QScrollArea):
            container = page_widget.widget()
            if container is not None and container.layout() is not None and container.layout().count():
                item = container.layout().itemAt(0)
                if item is not None and item.widget() is not None:
                    return item.widget()
        return page_widget

    def _wrap_page_with_scroll(self, page: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("pageScrollArea")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        container = QWidget()
        container.setObjectName("pageScrollContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(page)
        scroll.setWidget(container)
        return scroll

    def _create_page(self, page_id: str) -> QWidget:
        if page_id == "dashboard":
            view = DashboardView()
            view.tile_clicked.connect(self.navigate)
            return self._wrap_page_with_scroll(view)
        if page_id == "pos":
            view = POSView()
            view.cash_expected_changed.connect(self._update_pos_cash_label)
            return view
        if page_id == "products":
            return self._wrap_page_with_scroll(ProductsView())
        if page_id == "categories":
            return self._wrap_page_with_scroll(CategoriesView())
        if page_id == "suppliers":
            return self._wrap_page_with_scroll(SuppliersView())
        if page_id == "stock":
            return self._wrap_page_with_scroll(StockView())
        if page_id == "sales":
            return self._wrap_page_with_scroll(SalesView())
        if page_id == "customers":
            return CustomersView()
        if page_id == "expenses":
            return self._wrap_page_with_scroll(ExpensesView())
        if page_id == "users":
            return self._wrap_page_with_scroll(UsersView())
        if page_id == "settings":
            return self._wrap_page_with_scroll(SettingsView())
        return self._wrap_page_with_scroll(QWidget())

    def _apply_theme(self, theme: str):
        qss_path = ASSETS_DIR / "themes" / f"{theme}.qss"
        if qss_path.exists():
            QApplication.instance().setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _update_clock(self):
        from datetime import datetime
        self._clock_lbl.setText(datetime.now().strftime("  %d/%m/%Y   %H:%M:%S"))

    def _apply_role(self):
        is_admin = AuthController.is_admin()
        user = AuthController.current_user()

        name = user.get("full_name", user.get("username", ""))
        role_text = "Administrateur" if user.get("role") == "admin" else "Caissier"
        self._user_info_lbl.setText(f"👤 {name} • {role_text}")

        self._rebuild_nav()

        self._topnav.setVisible(is_admin)
        self._topbar.setVisible(True)
        self._page_title.setVisible(is_admin)
        self._apply_cashier_topbar_style(not is_admin)

        if not is_admin:
            self.navigate("pos")
        else:
            self.navigate("dashboard")

    def _confirm_logout(self) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Déconnexion")
        box.setText("Voulez-vous vraiment vous déconnecter de votre session ?")
        box.setInformativeText("Cette action vous ramènera à l’écran de connexion.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        apply_light_messagebox_theme(box)
        return box.exec() == QMessageBox.Yes

    def _handle_logout_action(self):
        if not self._confirm_logout():
            return
        self._logout(confirm=False)

    def _logout(self, confirm: bool = True):
        if confirm and not self._confirm_logout():
            return

        AuthController.logout()
        self.hide()

        from app.views.login_dialog import LoginDialog

        login = LoginDialog()
        if login.exec():
            self._pages.clear()
            while self._stack.count():
                widget = self._stack.widget(0)
                self._stack.removeWidget(widget)
                widget.deleteLater()
            self._apply_role()
            self.showMaximized()
        else:
            QApplication.quit()

    def _rebuild_nav(self):
        while self._nav_hlayout.count():
            item = self._nav_hlayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._nav_buttons.clear()

        allowed_pages = self._allowed_pages()

        for page_id, icon, label in self._nav_items:
            if page_id not in allowed_pages:
                continue

            btn = QPushButton(f"{icon} {label}")
            btn.setObjectName("topNavBtn")
            btn.setCheckable(True)
            btn.setMinimumHeight(36)
            btn.clicked.connect(lambda _, pid=page_id: self.navigate(pid))

            self._nav_buttons[page_id] = btn
            self._nav_hlayout.addWidget(btn)

        self._nav_hlayout.addStretch()

    def _pos_view(self):
        page_widget = self._pages.get("pos")
        if page_widget is None:
            return None
        return self._extract_page_content(page_widget)

    def _prompt_cashier_exit_action(self) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle("Clôture de caisse")
        dialog.setModal(True)
        dialog.setMinimumWidth(430)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        app_stylesheet = (QApplication.instance().styleSheet() or "").lower()
        is_dark_theme = any(token in app_stylesheet for token in ("#0b1121", "#0d1525", "#111b2e", "dark"))
        apply_dialog_theme(dialog, dark=is_dark_theme)

        dialog.setStyleSheet(
            dialog.styleSheet()
            + """
            QDialog {
                border-radius: 16px;
                border: 1px solid #E0E6EF;
            }
            QLabel#cashierExitTitle {
                color: #1B2A4A;
                font-size: 17px;
                font-weight: 800;
                margin-bottom: 4px;
            }
            QLabel#cashierExitSubtitle {
                color: #475569;
                font-size: 12px;
                font-weight: 500;
                margin-bottom: 6px;
            }
            QPushButton {
                min-width: 132px;
                min-height: 44px;
                max-height: 44px;
                padding: 0 16px;
                border-radius: 10px;
                border: 1.5px solid transparent;
            }
            QPushButton#btnSecondary {
                background: #F8FAFC;
                border-color: #CBD5E1;
                color: #475569;
            }
            QPushButton#btnSecondary:hover {
                background: #F1F5F9;
                border-color: #94A3B8;
                color: #1E293B;
            }
            QPushButton#btnPrimary {
                background: #1E88E5;
                color: #FFFFFF;
            }
            QPushButton#btnPrimary:hover {
                background: #1565C0;
            }
            QPushButton#btnDanger {
                background: #EF4444;
                color: #FFFFFF;
            }
            QPushButton#btnDanger:hover {
                background: #DC2626;
            }
            """
        )

        title_lbl = QLabel("Que souhaitez-vous faire ?")
        title_lbl.setObjectName("cashierExitTitle")
        subtitle_lbl = QLabel("Vous pouvez continuer le travail, vous déconnecter ou terminer la journée.")
        subtitle_lbl.setObjectName("cashierExitSubtitle")
        subtitle_lbl.setWordWrap(True)

        logout_btn = QPushButton("Se déconnecter")
        logout_btn.setObjectName("btnSecondary")
        finish_btn = QPushButton("Terminer la journée")
        finish_btn.setObjectName("btnPrimary")
        finish_btn.setDefault(True)
        stay_btn = QPushButton("Annuler")
        stay_btn.setObjectName("btnDanger")

        action = "cancel"

        def choose_logout() -> None:
            nonlocal action
            action = "logout"
            dialog.accept()

        def choose_finish() -> None:
            nonlocal action
            action = "finish"
            dialog.accept()

        def choose_stay() -> None:
            nonlocal action
            action = "cancel"
            dialog.reject()

        logout_btn.clicked.connect(choose_logout)
        finish_btn.clicked.connect(choose_finish)
        stay_btn.clicked.connect(choose_stay)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.addWidget(stay_btn)
        buttons_layout.addWidget(logout_btn)
        buttons_layout.addWidget(finish_btn)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title_lbl)
        layout.addWidget(subtitle_lbl)
        layout.addLayout(buttons_layout)

        dialog.setMinimumHeight(205)
        dialog.exec()
        return action

    def closeEvent(self, event):
        user = AuthController.current_user() or {}
        if str(user.get("role") or "").strip().lower() != "cashier":
            return super().closeEvent(event)

        pos_view = self._pos_view()
        if pos_view is None:
            return super().closeEvent(event)

        action = self._prompt_cashier_exit_action()
        if action == "cancel":
            event.ignore()
            return

        if action == "logout":
            self._logout(confirm=False)
            event.ignore()
            return

        summary = pos_view.finish_current_shift()
        light_information(
            self,
            "Fin de travail",
            (
                f"Montant attendu en caisse : {summary.get('expected_cash_text', '0.000 TND')}\n"
                f"Ouverture : {summary.get('opening_cash_text', '0.000 TND')}\n"
                f"Encaissements : {summary.get('total_received_text', '0.000 TND')}"
            ),
        )
        return super().closeEvent(event)

    def _auto_backup(self):
        try:
            from app.database.backup import create_backup
            create_backup()
        except Exception:
            pass
