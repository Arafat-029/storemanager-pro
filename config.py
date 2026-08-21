from __future__ import annotations
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── Où lire les ressources, où écrire les données ────────────────────────
# Deux racines distinctes, et c'est indispensable une fois l'application
# empaquetée en .exe : installée sous C:\Program Files\, Windows interdit
# d'écrire à côté du programme. Tout ce qui est modifiable doit donc vivre
# ailleurs que le code.
IS_FROZEN = bool(getattr(sys, "frozen", False))

if IS_FROZEN:
    # PyInstaller dépose les ressources embarquées dans _MEIPASS (dossier
    # temporaire en mode onefile, sous-dossier _internal en mode onedir).
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # %LOCALAPPDATA% est inscriptible sans droits administrateur et propre à
    # la session Windows ouverte sur la caisse.
    DATA_DIR = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "StoreManagerPro"
else:
    RESOURCE_DIR = BASE_DIR
    DATA_DIR = BASE_DIR / "data"


def _env_file() -> Path:
    """Emplacement du .env, en respectant ce que l'installateur a posé.

    Priorité au dossier de données (ce que crée l'installateur chez le
    client), puis à côté de l'exécutable, enfin le dossier du code en
    développement. Sans cet ordre, une réinstallation du programme
    écraserait la configuration du magasin.
    """
    candidates = [DATA_DIR / ".env"]
    if IS_FROZEN:
        candidates.append(Path(sys.executable).parent / ".env")
    candidates.append(BASE_DIR / ".env")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


ENV_FILE = _env_file()

# Les réglages viennent d'un fichier plutôt que de variables d'environnement :
# l'application se comporte pareil quel que soit le mode de lancement —
# raccourci, tâche planifiée ou terminal — au lieu de retomber en silence sur
# des valeurs par défaut quand une variable posée à la main manque.
try:
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)
except ImportError:  # dépendance absente : on s'en tient aux vraies variables
    pass

# Database
DB_BACKEND = os.getenv("DB_BACKEND", "mysql").strip().lower()
DATABASE_PATH = DATA_DIR / "store.db"
BACKUP_DIR = DATA_DIR / "backups"

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "storemanager")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "storemanager")
MYSQL_CHARSET = os.getenv("MYSQL_CHARSET", "utf8mb4")

# Ressources livrées avec le programme, jamais modifiées à l'exécution.
ASSETS_DIR = RESOURCE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
THEMES_DIR = ASSETS_DIR / "themes"

# Données produites par le magasin : elles doivent survivre à une mise à jour
# du programme, donc elles ne vivent jamais dans le dossier d'installation.
PRODUCT_IMAGES_DIR  = DATA_DIR / "product_images"
CATEGORY_IMAGES_DIR = DATA_DIR / "category_images"
QR_CODES_DIR = DATA_DIR / "qrcodes"
RECEIPTS_DIR = DATA_DIR / "receipts"
LOGS_DIR = DATA_DIR / "logs"
# Vignettes dérivées uniquement — suppression sans risque, régénérées à la demande.
THUMBNAIL_CACHE_DIR = DATA_DIR / "cache" / "thumbnails"

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
    for d in [
        DATA_DIR,
        DATABASE_PATH.parent,
        BACKUP_DIR,
        PRODUCT_IMAGES_DIR,
        CATEGORY_IMAGES_DIR,
        QR_CODES_DIR,
        RECEIPTS_DIR,
        LOGS_DIR,
        THUMBNAIL_CACHE_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)
