"""Jeu de données de test ENTIÈREMENT CONNU : chaque résultat attendu est calculé à la main.

Comptes : A (BNP Paribas), B (Deutsche Bank), C (BNP Paribas, même banque que A).
"""
import csv
from pathlib import Path

from pipeline.iban import calculer_iban
from pipeline.models import COLONNES

A = calculer_iban("FR", "30004000031234567890")
B = calculer_iban("DE", "37040044053201300000")
C = calculer_iban("FR", "30004000039876543210")
COMPTES = {A: ("FR", "BNP Paribas"), B: ("DE", "Deutsche Bank"), C: ("FR", "BNP Paribas")}

# (date/heure, IBAN origine, IBAN destinataire, montant)
FICHIER_1 = [
    ("2026-01-05 08:00:00", A, B, "100.00"),
    ("2026-01-05 09:15:00", A, C, "5000.00"),    # limite exacte : NON flaggé
    ("2026-01-05 10:30:00", B, A, "5000.01"),    # juste au-dessus : flaggé
    ("2026-01-05 11:45:00", C, B, "250.50"),
    ("2026-01-05 13:00:00", A, B, "12000.00"),   # flaggé
]
FICHIER_2 = [
    ("2026-01-06 08:00:00", B, C, "49.50"),
    ("2026-01-06 09:00:00", C, A, "7500.00"),    # flaggé
    ("2026-01-06 10:00:00", A, C, "0.50"),
    ("2026-01-06 11:00:00", B, A, "300.00"),
    ("2026-01-06 12:00:00", C, B, "1000.00"),
]

# Résultats attendus (en centimes) après traitement des DEUX fichiers.
ATTENDU_ENVOYE_PAR_IBAN = {A: 1_710_050, B: 534_951, C: 875_050}
ATTENDU_ENVOYE_PAR_BANQUE = {"BNP Paribas": 2_585_100, "Deutsche Bank": 534_951}
ATTENDU_RECU_PAR_IBAN = {A: 1_280_001, B: 1_335_050, C: 505_000}
ATTENDU_MONTANTS_FLAGGES = {500_001, 1_200_000, 750_000}
NB_TRANSACTIONS = 10


def ecrire_csv(chemin: Path, lignes) -> Path:
    with chemin.open("w", newline="", encoding="utf-8") as fichier:
        writer = csv.DictWriter(fichier, fieldnames=COLONNES)
        writer.writeheader()
        for date, origine, destinataire, montant in lignes:
            writer.writerow({
                "datetime_transaction": date,
                "iban_origine": origine,
                "pays_source": COMPTES[origine][0],
                "banque_source": COMPTES[origine][1],
                "iban_destinataire": destinataire,
                "pays_destinataire": COMPTES[destinataire][0],
                "montant": montant,
            })
    return chemin
