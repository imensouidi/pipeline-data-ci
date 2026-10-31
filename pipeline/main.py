"""Orchestration de la pipeline complète (exécutable automatiquement, en local comme en CI).

    1. génération des fichiers CSV (puis envoi dans le bucket S3 si un client S3 est fourni)
    2. récupération depuis S3 (avec retry) + chargement + traitement
    3. mise en place de la base relationnelle
    4. insertion des données traitées (avec retry et anti-doublons)
"""
import argparse
import logging
import tempfile
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from pipeline.database import (
    FichierDejaTraite,
    connecter,
    fichier_deja_traite,
    initialiser_schema,
    inserer_resultat,
    statistiques,
)
from pipeline.generator import generer_fichiers
from pipeline.loader import FichierCSVInvalide, calculer_hash, charger_csv, lister_fichiers_csv
from pipeline.processing import traiter_transactions
from pipeline.retry import RetryEpuiseError, SimulateurPanneBDD, executer_avec_retry
from pipeline.s3 import (
    ERREURS_S3_TEMPORAIRES,
    SimulateurPanneS3,
    client_depuis_environnement,
    configurer_bucket,
    envoyer_fichiers,
    lister_cles_csv,
    telecharger_fichier,
    verifier_presence,
)

logger = logging.getLogger("pipeline")


@dataclass
class RapportPipeline:
    fichiers_generes: int = 0
    fichiers_lus: int = 0
    fichiers_inseres: int = 0
    fichiers_ignores: int = 0
    transactions_inserees: int = 0


def _charger_et_traiter(chemins: list[Path]) -> list[tuple[str, str, object]]:
    lots = []
    for chemin in chemins:
        transactions = charger_csv(chemin)  # lève FichierCSVInvalide si une donnée est incorrecte
        resultat = traiter_transactions(transactions)
        nb_flags = sum(t.flag_montant_eleve for t in resultat.transactions)
        logger.info("%s : %d transaction(s), %d flaggée(s)", chemin.name, len(transactions), nb_flags)
        lots.append((chemin.name, calculer_hash(chemin), resultat))
    return lots


def _recuperer_depuis_s3(client, bucket, dossier_cache, max_tentatives, delai_retry, sleep, simulateur):
    """Télécharge chaque CSV du bucket (avec retry) et renvoie les chemins locaux de travail."""
    chemins = []
    for cle in lister_cles_csv(client, bucket):
        def operation(cle=cle):
            simulateur.declencher_si_prevu()
            return telecharger_fichier(client, bucket, cle, dossier_cache)

        chemins.append(
            executer_avec_retry(
                operation,
                description=f"la récupération de {cle} depuis S3",
                max_tentatives=max_tentatives,
                delai_initial=delai_retry,
                erreurs_temporaires=ERREURS_S3_TEMPORAIRES,
                sleep=sleep,
            )
        )
    return chemins


def executer_pipeline(
    dossier_donnees: str | Path,
    chemin_bdd: str | Path,
    *,
    generer: bool = True,
    nb_fichiers: int = 5,
    graine: int = 42,
    injecter_erreur: bool = False,
    pannes_simulees: int = 0,
    max_tentatives: int = 3,
    delai_retry: float = 1.0,
    sleep=time.sleep,
    client_s3=None,
    bucket: str = "transactions",
    pannes_s3_simulees: int = 0,
) -> RapportPipeline:
    rapport = RapportPipeline()

    logger.info("=== Étape 1/4 : génération des fichiers CSV ===")
    if generer:
        chemins = generer_fichiers(dossier_donnees, nb_fichiers, graine, injecter_erreur)
        rapport.fichiers_generes = len(chemins)
        logger.info("%d fichier(s) généré(s) dans %s (graine=%d)", len(chemins), dossier_donnees, graine)
        if client_s3 is not None:
            configurer_bucket(client_s3, bucket)
            envoyer_fichiers(client_s3, bucket, chemins)
            verifier_presence(client_s3, bucket, chemins)
    else:
        logger.info("Génération désactivée : utilisation des fichiers existants.")

    logger.info("=== Étape 2/4 : chargement et traitement ===")
    with tempfile.TemporaryDirectory() as dossier_cache:
        if client_s3 is not None:
            chemins_csv = _recuperer_depuis_s3(
                client_s3, bucket, Path(dossier_cache), max_tentatives, delai_retry, sleep,
                SimulateurPanneS3(pannes_s3_simulees),
            )
        else:
            chemins_csv = lister_fichiers_csv(dossier_donnees)
        lots = _charger_et_traiter(chemins_csv)
    rapport.fichiers_lus = len(lots)
    if not lots:
        logger.warning("Aucun fichier CSV trouvé (dossier %s / bucket %s)", dossier_donnees, bucket)

    logger.info("=== Étape 3/4 : mise en place de la base de données ===")
    connexion = connecter(chemin_bdd)
    try:
        initialiser_schema(connexion)
        logger.info("Schéma prêt : %s", chemin_bdd)

        logger.info("=== Étape 4/4 : insertion des données traitées ===")
        simulateur = SimulateurPanneBDD(pannes_simulees)
        for nom, hash_contenu, resultat in lots:
            if fichier_deja_traite(connexion, hash_contenu):
                logger.info("%s déjà traité (hash %s...) : ignoré", nom, hash_contenu[:12])
                rapport.fichiers_ignores += 1
                continue
            try:
                executer_avec_retry(
                    partial(inserer_resultat, connexion, nom, hash_contenu, resultat, simulateur),
                    description=f"l'insertion de {nom}",
                    max_tentatives=max_tentatives,
                    delai_initial=delai_retry,
                    sleep=sleep,
                )
            except FichierDejaTraite:
                logger.info("%s déjà traité : ignoré", nom)
                rapport.fichiers_ignores += 1
                continue
            rapport.fichiers_inseres += 1
            rapport.transactions_inserees += len(resultat.transactions)
            logger.info("%s inséré (%d transactions)", nom, len(resultat.transactions))

        stats = statistiques(connexion)
        logger.info(
            "Base : %d fichier(s), %d transaction(s) dont %d flaggée(s)",
            stats["fichiers"], stats["transactions"], stats["transactions_flaggees"],
        )
    finally:
        connexion.close()

    return rapport


def _arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline data : CSV -> S3 -> traitement -> base SQL")
    parser.add_argument("--data-dir", default="data", help="dossier de génération des CSV")
    parser.add_argument("--db-path", default="output/pipeline.db", help="fichier de base SQLite")
    parser.add_argument("--n-files", type=int, default=5, help="nombre de fichiers à générer")
    parser.add_argument("--seed", type=int, default=42, help="graine de génération")
    parser.add_argument("--skip-generation", action="store_true", help="ne pas générer de CSV")
    parser.add_argument("--inject-invalid", action="store_true",
                        help="injecte une donnée invalide (simulation d'échec)")
    parser.add_argument("--simulate-db-failures", type=int, default=0,
                        help="nombre de pannes temporaires simulées à l'insertion")
    parser.add_argument("--simulate-s3-failures", type=int, default=0,
                        help="nombre de pannes temporaires simulées au téléchargement S3")
    parser.add_argument("--max-retries", type=int, default=3, help="nombre maximal de tentatives")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="délai initial entre tentatives (s)")
    parser.add_argument("--local", action="store_true",
                        help="lire les CSV depuis le dossier local au lieu de S3 (sans S3)")
    parser.add_argument("--bucket", default="transactions", help="bucket S3 utilisé")
    parser.add_argument("--every", type=int, default=0,
                        help="relancer la pipeline toutes les N secondes (0 = une seule fois)")
    return parser.parse_args(argv)


def _executer_une_fois(args) -> int:
    client = None if args.local else client_depuis_environnement()
    try:
        rapport = executer_pipeline(
            args.data_dir,
            args.db_path,
            generer=not args.skip_generation,
            nb_fichiers=args.n_files,
            graine=args.seed,
            injecter_erreur=args.inject_invalid,
            pannes_simulees=args.simulate_db_failures,
            max_tentatives=args.max_retries,
            delai_retry=args.retry_delay,
            client_s3=client,
            bucket=args.bucket,
            pannes_s3_simulees=args.simulate_s3_failures,
        )
    except FichierCSVInvalide as erreur:
        logger.error("ÉCHEC - donnée invalide : %s", erreur)
        logger.error("Pipeline arrêtée avant toute insertion en base.")
        return 1
    except RetryEpuiseError as erreur:
        logger.error("ÉCHEC - %s", erreur)
        logger.error("Pipeline arrêtée : nombre maximal de tentatives dépassé.")
        return 2

    logger.info("SUCCÈS - %s", rapport)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
    args = _arguments(argv)
    if args.every <= 0:
        return _executer_une_fois(args)

    # Mode planifié : la pipeline tourne en boucle, une erreur ne doit pas arrêter le planificateur.
    logger.info("Mode planifié : exécution toutes les %d s (Ctrl+C pour arrêter).", args.every)
    while True:
        _executer_une_fois(args)
        time.sleep(args.every)
