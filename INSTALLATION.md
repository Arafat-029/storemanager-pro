# Installation de StoreManager Pro

Guide pour installer l'application sur un nouveau poste (Windows).
Comptez environ 30 minutes, dont l'installation de MySQL.

---

## 1. Prérequis à installer

### Python 3.11 ou plus récent

Télécharger : https://www.python.org/downloads/

> ⚠️ À l'écran d'installation, **cocher « Add Python to PATH »** avant de cliquer sur Install.

Vérifier dans PowerShell :
```powershell
python --version
```

### MySQL Server 8.0 ou plus récent

Télécharger **MySQL Installer for Windows** :
https://dev.mysql.com/downloads/installer/

Pendant l'installation :

| Écran | Choix |
|---|---|
| Setup Type | **Custom** → ajouter *MySQL Server* et *MySQL Workbench* |
| Type and Networking | `Development Computer`, port **3306** |
| Authentication Method | Use Strong Password Encryption (par défaut) |
| Accounts and Roles | Définir un mot de passe **root** et le noter |
| Windows Service | ⚠️ **Cocher « Start the MySQL Server at System Startup »** |

> Le démarrage automatique est indispensable : si MySQL ne démarre pas tout
> seul, l'application ne s'ouvrira pas le matin.

Vérifier :
```powershell
Get-Service MySQL*
```
Le service doit être `Running` avec `StartType: Automatic`.

### Visual C++ Redistributable (pour le lecteur de codes-barres)

La lecture de codes-barres (`pyzbar`) a besoin du redistribuable
**Visual C++ 2013** sur Windows :
https://www.microsoft.com/en-us/download/details.aspx?id=40784

> Sans lui, l'application démarre quand même, mais le scan de codes-barres
> sera indisponible.

---

## 2. Récupérer l'application

Copier le dossier du projet sur le poste, par exemple dans
`C:\StoreManager\storemanager-pro`.

> ⚠️ **Le fichier `.env` n'est pas transmis** (il contient un mot de passe et
> est volontairement exclu). Vous le créerez à l'étape 5.
>
> La base de données et les photos de produits ne sont pas transmises non
> plus : le nouveau poste démarre avec une base vierge.

---

## 3. Créer l'environnement Python

Dans PowerShell, depuis le dossier du projet :

```powershell
cd C:\StoreManager\storemanager-pro
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> Si PowerShell refuse d'exécuter `Activate.ps1`, lancer une fois :
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

L'installation prend quelques minutes (PySide6 et OpenCV sont volumineux).

---

## 4. Créer la base de données et son utilisateur

```powershell
mysql -u root -p
```

Puis coller ces lignes en **remplaçant le mot de passe** :

```sql
CREATE DATABASE storemanager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'storemanager'@'localhost' IDENTIFIED BY 'ChoisirUnMotDePasseSolide';
GRANT ALL PRIVILEGES ON storemanager.* TO 'storemanager'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> Ne pas faire tourner l'application avec le compte `root`.

---

## 5. Configurer l'application

Copier le modèle fourni :

```powershell
copy .env.example .env
notepad .env
```

Remplacer la ligne du mot de passe par celui choisi à l'étape 4 :

```
DB_BACKEND=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=storemanager
MYSQL_PASSWORD=ChoisirUnMotDePasseSolide
MYSQL_DATABASE=storemanager
MYSQL_CHARSET=utf8mb4
```

Enregistrer et fermer.

> Ce fichier contient un mot de passe : ne jamais l'envoyer par e-mail ni le
> mettre sur un dépôt Git.

---

## 6. Vérifier l'installation

```powershell
python scripts\check_setup.py
```

Résultat attendu :

```
[ OK ]  Fichier .env present
[ OK ]  Mot de passe MySQL renseigne
[ OK ]  Utilisateur non-root
[ OK ]  Connexion a la base
[ OK ]  Creation / mise a jour du schema
[ OK ]  Tables presentes (19/19)
[ OK ]  Horloge base alignee sur l'heure locale
RESULTAT : PRET
```

Ce script crée aussi les tables au premier lancement.

**Si une ligne est en `[FAIL]`**, corriger avant de continuer :

| Message | Cause probable |
|---|---|
| `Connexion a la base` échoue | MySQL n'est pas démarré, ou mot de passe erroné dans `.env` |
| `Mot de passe MySQL renseigne` échoue | Le `.env` contient encore le texte à remplacer |
| `Horloge base` décalée | Fuseau horaire du poste mal réglé |

---

## 7. Lancer l'application

```powershell
python main.py
```

Identifiants de première connexion :

| Rôle | Identifiant | Mot de passe |
|---|---|---|
| Administrateur | `admin` | `admin` |
| Caissier | `001` | `001` |

---

## 8. ⚠️ À faire immédiatement après la première connexion

1. **Changer les deux mots de passe par défaut**
   Paramètres → Utilisateurs → modifier chaque compte.
   Tant que ce n'est pas fait, n'importe qui connaissant l'application peut
   se connecter en administrateur.

2. **Renseigner les informations du magasin**
   Paramètres → Informations du magasin (nom, adresse, téléphone) — elles
   apparaissent sur les tickets de caisse.

3. **Créer une première sauvegarde**
   Paramètres → Sauvegardes → *Créer une sauvegarde maintenant*.

---

## Sauvegardes

- Une sauvegarde automatique est créée **une fois par jour** pendant que
  l'application tourne.
- Elles sont stockées dans `data\backups`, **sur ce même ordinateur**.

> ⚠️ Si le poste tombe en panne ou est volé, ces sauvegardes disparaissent
> avec lui. **Copier régulièrement le dossier `data\backups` sur une clé USB
> ou un cloud.**

Pour restaurer : Paramètres → Sauvegardes → sélectionner une sauvegarde →
*Restaurer la sauvegarde sélectionnée*. L'application se ferme ensuite ; il
faut la relancer.

---

## Créer un raccourci sur le Bureau

Le fichier **`lancer.bat`** est fourni à la racine du projet : il active
l'environnement Python et démarre l'application en un double-clic.

Clic droit sur `lancer.bat` → *Envoyer vers* → *Bureau (créer un raccourci)*.

Les jours suivants, un double-clic sur ce raccourci suffit — plus besoin de
PowerShell.

---

## En cas de problème

1. Lancer `python scripts\check_setup.py` — il diagnostique la plupart des
   problèmes de configuration.
2. Consulter `data\logs\erreurs.log` — toute erreur inattendue y est
   enregistrée avec sa date.
3. Vérifier que le service MySQL tourne : `Get-Service MySQL*`
