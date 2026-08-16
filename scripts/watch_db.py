"""Observe la base en direct pendant qu'on utilise l'application.

    python scripts/watch_db.py

Affiche le backend actif puis, toutes les 2 secondes, signale tout nouveau
produit / vente / client. Sert a prouver que l'application ecrit bien dans la
base attendue : creez un produit dans l'appli, il doit apparaitre ici.
Ctrl+C pour arreter.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# La console Windows ne sait pas afficher l'arabe : on force l'UTF-8 sur la
# sortie, sinon l'affichage d'un nom de produit fait planter le script.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import config
from app.database.connection import db

WATCHED = ("products", "sales", "customers")

print("=" * 58)
print(f"BACKEND ACTIF : {db.backend.upper()}")
if db.is_mysql():
    print(f"Serveur       : {config.MYSQL_HOST}:{config.MYSQL_PORT}")
    print(f"Base          : {config.MYSQL_DATABASE}")
else:
    print(f"Fichier       : {config.DATABASE_PATH}")
print("=" * 58)
print("En attente... Creez un produit dans l'application.")
print("(Ctrl+C pour arreter)\n")


def snapshot() -> dict[str, int]:
    return {t: db.fetchone(f"SELECT COUNT(*) AS n FROM {t}")["n"] for t in WATCHED}


previous = snapshot()
for table, count in previous.items():
    print(f"  {table:12} {count}")
print()

try:
    while True:
        time.sleep(2)
        current = snapshot()
        for table in WATCHED:
            delta = current[table] - previous[table]
            if delta > 0:
                print(f">>> +{delta} dans {table}  (total {current[table]})", flush=True)
                if table == "products":
                    row = db.fetchone("SELECT name, sale_price FROM products ORDER BY id DESC LIMIT 1")
                    print(f"    dernier : {row['name']}  -  {row['sale_price']}", flush=True)
            elif delta < 0:
                print(f">>> {delta} dans {table}  (total {current[table]})", flush=True)
        previous = current
except KeyboardInterrupt:
    print("\nArret.")
