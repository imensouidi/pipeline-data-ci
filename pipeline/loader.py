"""Étape 2a — Chargement des fichiers CSV (entrées/sorties uniquement, aucun calcul métier).

Chaque ligne est validée : en cas de donnée invalide, une erreur explicite indique
le fichier, la ligne, la colonne et la valeur fautive, puis la pipeline s'arrête.
"""
import csv
import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline.iban import iban_valide
from pipeline.models import COLONNES, FORMAT_DATETIME, Transaction


class FichierCSVInvalide(ValueError):
    """Le fichier CSV ou l'une de ses lignes ne respecte pas le format attendu."""


def lister_fichiers_csv(dossier: str | Path) -> list[Path]:
    return sorted(Path(dossier).glob("*.csv"))


def calculer_hash(chemin: str | Path) -> str:
    """Empreinte SHA-256 du contenu : identifie un fichier indépendamment de son nom."""
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()


def _erreur(fichier: str, ligne: int, colonne: str, detail: str, valeur) -> FichierCSVInvalide:
    return FichierCSVInvalide(
        f"{fichier}, ligne {ligne}, colonne '{colonne}' : {detail} (valeur reçue : {valeur!r})"
    )


def _parser_ligne(brute: dict, fichier: str, num: int) -> Transaction:
    if None in brute:
        raise FichierCSVInvalide(f"{fichier}, ligne {num} : trop de colonnes")
    for colonne in COLONNES:
        if brute.get(colonne) is None or brute[colonne].strip() == "":
            raise _erreur(fichier, num, colonne, "valeur manquante", brute.get(colonne))

    try:
        horodatage = datetime.strptime(brute["datetime_transaction"], FORMAT_DATETIME)
    except ValueError:
        raise _erreur(
            fichier, num, "datetime_transaction",
            f"format attendu {FORMAT_DATETIME}", brute["datetime_transaction"],
        ) from None

    for colonne in ("iban_origine", "iban_destinataire"):
        if not iban_valide(brute[colonne]):
            raise _erreur(fichier, num, colonne, "IBAN invalide", brute[colonne])

    for colonne in ("pays_source", "pays_destinataire"):
        valeur = brute[colonne]
        if not (len(valeur) == 2 and valeur.isalpha() and valeur.isupper()):
            raise _erreur(fichier, num, colonne, "code pays ISO à 2 lettres attendu", valeur)

    try:
        montant = Decimal(brute["montant"])
    except InvalidOperation:
        raise _erreur(
            fichier, num, "montant", "nombre décimal attendu (ex : 1234.56)", brute["montant"]
        ) from None
    if not montant.is_finite() or montant <= 0:
        raise _erreur(fichier, num, "montant", "montant strictement positif attendu", brute["montant"])
    if montant.as_tuple().exponent < -2:
        raise _erreur(fichier, num, "montant", "2 décimales maximum", brute["montant"])

    return Transaction(
        datetime_transaction=horodatage,
        iban_origine=brute["iban_origine"],
        pays_source=brute["pays_source"],
        banque_source=brute["banque_source"].strip(),
        iban_destinataire=brute["iban_destinataire"],
        pays_destinataire=brute["pays_destinataire"],
        montant=montant,
    )


def charger_csv(chemin: str | Path) -> list[Transaction]:
    """Lit et valide un fichier CSV, renvoie la liste de ses transactions."""
    chemin = Path(chemin)
    with chemin.open(newline="", encoding="utf-8") as fichier:
        lecteur = csv.DictReader(fichier)
        if lecteur.fieldnames is None:
            raise FichierCSVInvalide(f"{chemin.name} : fichier vide")
        manquantes = [c for c in COLONNES if c not in lecteur.fieldnames]
        if manquantes:
            raise FichierCSVInvalide(f"{chemin.name} : colonnes manquantes {manquantes}")
        transactions = [
            _parser_ligne(ligne, chemin.name, num) for num, ligne in enumerate(lecteur, start=2)
        ]

    if not transactions:
        raise FichierCSVInvalide(f"{chemin.name} : aucune transaction")
    return transactions