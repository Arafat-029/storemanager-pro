"""Verifie que l'installation est prete a servir en caisse.

    python scripts/check_setup.py

Controle la configuration, la connexion a la base, la presence de toutes les
tables et l'alignement de l'horloge de la base sur l'heure locale (un decalage
ferait basculer les ventes de fin de soiree sur le mauvais jour).
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from app.database.connection import db

EXPECTED_TABLES = [
    "users", "categories", "suppliers", "customers", "customer_credit_payments",
    "products", "product_sale_units", "sales", "sale_items", "sale_payments",
    "stock_movements", "expenses", "product_returns", "user_logs", "settings",
    "supplier_transactions", "supplier_invoices", "supplier_invoice_payments",
    "supplier_invoice_items", "cash_sessions",
]

ok = True


def check(label: str, passed: bool, detail: str = "") -> None:
    global ok
    mark = "[ OK ]" if passed else "[FAIL]"
    print(f"{mark}  {label}" + (f"  -> {detail}" if detail else ""))
    if not passed:
        ok = False


print("=" * 60)
print("VERIFICATION DE L'INSTALLATION")
print("=" * 60)

# 1. Configuration
check("Fichier .env present", config.ENV_FILE.is_file(), str(config.ENV_FILE))
print(f"       ressources = {config.RESOURCE_DIR}")
print(f"       donnees    = {config.DATA_DIR}")
print(f"       backend    = {config.DB_BACKEND}")
if config.DB_BACKEND == "mysql":
    print(f"       serveur    = {config.MYSQL_HOST}:{config.MYSQL_PORT}")
    print(f"       base       = {config.MYSQL_DATABASE}")
    print(f"       utilisateur= {config.MYSQL_USER}")
    check(
        "Mot de passe MySQL renseigne",
        bool(config.MYSQL_PASSWORD) and "REMPLACER" not in config.MYSQL_PASSWORD,
        "editez .env" if not config.MYSQL_PASSWORD else "",
    )
    check("Utilisateur non-root", config.MYSQL_USER != "root",
          "root deconseille en production" if config.MYSQL_USER == "root" else "")

# 2. Connexion
try:
    db.get_connection()
    check("Connexion a la base", True)
except Exception as exc:
    check("Connexion a la base", False, f"{type(exc).__name__}: {exc}")
    print("\nArret : impossible de continuer sans connexion.")
    sys.exit(1)

# 3. Schema
try:
    from app.database.schema import init_schema
    init_schema()
    check("Creation / mise a jour du schema", True)
except Exception as exc:
    check("Creation / mise a jour du schema", False, f"{type(exc).__name__}: {exc}")

missing = [t for t in EXPECTED_TABLES if not db.table_exists(t)]
check(f"Tables presentes ({len(EXPECTED_TABLES) - len(missing)}/{len(EXPECTED_TABLES)})",
      not missing, f"manquantes: {missing}" if missing else "")

# 4. Horloge de la base alignee sur l'heure locale
row = db.fetchone(
    "SELECT NOW() AS db_time" if db.is_mysql()
    else "SELECT datetime('now','localtime') AS db_time"
)
db_time = str((row or {}).get("db_time"))
local_time = datetime.now()
try:
    parsed = datetime.strptime(db_time[:19], "%Y-%m-%d %H:%M:%S")
    drift = abs((parsed - local_time).total_seconds())
except ValueError:
    drift = 9999
check("Horloge base alignee sur l'heure locale", drift < 120,
      f"base={db_time}  local={local_time:%Y-%m-%d %H:%M:%S}  ecart={drift:.0f}s")

# 5. Comptes par defaut encore actifs (rappel de securite)
weak = db.fetchall("SELECT username FROM users WHERE username IN ('admin','001') AND is_active=1")
if weak:
    print(f"[WARN]  Comptes par defaut actifs : {[u['username'] for u in weak]}"
          " -> changez les mots de passe avant la mise en production")

print("=" * 60)
print("RESULTAT :", "PRET" if ok else "CORRECTIONS NECESSAIRES")
print("=" * 60)
sys.exit(0 if ok else 1)
