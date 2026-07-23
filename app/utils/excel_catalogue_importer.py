from __future__ import annotations

from pathlib import Path
import re
import unicodedata


_CATEGORY_MAP: dict[str, str] = {
    "Laiterie & Fromage": "Produits laitiers",
    "Yaourts": "Yaourts",
    "Boissons": "Boissons",
    "Épicerie Sèche": "Épicerie",
    "Épicerie sèche": "Épicerie",
    "Épicerie": "Épicerie",
    "Huiles & Condiments": "Épicerie",
    "Boulangerie": "Boulangerie",
    "Pâtisseries": "Pâtisseries",
    "Fruits et légumes": "Fruits et légumes",
    "Produits ménagers": "Produits ménagers",
}


def _normalize(value: object) -> str:
    text = "" if value is None else str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).lower()


def _parse_price(value: object) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("TND", "").replace("€", "").replace("$", "")
    text = text.replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_catalogue_xlsx(path: str) -> list[dict]:
    """Parse an .xlsx catalogue file and return product rows."""
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl n'est pas installé.\n"
            "Installez-le avec : pip install openpyxl"
        ) from exc

    file_path = Path(path)
    if file_path.suffix.lower() != ".xlsx":
        raise RuntimeError(
            "Le format .xls n'est pas pris en charge dans cette version.\n"
            "Enregistrez le fichier au format .xlsx puis réessayez."
        )

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    header_aliases = {
        "barcode": ("code", "barre", "barcode", "ean"),
        "name": ("nom", "produit", "designation", "article", "libelle"),
        "supplier": ("fournisseur", "marque"),
        "category": ("categorie", "famille", "rayon"),
        "description": ("description", "details", "detail"),
        "price": ("prix", "vente", "pu", "unitaire", "price"),
        "purchase_price": ("achat", "cout", "cost"),
    }

    def detect_header(cells: list[str]) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for index, cell in enumerate(cells):
            for key, aliases in header_aliases.items():
                if key in mapping:
                    continue
                if any(alias in cell for alias in aliases):
                    mapping[key] = index
        return mapping

    header_row_found = False
    col_map: dict[str, int] = {}
    products: list[dict] = []

    for row in ws.iter_rows(values_only=True):
        if not any(cell is not None and str(cell).strip() for cell in row):
            continue

        normalized = [_normalize(cell) for cell in row]

        if not header_row_found:
            detected = detect_header(normalized)
            if "name" in detected:
                col_map = detected
                header_row_found = True
            continue

        name_index = col_map.get("name")
        if name_index is None or name_index >= len(row):
            continue

        name_raw = row[name_index]
        if not name_raw or not str(name_raw).strip():
            continue

        def get_value(key: str) -> str:
            idx = col_map.get(key)
            if idx is None or idx >= len(row):
                return ""
            value = row[idx]
            return str(value).strip() if value is not None else ""

        raw_category = get_value("category")
        category = _CATEGORY_MAP.get(raw_category, raw_category)

        products.append(
            {
                "name": str(name_raw).strip(),
                "barcode": get_value("barcode"),
                "supplier": get_value("supplier"),
                "category": category,
                "description": get_value("description"),
                "sale_price": _parse_price(
                    row[col_map["price"]] if "price" in col_map and col_map["price"] < len(row) else 0
                ),
                "purchase_price": _parse_price(
                    row[col_map["purchase_price"]]
                    if "purchase_price" in col_map and col_map["purchase_price"] < len(row)
                    else 0
                ),
            }
        )

    wb.close()
    return products
