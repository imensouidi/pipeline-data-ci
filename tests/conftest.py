import sqlite3

import pytest

from tests.jeu_de_donnees import FICHIER_1, FICHIER_2, ecrire_csv


@pytest.fixture
def dossier_connu(tmp_path):
    """Dossier contenant les deux fichiers CSV du jeu de données connu."""
    dossier = tmp_path / "data"
    dossier.mkdir()
    ecrire_csv(dossier / "fichier_1.csv", FICHIER_1)
    ecrire_csv(dossier / "fichier_2.csv", FICHIER_2)
    return dossier


@pytest.fixture
def chemin_bdd(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def requete(chemin_bdd):
    """Exécute une requête SQL sur la base de test et renvoie toutes les lignes."""
    def _requete(sql, params=()):
        with sqlite3.connect(chemin_bdd) as connexion:
            return connexion.execute(sql, params).fetchall()
    return _requete
