"""Tests d'intégration : pipeline complète, de la lecture des CSV jusqu'à la base de données."""
import shutil
from decimal import Decimal

import pytest

from pipeline.loader import FichierCSVInvalide, charger_csv, lister_fichiers_csv
from pipeline.main import executer_pipeline, main
from tests.jeu_de_donnees import (
    A,
    ATTENDU_ENVOYE_PAR_BANQUE,
    ATTENDU_ENVOYE_PAR_IBAN,
    ATTENDU_MONTANTS_FLAGGES,
    ATTENDU_RECU_PAR_IBAN,
    B,
    NB_TRANSACTIONS,
)


def _lancer(dossier, bdd, **options):
    return executer_pipeline(dossier, bdd, generer=False, sleep=lambda _: None, **options)


def test_donnees_bien_inserees(dossier_connu, chemin_bdd, requete):
    rapport = _lancer(dossier_connu, chemin_bdd)
    assert rapport.fichiers_inseres == 2
    assert requete("SELECT COUNT(*) FROM processed_files") == [(2,)]
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]


def test_valeurs_enregistrees_correctes(dossier_connu, chemin_bdd, requete):
    _lancer(dossier_connu, chemin_bdd)
    ligne = requete(
        "SELECT datetime_transaction, iban_origine, pays_source, banque_source, "
        "iban_destinataire, pays_destinataire, montant_centimes "
        "FROM transactions WHERE datetime_transaction = '2026-01-05 08:00:00'"
    )
    assert ligne == [("2026-01-05 08:00:00", A, "FR", "BNP Paribas", B, "DE", 10_000)]


def test_traitements_produisent_les_resultats_attendus(dossier_connu, chemin_bdd, requete):
    _lancer(dossier_connu, chemin_bdd)
    assert dict(requete("SELECT * FROM total_envoye_par_iban")) == ATTENDU_ENVOYE_PAR_IBAN
    assert dict(requete("SELECT * FROM total_envoye_par_banque")) == ATTENDU_ENVOYE_PAR_BANQUE
    assert dict(requete("SELECT * FROM total_recu_par_iban")) == ATTENDU_RECU_PAR_IBAN


def test_flags_correctement_positionnes(dossier_connu, chemin_bdd, requete):
    _lancer(dossier_connu, chemin_bdd)
    flaggees = {m for (m,) in requete("SELECT montant_centimes FROM transactions WHERE flag_montant_eleve = 1")}
    assert flaggees == ATTENDU_MONTANTS_FLAGGES
    assert requete("SELECT flag_montant_eleve FROM transactions WHERE montant_centimes = 500000") == [(0,)]


def test_pas_de_doublon_si_pipeline_relancee(dossier_connu, chemin_bdd, requete):
    _lancer(dossier_connu, chemin_bdd)
    rapport = _lancer(dossier_connu, chemin_bdd)
    assert rapport.fichiers_inseres == 0
    assert rapport.fichiers_ignores == 2
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]
    assert dict(requete("SELECT * FROM total_envoye_par_iban")) == ATTENDU_ENVOYE_PAR_IBAN


def test_meme_contenu_sous_un_autre_nom_non_retraite(dossier_connu, chemin_bdd, requete):
    _lancer(dossier_connu, chemin_bdd)
    shutil.copy(dossier_connu / "fichier_1.csv", dossier_connu / "fichier_1_copie.csv")
    rapport = _lancer(dossier_connu, chemin_bdd)
    assert rapport.fichiers_ignores == 3
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]


def test_pipeline_complete_avec_generation(tmp_path, chemin_bdd, requete):
    dossier = tmp_path / "data"
    rapport = executer_pipeline(dossier, chemin_bdd, nb_fichiers=5, graine=42)
    transactions = [t for f in lister_fichiers_csv(dossier) for t in charger_csv(f)]
    total = int(sum(t.montant for t in transactions) * 100)

    assert rapport.fichiers_generes == rapport.fichiers_inseres == 5
    assert requete("SELECT COUNT(*) FROM transactions") == [(len(transactions),)]
    assert requete("SELECT SUM(total_centimes) FROM total_envoye_par_iban") == [(total,)]
    assert requete("SELECT SUM(total_centimes) FROM total_recu_par_iban") == [(total,)]
    attendues = sum(t.montant > Decimal("5000") for t in transactions)
    assert requete("SELECT COUNT(*) FROM transactions WHERE flag_montant_eleve = 1") == [(attendues,)]


def test_donnee_invalide_arrete_la_pipeline_sans_insertion(tmp_path, chemin_bdd):
    with pytest.raises(FichierCSVInvalide):
        executer_pipeline(tmp_path / "data", chemin_bdd, injecter_erreur=True)
    assert not chemin_bdd.exists()  # échec détecté avant même la création de la base


def test_code_retour_cli(tmp_path):
    base = ["--local", "--data-dir", str(tmp_path / "data"), "--db-path", str(tmp_path / "cli.db")]
    assert main(base) == 0
    assert main(["--local", "--data-dir", str(tmp_path / "ko"), "--db-path", str(tmp_path / "ko.db"),
                 "--inject-invalid"]) == 1
    