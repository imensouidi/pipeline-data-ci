"""Modèles de données (immuables) partagés par toutes les étapes de la pipeline."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

COLONNES = (
    "datetime_transaction",
    "iban_origine",
    "pays_source",
    "banque_source",
    "iban_destinataire",
    "pays_destinataire",
    "montant",
)
FORMAT_DATETIME = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class Transaction:
    """Une transaction financière telle que lue dans un fichier CSV."""

    datetime_transaction: datetime
    iban_origine: str
    pays_source: str
    banque_source: str
    iban_destinataire: str
    pays_destinataire: str
    montant: Decimal


@dataclass(frozen=True)
class TransactionFlaggee(Transaction):
    """Transaction enrichie du flag 'montant élevé'."""

    flag_montant_eleve: bool = False
    