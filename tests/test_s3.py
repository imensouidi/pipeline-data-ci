"""Tests du niveau 2 : stockage S3 (simulé avec moto), lecture depuis S3, retry et anti-doublon."""
import pytest
from moto import mock_aws

from pipeline.loader import lister_fichiers_csv
from pipeline.main import executer_pipeline
from pipeline.retry import RetryEpuiseError
from pipeline.s3 import (
    FichierS3Manquant,
    configurer_bucket,
    creer_client,
    envoyer_fichiers,
    lister_cles_csv,
    verifier_presence,
)
from tests.jeu_de_donnees import NB_TRANSACTIONS

BUCKET = "transactions-test"


@pytest.fixture
def s3():
    """Faux service S3 en mémoire, avec un bucket prêt."""
    with mock_aws():
        client = creer_client(None, "test", "test")
        configurer_bucket(client, BUCKET)
        yield client


def _lancer(client, dossier, bdd, **options):
    return executer_pipeline(
        dossier, bdd, generer=False, client_s3=client, bucket=BUCKET,
        sleep=lambda _: None, **options,
    )


def test_envoi_et_verification_dans_le_bucket(s3, dossier_connu):
    chemins = lister_fichiers_csv(dossier_connu)
    envoyer_fichiers(s3, BUCKET, chemins)
    verifier_presence(s3, BUCKET, chemins)  # ne lève rien si tout est présent
    assert lister_cles_csv(s3, BUCKET) == sorted(c.name for c in chemins)


def test_verification_detecte_un_fichier_absent(s3, dossier_connu):
    chemins = lister_fichiers_csv(dossier_connu)
    envoyer_fichiers(s3, BUCKET, chemins[:1])  # un seul fichier envoyé
    with pytest.raises(FichierS3Manquant):
        verifier_presence(s3, BUCKET, chemins)


def test_pipeline_lit_les_donnees_depuis_s3(s3, dossier_connu, tmp_path, requete, chemin_bdd):
    envoyer_fichiers(s3, BUCKET, lister_fichiers_csv(dossier_connu))
    # Le dossier local n'est PAS utilisé : tout doit venir du bucket.
    dossier_vide = tmp_path / "vide"
    dossier_vide.mkdir()

    rapport = _lancer(s3, dossier_vide, chemin_bdd)

    assert rapport.fichiers_inseres == 2
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]


def test_pipeline_complete_avec_envoi_s3(s3, tmp_path, requete, chemin_bdd):
    rapport = executer_pipeline(
        tmp_path / "data", chemin_bdd, nb_fichiers=5, graine=42,
        client_s3=s3, bucket=BUCKET, sleep=lambda _: None,
    )
    assert rapport.fichiers_generes == rapport.fichiers_inseres == 5
    assert len(lister_cles_csv(s3, BUCKET)) == 5


def test_retry_sous_le_seuil_recupere_les_fichiers(s3, dossier_connu, tmp_path, requete, chemin_bdd):
    envoyer_fichiers(s3, BUCKET, lister_fichiers_csv(dossier_connu))
    rapport = _lancer(s3, tmp_path / "vide", chemin_bdd, pannes_s3_simulees=2, max_tentatives=3)
    assert rapport.fichiers_inseres == 2
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]


def test_retry_au_dessus_du_seuil_arrete_proprement(s3, dossier_connu, tmp_path, chemin_bdd):
    envoyer_fichiers(s3, BUCKET, lister_fichiers_csv(dossier_connu))
    with pytest.raises(RetryEpuiseError):
        _lancer(s3, tmp_path / "vide", chemin_bdd, pannes_s3_simulees=10, max_tentatives=3)
    # Le fichier reste inaccessible : la pipeline s'arrête avant toute écriture en base.
    assert not chemin_bdd.exists()


def test_relance_s3_pas_de_doublon(s3, dossier_connu, tmp_path, requete, chemin_bdd):
    envoyer_fichiers(s3, BUCKET, lister_fichiers_csv(dossier_connu))
    _lancer(s3, tmp_path / "vide", chemin_bdd)
    rapport = _lancer(s3, tmp_path / "vide", chemin_bdd)
    assert rapport.fichiers_inseres == 0
    assert rapport.fichiers_ignores == 2
    assert requete("SELECT COUNT(*) FROM transactions") == [(NB_TRANSACTIONS,)]
