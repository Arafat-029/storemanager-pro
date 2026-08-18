"""Traduction du journal d'actions en francais lisible.

Le journal stocke des codes techniques (SALE_CANCEL, CASH_SESSION_CLOSE...)
parce qu'ils sont stables et faciles a filtrer. Mais le proprietaire du
magasin n'a pas a les dechiffrer : la traduction se fait a l'affichage, ce
qui vaut aussi pour les lignes deja enregistrees.
"""
from __future__ import annotations

# Regroupement par domaine : sert au filtre de l'ecran Journal.
VENTES = "Ventes"
CAISSE = "Caisse"
STOCK = "Stock & produits"
TIERS = "Clients & fournisseurs"
ARGENT = "Dépenses"
SECURITE = "Sécurité & accès"
SYSTEME = "Système"

# code -> (libelle affiche, domaine)
_LABELS: dict[str, tuple[str, str]] = {
    # Ventes
    "SALE_CREATE": ("Vente enregistrée", VENTES),
    "SALE_CANCEL": ("Vente annulée", VENTES),
    # Caisse
    "CASH_SESSION_OPEN": ("Ouverture de caisse", CAISSE),
    "CASH_SESSION_CLOSE": ("Clôture de caisse", CAISSE),
    # Stock et produits
    "PRODUCT_CREATE": ("Produit créé", STOCK),
    "PRODUCT_UPDATE": ("Produit modifié", STOCK),
    "PRODUCT_DELETE": ("Produit supprimé", STOCK),
    "CATEGORY_CREATE": ("Catégorie créée", STOCK),
    "CATEGORY_UPDATE": ("Catégorie modifiée", STOCK),
    "CATEGORY_DELETE": ("Catégorie supprimée", STOCK),
    "STOCK_IN": ("Entrée de stock", STOCK),
    "STOCK_ADJUST": ("Ajustement de stock", STOCK),
    "STOCK_LOSS": ("Perte déclarée", STOCK),
    "STOCK_EXPIRY_UPDATE": ("Dates de péremption mises à jour", STOCK),
    # Clients et fournisseurs
    "CUSTOMER_CREATE": ("Client créé", TIERS),
    "CUSTOMER_UPDATE": ("Client modifié", TIERS),
    "CUSTOMER_DELETE": ("Client supprimé", TIERS),
    "CUSTOMER_CREDIT": ("Crédit accordé à un client", TIERS),
    "CUSTOMER_PAYMENT": ("Règlement d'un client", TIERS),
    "SUPPLIER_CREATE": ("Fournisseur créé", TIERS),
    "SUPPLIER_UPDATE": ("Fournisseur modifié", TIERS),
    "SUPPLIER_DELETE": ("Fournisseur supprimé", TIERS),
    "SUPPLIER_INVOICE_CREATE": ("Facture fournisseur ajoutée", TIERS),
    "SUPPLIER_INVOICE_UPDATE": ("Facture fournisseur modifiée", TIERS),
    "SUPPLIER_INVOICE_DELETE": ("Facture fournisseur supprimée", TIERS),
    "SUPPLIER_INVOICE_PAYMENT": ("Paiement à un fournisseur", TIERS),
    "SUPPLIER_PAYMENT_LEGACY": ("Paiement à un fournisseur", TIERS),
    # Depenses
    "EXPENSE_CREATE": ("Dépense enregistrée", ARGENT),
    "EXPENSE_DELETE": ("Dépense supprimée", ARGENT),
    # Securite
    "LOGIN": ("Connexion", SECURITE),
    "LOGOUT": ("Déconnexion", SECURITE),
    "ACCESS_GRANTED": ("Accès autorisé", SECURITE),
    "ACCESS_DENIED": ("Mot de passe refusé", SECURITE),
    "ACCESS_REFUSED": ("Accès abandonné", SECURITE),
    "USER_CREATE": ("Utilisateur créé", SECURITE),
    "USER_UPDATE": ("Utilisateur modifié", SECURITE),
    "USER_DELETE": ("Utilisateur désactivé", SECURITE),
    # Systeme
    "SETTINGS_UPDATE": ("Paramètre modifié", SYSTEME),
    "BACKUP_AUTO": ("Sauvegarde automatique", SYSTEME),
    "BACKUP_FAILED": ("Échec de sauvegarde", SYSTEME),
    "APP_ERROR": ("Erreur de l'application", SYSTEME),
}

DOMAINES = [VENTES, CAISSE, STOCK, TIERS, ARGENT, SECURITE, SYSTEME]

# Actions qui meritent d'etre reperees d'un coup d'oeil par le proprietaire :
# elles touchent a l'argent ou a la securite.
SENSIBLES = {
    "SALE_CANCEL", "CASH_SESSION_CLOSE", "STOCK_LOSS", "PRODUCT_DELETE",
    "ACCESS_DENIED", "BACKUP_FAILED", "APP_ERROR", "USER_DELETE",
}

# Termes techniques laisses dans les details par le code qui les ecrit.
_REMPLACEMENTS = [
    ("Méthode: cash", "payé en espèces"),
    ("Méthode: credit", "à crédit"),
    ("Méthode: card", "payé par carte"),
    ("« settings »", "« Paramètres »"),
    ("« products »", "« Produits »"),
    ("« users »", "« Utilisateurs »"),
    ("Total:", "total"),
    (" | ", " — "),
]


def label_for(action: str) -> str:
    """Libellé lisible d'un code d'action ; le code brut en dernier recours."""
    return _LABELS.get(str(action or "").strip().upper(), (str(action or ""), SYSTEME))[0]


def domain_for(action: str) -> str:
    return _LABELS.get(str(action or "").strip().upper(), ("", SYSTEME))[1]


def is_sensitive(action: str) -> bool:
    return str(action or "").strip().upper() in SENSIBLES


def humanize_details(details: str | None) -> str:
    """Nettoie les restes techniques d'une ligne de détail."""
    text = str(details or "").strip()
    for avant, apres in _REMPLACEMENTS:
        text = text.replace(avant, apres)
    return text
