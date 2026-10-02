"""Mécanisme de retry (nouvelles tentatives automatiques) et simulateur de panne temporaire."""
import logging
import sqlite3
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)

# Erreurs considérées comme TEMPORAIRES (base verrouillée, indisponible...) : on réessaie.
# Les autres (contrainte violée, donnée invalide...) ne sont PAS réessayées : réessayer ne
# changerait rien, elles remontent immédiatement.
ERREURS_TEMPORAIRES = (sqlite3.OperationalError,)


class RetryEpuiseError(RuntimeError):
    """Le nombre maximal de tentatives a été atteint sans succès."""


def executer_avec_retry(
    operation: Callable[[], T],
    *,
    description: str = "l'opération",
    max_tentatives: int = 3,
    delai_initial: float = 1.0,
    facteur: float = 2.0,
    erreurs_temporaires: tuple[type[BaseException], ...] = ERREURS_TEMPORAIRES,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Exécute `operation` ; en cas d'erreur temporaire, attend puis réessaie.

    Délai d'attente exponentiel : delai_initial, puis x facteur à chaque tentative
    (1 s, 2 s, 4 s...). Lève RetryEpuiseError après `max_tentatives` échecs.
    """
    if max_tentatives < 1:
        raise ValueError("max_tentatives doit être >= 1")

    for tentative in range(1, max_tentatives + 1):
        try:
            resultat = operation()
        except erreurs_temporaires as erreur:
            logger.warning(
                "Échec de %s (tentative %d/%d) : %s",
                description, tentative, max_tentatives, erreur,
            )
            if tentative == max_tentatives:
                logger.error("Abandon de %s après %d tentatives.", description, max_tentatives)
                raise RetryEpuiseError(
                    f"échec de {description} après {max_tentatives} tentatives "
                    f"(dernière erreur : {erreur})"
                ) from erreur
            delai = delai_initial * facteur ** (tentative - 1)
            logger.info("Nouvelle tentative dans %.1f s...", delai)
            sleep(delai)
        else:
            if tentative > 1:
                logger.info("Succès de %s à la tentative %d/%d.", description, tentative, max_tentatives)
            return resultat

    raise AssertionError("inatteignable")


class SimulateurPanneBDD:
    """Fait échouer les `nb_pannes` premières tentatives d'insertion avec une erreur temporaire."""

    def __init__(self, nb_pannes: int = 0):
        self.pannes_restantes = nb_pannes

    def declencher_si_prevu(self) -> None:
        if self.pannes_restantes > 0:
            self.pannes_restantes -= 1
            raise sqlite3.OperationalError("database is locked (panne temporaire simulée)")
        
        