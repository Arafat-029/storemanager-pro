# MySQL

## 1) Installer la dépendance
```bash
pip install PyMySQL
```

## 2) Configurer MySQL
Définir ces variables d'environnement avant lancer l'application :

```bash
set DB_BACKEND=mysql
set MYSQL_HOST=127.0.0.1
set MYSQL_PORT=3306
set MYSQL_USER=root
set MYSQL_PASSWORD=
set MYSQL_DATABASE=storemanager
```

## 3) Lancer l'application
```bash
python main.py
```

## 4) Importer les anciennes données SQLite
```bash
python scripts/migrate_sqlite_to_mysql.py
```


## Fix FK supplier_invoice_payments

If the database was partially created before this fix, drop and recreate the database, or run:

```sql
DROP TABLE IF EXISTS supplier_invoice_payments;
DROP TABLE IF EXISTS supplier_invoice_items;
```
