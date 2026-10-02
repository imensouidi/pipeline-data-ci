"""Orchestration de la pipeline complète (exécutable automatiquement, en local comme en CI).

    1. génération des fichiers CSV
    2. chargement + traitement des données
    3. mise en place de la base relationnelle
    4. insertion des données traitées (avec retry et anti-doublons)
"""
import argparse
import logging
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

logger = logging.getLogger("pipeline")


@dataclass
class RapportPipeline:
    fichiers_generes: int = 0
    fichiers_lus: int = 0
    fichiers_inseres: int = 0
    fichiers_ignores: int = 0
    transactions_inserees: int = 0


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
) -> RapportPipeline:
    rapport = RapportPipeline()

    logger.info("=== Étape 1/4 : génération des fichiers CSV ===")
    if generer:
        chemins = generer_fichiers(dossier_donnees, nb_fichiers, graine, injecter_erreur)
        rapport.fichiers_generes = len(chemins)
        logger.info("%d fichier(s) généré(s) dans %s (graine=%d)", len(chemins), dossier_donnees, graine)
    else:
        logger.info("Génération désactivée : utilisation des fichiers existants.")

    logger.info("=== Étape 2/4 : chargement et traitement ===")
    lots = []
    for chemin in lister_fichiers_csv(dossier_donnees):
        transactions = charger_csv(chemin)  # lève FichierCSVInvalide si une donnée est incorrecte
        resultat = traiter_transactions(transactions)
        nb_flags = sum(t.flag_montant_eleve for t in resultat.transactions)
        logger.info("%s : %d transaction(s), %d flaggée(s)", chemin.name, len(transactions), nb_flags)
        lots.append((chemin.name, calculer_hash(chemin), resultat))
    rapport.fichiers_lus = len(lots)
    if not lots:
        logger.warning("Aucun fichier CSV trouvé dans %s", dossier_donnees)

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
    parser = argparse.ArgumentParser(description="Pipeline data : CSV -> traitement -> base SQL")
    parser.add_argument("--data-dir", default="data", help="dossier des fichiers CSV")
    parser.add_argument("--db-path", default="output/pipeline.db", help="fichier de base SQLite")
    parser.add_argument("--n-files", type=int, default=5, help="nombre de fichiers à générer")
    parser.add_argument("--seed", type=int, default=42, help="graine de génération")
    parser.add_argument("--skip-generation", action="store_true", help="ne pas générer de CSV")
    parser.add_argument("--inject-invalid", action="store_true",
                        help="injecte une donnée invalide (simulation d'échec)")
    parser.add_argument("--simulate-db-failures", type=int, default=0,
                        help="nombre de pannes temporaires simulées à l'insertion")
    parser.add_argument("--max-retries", type=int, default=3, help="nombre maximal de tentatives")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="délai initial entre tentatives (s)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
    args = _arguments(argv)
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
