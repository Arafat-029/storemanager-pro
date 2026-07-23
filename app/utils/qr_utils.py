from __future__ import annotations
import qrcode
from pathlib import Path
from config import QR_CODES_DIR


def generate_qr(data: str, product_id: int) -> str:
    QR_CODES_DIR.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(data)
    path = QR_CODES_DIR / f"product_{product_id}.png"
    img.save(str(path))
    return str(path)


def generate_barcode_value(product_id: int) -> str:
    return f"SM{product_id:010d}"
