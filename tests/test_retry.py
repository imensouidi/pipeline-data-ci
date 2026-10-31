"""Tests du mécanisme de retry (étape 7) : pannes temporaires, arrêt après max tentatives, pas de doublon."""
import sqlite3

import pytest

from pipeline.main import executer_pipeline
from pipeline.retry import RetryEpuiseError, executer_avec_retry
from tests.jeu_de_donnees import NB_TRANSACTIONS


def test_retry_reussit_apres_erreurs_temporaires():
    appels = []
    delais = []

    def operation():
        appels.append(1)
        if len(appels) < 3:
            raise sqlite3.OperationalError("database is locked")
        return "ok"

    resultat = executer_avec_retry(operation, max_tentatives=3, delai_initial=0.1, sleep=delais.append)

    assert resultat == "ok"
    assert len(appels) == 3
    assert delais == pytest.approx([0.1, 0.2])  # attente exponentielle


def test_retry_abandonne_apres_max_tentatives():
    appels = []

    def operation():
        appels.append(1)
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(RetryEpuiseError, match="après 3 tentatives"):
        executer_avec_retry(operation, max_tentatives=3, sleep=lambda _: None)
    assert len(appels) == 3


def test_erreur_non_temporaire_pas_reessayee():
    appels = []

    def operation():
        appels.append(1)
        raise ValueError("donnée invalide")

    with pytest.raises(ValueError):
        executer_avec_retry(operation, max_tentatives=3, sleep=lambda _: None)
    assert len(appels) == 1


def test_pannes_sous_le_seuil_pas_de_doublon(dossier_connu, chemin_bdd, requete):
    rapport = executer_pipeline(
        dossier_connu, chemin_bdd, generer=False, pannes_simulees=2,
        max_tentatives=3, sleep=lambda _: None,
    )

    assert rapport.fichiers_inseres == 2
    assert requete("SELECT COUNT(*) FROM processed_files") == [(2,)]
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]


def test_pannes_au_dessus_du_seuil_arrete_la_pipeline(dossier_connu, chemin_bdd, requete):
    with pytest.raises(RetryEpuiseError):
        executer_pipeline(
            dossier_connu, chemin_bdd, generer=False, pannes_simulees=10,
            max_tentatives=3, sleep=lambda _: None,
        )

    # La panne a eu lieu au milieu de l'insertion : rollback complet, rien n'est enregistré.
    assert requete("SELECT COUNT(*) FROM processed_files") == [(0,)]
    assert requete("SELECT COUNT(*) FROM transactions") == [(0,)]


def test_relance_apres_panne_ne_cree_pas_de_doublon(dossier_connu, chemin_bdd, requete):
    with pytest.raises(RetryEpuiseError):
        executer_pipeline(
            dossier_connu, chemin_bdd, generer=False, pannes_simulees=10,
            max_tentatives=3, sleep=lambda _: None,
        )
    rapport = executer_pipeline(
        dossier_connu, chemin_bdd, generer=False, sleep=lambda _: None,
    )

    assert rapport.fichiers_inseres == 2
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]
