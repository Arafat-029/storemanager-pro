from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except ImportError:
    _HAS_FITZ = False

# ── Regex patterns ────────────────────────────────────────────────
_NUM_PAT      = re.compile(r'^[\d,\.\s\(\)/]+$')
_SHELF_PAT    = re.compile(r'\d+\s*(?:an|mois|jour|year|month|day)', re.IGNORECASE)

# Words that indicate header rows (first word is enough)
_NOISE_WORDS = {
    'poids', 'weight', 'box', 'boite', 'colisage', 'packing', 'pack',
    'palettisation', 'palletization', 'dlc', 'shelf', 'life', 'barcode',
    'portion', 'nombre', 'carton', 'palettes', 'caractéristiques',
    'techniques', 'technical', 'specifications', 'code', 'barre',
    'gamme', 'range', 'famille', 'family', 'notre', 'our', 'the',
}

# Exact strings that should be skipped
_NOISE_EXACT = {
    '( l )', '(l)', 'l', 'lr', 'kg', 'gr', 'ml',
    'days', 'months', 'years', 'day', 'month', 'year',
    'jours', 'ans', 'mois', 'an',
    'milk', 'dairy', 'juice', 'water', 'butter and cream',
    'fresh cheese', 'processed cheese', 'soft drinks',
    'flavoured milk', 'fermented milk', 'long shelf life milk',
    'spreadable fresh cheese', 'vegetable fat product',
}

# Page index (1-based) → (db_category_name, product_series)
_PAGE_INFO: dict[int, tuple[str, str]] = {
    3:  ('Boissons',          'Délice Jus'),
    4:  ('Boissons',          'Fruzzy'),
    5:  ('Boissons',          "Déli'o"),
    6:  ('Boissons',          'Punch'),
    7:  ('Boissons',          'Bitter Soda'),
    8:  ('Produits laitiers', 'Triangle Milkana'),
    9:  ('Produits laitiers', 'Mon Carré Milkana'),
    11: ('Produits laitiers', 'Cheesland'),
    12: ('Produits laitiers', "Tarti'frais"),
    13: ('Produits laitiers', 'Goutta'),
    14: ('Produits laitiers', 'Tartare'),
    15: ('Produits laitiers', 'Lait Délice'),
    16: ('Produits laitiers', 'Déli Shake'),
    17: ('Produits laitiers', 'WakeUp Délice'),
    18: ('Produits laitiers', 'Délisso'),
    19: ('Produits laitiers', 'Lben/Raïeb Délice'),
    20: ('Produits laitiers', 'Crème Délice'),
    21: ('Produits laitiers', 'Beurre Délice'),
    22: ('Boissons',          'Eau Délice'),
}


def _clean_barcode(raw: str) -> Optional[str]:
    cleaned = re.sub(r'\s', '', raw).upper().replace('O', '0')
    if cleaned.isdigit() and 8 <= len(cleaned) <= 14:
        return cleaned
    return None


def _is_barcode_like(text: str) -> bool:
    t = re.sub(r'\s', '', text).upper().replace('O', '0')
    return t.isdigit() and 8 <= len(t) <= 15


def _is_noise(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return True

    lower = stripped.lower()

    # Encoding gibberish from corrupted PDF fonts (chars above Latin-1, U+00FF)
    non_latin = sum(1 for c in stripped if ord(c) > 0x00FF)
    if non_latin > len(stripped) * 0.25:
        return True

    # Lines with high density of special chars (corrupted ASCII like "<$$}$PW")
    special = sum(
        1 for c in stripped
        if not c.isalnum() and c not in " '-/&.,éèêëàâùûüôîïœæçÉÈÊËÀÂÙÛÜÔÎÏŒÆÇ"
    )
    if special > 2 and special / len(stripped) > 0.35:
        return True

    # Pure numbers / symbols
    if _NUM_PAT.match(stripped):
        return True

    # Shelf-life pattern with a number
    if _SHELF_PAT.search(stripped):
        return True

    # Exact noise strings
    if lower in _NOISE_EXACT:
        return True

    # Lines that look like partial context "(pack)", "(bottle)" etc.
    if stripped.startswith('(') and stripped.endswith(')'):
        return True

    # Long sentences or description sentences are not product names
    if len(stripped) > 65:
        return True
    if stripped.endswith('.') and len(stripped) > 20:
        return True

    # Header row — split on spaces AND "/" to catch "weight/portion"
    first_word = re.split(r'[\s/]', lower)[0] if lower else ''
    return first_word in _NOISE_WORDS


def _normalize(s: str) -> str:
    """Normalize apostrophes and case for comparison."""
    return s.lower().replace('’', "'").replace('‘', "'")


def _build_name(series: str, flavor: str) -> str:
    if not flavor:
        return series
    # Avoid "Punch — Punch Cidre" → just "Punch Cidre"
    # Also handles curly vs. straight apostrophe differences
    series_first = _normalize(series).split()[0]
    if series_first in _normalize(flavor):
        return flavor
    return f"{series} — {flavor}"


def _extract_from_lines(
    lines: list[str], series: str, category: str
) -> list[dict]:
    products: list[dict] = []
    last_name = ""
    pending = ""   # for hyphenated line breaks (e.g. "Choc-" + "olate")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if _is_barcode_like(line):
            # Flush any pending concatenation
            if pending:
                last_name = pending.rstrip('-')
                pending = ""
            barcode = _clean_barcode(line)
            if barcode:
                name = _build_name(series, last_name) if last_name else series
                products.append({'name': name, 'barcode': barcode, 'category': category})

        elif pending:
            # Previous line ended with '-': join with this line
            joined = pending.rstrip('-') + line
            pending = ""
            if not _is_noise(joined):
                last_name = joined

        elif not _is_noise(line):
            if line.endswith('-'):
                pending = line
            else:
                last_name = line

    return products


def parse_catalogue_pdf(pdf_path: str | Path) -> list[dict]:
    """
    Parse a Délice product catalogue PDF.

    Returns list of dicts:
        {'name': str, 'barcode': str, 'category': str}

    Raises ImportError if PyMuPDF is not installed.
    Raises FileNotFoundError if the PDF does not exist.
    """
    if not _HAS_FITZ:
        raise ImportError(
            "PyMuPDF n'est pas installé. Lancez : pip install pymupdf"
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {pdf_path}")

    doc = fitz.open(str(pdf_path))
    products: list[dict] = []
    seen: set[str] = set()

    for page_idx in range(doc.page_count):
        page_num = page_idx + 1
        if page_num not in _PAGE_INFO:
            continue

        category, series = _PAGE_INFO[page_num]
        page = doc[page_idx]
        lines = [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]

        for p in _extract_from_lines(lines, series, category):
            bc = p['barcode']
            if bc not in seen:
                seen.add(bc)
                products.append(p)

    return products
