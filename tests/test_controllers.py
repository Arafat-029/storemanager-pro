"""Basic smoke tests — run with: python -m pytest tests/"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from app.database.schema import init_schema
from app.controllers.auth_controller import AuthController
from app.controllers.category_controller import CategoryController
from app.controllers.product_controller import ProductController
from app.controllers.sale_controller import SaleController


@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(config, "QR_CODES_DIR", tmp_path / "qr")
    monkeypatch.setattr(config, "PRODUCT_IMAGES_DIR", tmp_path / "img")
    monkeypatch.setattr(config, "RECEIPTS_DIR", tmp_path / "receipts")
    from app.database import connection
    connection.db._initialized = False
    connection.db._local = __import__("threading").local()
    init_schema()
    AuthController.login("admin", "admin")
    yield
    connection.db.close()


def test_login_success():
    user = AuthController.login("admin", "admin")
    assert user is not None
    assert user["role"] == "admin"


def test_login_failure():
    user = AuthController.login("admin", "wrongpassword")
    assert user is None


def test_create_category():
    cat_id = CategoryController.create("Test Cat", "desc", "#FF0000")
    assert cat_id > 0
    cats = CategoryController.get_all()
    names = [c["name"] for c in cats]
    assert "Test Cat" in names


def test_create_product():
    cat_id = CategoryController.create("Boissons Test", "test")
    pid = ProductController.create({
        "name": "Eau Minérale",
        "sale_price": 0.500,
        "purchase_price": 0.300,
        "category_id": cat_id,
        "stock_quantity": 100,
        "unit_type": "piece",
    })
    assert pid > 0
    p = ProductController.get_by_id(pid)
    assert p["name"] == "Eau Minérale"
    assert p["stock_quantity"] == 100


def test_create_sale():
    cat_id = CategoryController.create("Test Sale Cat")
    pid = ProductController.create({
        "name": "Produit Test",
        "sale_price": 1.500,
        "stock_quantity": 50,
        "unit_type": "piece",
    })
    sale = SaleController.create_sale(
        [{"product_id": pid, "quantity": 3, "unit_price": 1.500, "discount": 0}],
        "cash", 0, 0, 5.0,
    )
    assert sale["total"] == pytest.approx(4.5, abs=0.001)
    assert sale["change_given"] == pytest.approx(0.5, abs=0.001)

    p_after = ProductController.get_by_id(pid)
    assert p_after["stock_quantity"] == 47


def test_low_stock_alert():
    cat_id = CategoryController.create("Alert Cat")
    ProductController.create({
        "name": "Produit Faible",
        "sale_price": 1.0,
        "stock_quantity": 2,
        "min_stock": 10,
        "unit_type": "piece",
    })
    low = ProductController.get_low_stock()
    names = [p["name"] for p in low]
    assert "Produit Faible" in names


def test_credit_payment_realizes_revenue():
    from app.controllers.customer_controller import CustomerController

    pid = ProductController.create({
        "name": "Produit Crédit",
        "sale_price": 2.000,
        "purchase_price": 1.000,
        "stock_quantity": 20,
        "unit_type": "piece",
    })
    customer_id = CustomerController.create({"name": "Client Crédit", "phone": "", "address": "", "notes": ""})

    sale = SaleController.create_sale(
        [{"product_id": pid, "quantity": 3, "stock_quantity": 3, "unit_price": 2.000, "discount": 0}],
        "credit", 0, 0, 0,
        customer_id=customer_id,
    )
    assert sale["payment_status"] == "credit"

    summary_before = SaleController.get_daily_summary()
    assert summary_before["revenue"] == pytest.approx(0.0, abs=0.001)

    new_balance = CustomerController.record_payment(customer_id, 6.0)
    assert new_balance == pytest.approx(0.0, abs=0.001)

    summary_after = SaleController.get_daily_summary()
    assert summary_after["revenue"] == pytest.approx(6.0, abs=0.001)


def test_multi_unit_sale_decrements_real_stock():
    pid = ProductController.create({
        "name": "Eau Pack",
        "sale_price": 0.900,
        "purchase_price": 0.500,
        "stock_quantity": 12,
        "unit_type": "piece",
        "sale_units": [
            {"name": "Bouteille", "quantity": 1, "sale_price": 0.900, "barcode": "111", "is_default": True},
            {"name": "Pack 6", "quantity": 6, "sale_price": 4.700, "barcode": "666", "is_default": False},
        ],
    })
    scanned = ProductController.get_by_barcode("666")
    assert scanned["selected_sale_unit_name"] == "Pack 6"

    SaleController.create_sale(
        [{
            "product_id": pid,
            "sale_unit_id": scanned["selected_sale_unit_id"],
            "sale_unit_name": scanned["selected_sale_unit_name"],
            "quantity": 1,
            "stock_quantity": scanned["selected_sale_unit_quantity"],
            "unit_price": scanned["selected_sale_unit_price"],
            "discount": 0,
        }],
        "cash", 0, 0, 4.700,
    )

    p_after = ProductController.get_by_id(pid)
    assert p_after["stock_quantity"] == pytest.approx(6.0, abs=0.001)

    top = SaleController.get_top_products(limit=1)
    assert top[0]["total_qty"] == pytest.approx(6.0, abs=0.001)
