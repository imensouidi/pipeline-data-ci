"""Étape 2b — Traitements métier. Toutes les fonctions de ce module sont PURES :

- elles ne modifient jamais les données reçues (les transactions sont immuables
  et chaque fonction renvoie de NOUVEAUX objets) ;
- elles ne dépendent d'aucun état externe (pas de fichier, base, variable globale
  modifiable, date courante ni hasard) ;
- elles renvoient toujours le même résultat pour les mêmes entrées.
"""
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields
from decimal import Decimal
from types import MappingProxyType

from pipeline.models import Transaction, TransactionFlaggee

SEUIL_MONTANT_ELEVE = Decimal("5000")


@dataclass(frozen=True)
class ResultatTraitement:
    transactions: tuple[TransactionFlaggee, ...]
    total_envoye_par_iban: Mapping[str, Decimal]
    total_envoye_par_banque: Mapping[str, Decimal]
    total_recu_par_iban: Mapping[str, Decimal]


def _somme_par(transactions: Iterable[Transaction], cle: Callable[[Transaction], str]) -> dict:
    totaux: dict[str, Decimal] = {}
    for transaction in transactions:
        k = cle(transaction)
        totaux[k] = totaux.get(k, Decimal("0")) + transaction.montant
    return totaux


def somme_envoyee_par_iban(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    return _somme_par(transactions, lambda t: t.iban_origine)


def somme_envoyee_par_banque(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    return _somme_par(transactions, lambda t: t.banque_source)


def somme_recue_par_iban(transactions: Iterable[Transaction]) -> dict[str, Decimal]:
    return _somme_par(transactions, lambda t: t.iban_destinataire)


def flagger_montants_eleves(
    transactions: Iterable[Transaction], seuil: Decimal = SEUIL_MONTANT_ELEVE
) -> tuple[TransactionFlaggee, ...]:
    """Flag = True si le montant est STRICTEMENT supérieur au seuil (5000.00 n'est pas flaggé)."""
    return tuple(
        TransactionFlaggee(
            **{champ.name: getattr(t, champ.name) for champ in fields(Transaction)},
            flag_montant_eleve=t.montant > seuil,
        )
        for t in transactions
    )


def traiter_transactions(transactions: Iterable[Transaction]) -> ResultatTraitement:
    """Applique l'ensemble des traitements et regroupe les résultats (lecture seule)."""
    transactions = tuple(transactions)
    return ResultatTraitement(
        transactions=flagger_montants_eleves(transactions),
        total_envoye_par_iban=MappingProxyType(somme_envoyee_par_iban(transactions)),
        total_envoye_par_banque=MappingProxyType(somme_envoyee_par_banque(transactions)),
        total_recu_par_iban=MappingProxyType(somme_recue_par_iban(transactions)),
    )