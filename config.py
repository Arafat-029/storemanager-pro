from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Database
DB_BACKEND = os.getenv("DB_BACKEND", "mysql").strip().lower()
DATABASE_PATH = BASE_DIR / "data" / "store.db"
BACKUP_DIR = BASE_DIR / "data" / "backups"

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "storemanager")
MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

# Assets
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
THEMES_DIR = ASSETS_DIR / "themes"
PRODUCT_IMAGES_DIR  = BASE_DIR / "data" / "product_images"
CATEGORY_IMAGES_DIR = BASE_DIR / "data" / "category_images"
QR_CODES_DIR = BASE_DIR / "data" / "qrcodes"
RECEIPTS_DIR = BASE_DIR / "data" / "receipts"
# Derived thumbnails only — safe to delete, rebuilt on demand.
THUMBNAIL_CACHE_DIR = BASE_DIR / "data" / "cache" / "thumbnails"

# App info
APP_NAME = "StoreManager Pro"
APP_VERSION = "1.0.0"
APP_AUTHOR = "StoreManager"

# Stock
LOW_STOCK_THRESHOLD = 10

# Backup
AUTO_BACKUP_DAYS = 1

# UI
DEFAULT_THEME = "light"
WINDOW_MIN_WIDTH = 1280
WINDOW_MIN_HEIGHT = 800

# Date formats
DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"

# Receipt
STORE_NAME = "Mon Magasin"
STORE_ADDRESS = "Adresse du magasin"
STORE_PHONE = "+216 XX XXX XXX"

def ensure_dirs() -> None:
    for d in [DATABASE_PATH.parent, BACKUP_DIR, PRODUCT_IMAGES_DIR, CATEGORY_IMAGES_DIR, QR_CODES_DIR, RECEIPTS_DIR, THUMBNAIL_CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
