"""Étape 1 — Génération des fichiers CSV de transactions.

Les données ne sont PAS totalement aléatoires :
- la graine (seed) est fixe : même graine => mêmes fichiers, octet pour octet ;
- les comptes proviennent d'un référentiel fixe (IBAN valides, banques, pays) ;
- chaque fichier contient volontairement des cas limites pour tester le flag :
  un montant de 5000.00 exactement (NON flaggé) et un montant > 5000 (flaggé).
"""
import csv
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pipeline.iban import calculer_iban
from pipeline.models import COLONNES, FORMAT_DATETIME


@dataclass(frozen=True)
class Compte:
    iban: str
    pays: str
    banque: str


def _compte(pays: str, banque: str, bban: str) -> Compte:
    return Compte(calculer_iban(pays, bban), pays, banque)


# Référentiel fixe : deux comptes partagent la même banque pour tester l'agrégation par banque.
COMPTES = (
    _compte("FR", "BNP Paribas", "30004000031234567890"),
    _compte("FR", "BNP Paribas", "30004000039876543210"),
    _compte("FR", "Société Générale", "30003000701111222233"),
    _compte("DE", "Deutsche Bank", "37040044053201300000"),
    _compte("DE", "Commerzbank", "50040000123456789012"),
    _compte("ES", "Santander", "00491500051234567892"),
    _compte("IT", "UniCredit", "X0200811770000123456"),
    _compte("BE", "ING Belgique", "31012345678901234567"),
)

MONTANT_LIMITE = Decimal("5000.00")
MONTANTS_ELEVES = tuple(Decimal(m) for m in ("5000.01", "7500.00", "12500.00", "25000.00"))
DATE_DEPART = datetime(2026, 1, 5, 8, 0, 0)


def _montant_courant(rng: random.Random) -> Decimal:
    """Montant 'normal' entre 10.00 et 4999.99 (jamais flaggé)."""
    return Decimal(rng.randint(1_000, 499_999)).scaleb(-2)


def _generer_lignes(rng: random.Random, nb: int, depart: datetime) -> tuple[list[dict], datetime]:
    montants = [rng.choice(MONTANTS_ELEVES), MONTANT_LIMITE]
    montants += [_montant_courant(rng) for _ in range(nb - 2)]
    rng.shuffle(montants)

    lignes = []
    horodatage = depart
    for montant in montants:
        horodatage += timedelta(minutes=rng.randint(1, 240), seconds=rng.randint(0, 59))
        origine, destinataire = rng.sample(COMPTES, 2)
        lignes.append(
            {
                "datetime_transaction": horodatage.strftime(FORMAT_DATETIME),
                "iban_origine": origine.iban,
                "pays_source": origine.pays,
                "banque_source": origine.banque,
                "iban_destinataire": destinataire.iban,
                "pays_destinataire": destinataire.pays,
                "montant": f"{montant:.2f}".replace(".", ","),
            }
        )
    return lignes, horodatage


def generer_fichiers(
    dossier: str | Path,
    nb_fichiers: int = 5,
    graine: int = 42,
    injecter_erreur: bool = False,
) -> list[Path]:
    """Génère `nb_fichiers` CSV de 5 à 10 transactions chacun et renvoie leurs chemins.

    `injecter_erreur=True` écrit volontairement un montant au mauvais format ("12,50")
    dans le premier fichier : utile pour simuler un échec de pipeline.
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    rng = random.Random(graine)
    horodatage = DATE_DEPART
    chemins = []

    for numero in range(1, nb_fichiers + 1):
        lignes, horodatage = _generer_lignes(rng, rng.randint(5, 10), horodatage)
        if injecter_erreur and numero == 1:
            lignes[-1]["montant"] = "12,50"

        chemin = dossier / f"transactions_s{graine}_{numero:03d}.csv"
        with chemin.open("w", newline="", encoding="utf-8") as fichier:
            writer = csv.DictWriter(fichier, fieldnames=COLONNES)
            writer.writeheader()
            writer.writerows(lignes)
        chemins.append(chemin)

    return chemins
