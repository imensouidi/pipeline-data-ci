"""Étapes 3 et 4 — Mise en place de la base relationnelle et insertion des données traitées.

L'insertion d'un fichier est ATOMIQUE : l'enregistrement dans `processed_files`,
les transactions et la mise à jour des totaux sont faits dans UNE seule transaction SQL.
Si une erreur survient au milieu, tout est annulé (rollback) : un retry repart d'une
base propre et ne peut donc pas créer de doublons.
"""
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pipeline.processing import ResultatTraitement

SCHEMA = Path(__file__).with_name("schema.sql")


class FichierDejaTraite(Exception):
    """Le contenu de ce fichier a déjà été inséré avec succès."""


def connecter(chemin_bdd: str | Path) -> sqlite3.Connection:
    Path(chemin_bdd).parent.mkdir(parents=True, exist_ok=True)
    connexion = sqlite3.connect(chemin_bdd)
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion


def initialiser_schema(connexion: sqlite3.Connection) -> None:
    connexion.executescript(SCHEMA.read_text(encoding="utf-8"))


def en_centimes(montant: Decimal) -> int:
    return int(montant * 100)


def fichier_deja_traite(connexion: sqlite3.Connection, hash_contenu: str) -> bool:
    ligne = connexion.execute(
        "SELECT 1 FROM processed_files WHERE hash_contenu = ?", (hash_contenu,)
    ).fetchone()
    return ligne is not None


def _cumuler(connexion: sqlite3.Connection, table: str, colonne: str, totaux) -> None:
    """Ajoute les totaux du fichier aux totaux existants (UPSERT)."""
    connexion.executemany(
        f"INSERT INTO {table} ({colonne}, total_centimes) VALUES (?, ?) "
        f"ON CONFLICT({colonne}) DO UPDATE SET total_centimes = total_centimes + excluded.total_centimes",
        [(cle, en_centimes(total)) for cle, total in sorted(totaux.items())],
    )


def inserer_resultat(
    connexion: sqlite3.Connection,
    nom_fichier: str,
    hash_contenu: str,
    resultat: ResultatTraitement,
    simulateur_panne=None,
) -> int:
    """Insère les données traitées d'un fichier en une seule transaction. Renvoie l'id du fichier."""
    try:
        with connexion:  # COMMIT si tout réussit, ROLLBACK en cas d'exception
            curseur = connexion.execute(
                "INSERT INTO processed_files (nom_fichier, hash_contenu, nb_transactions, traite_le) "
                "VALUES (?, ?, ?, ?)",
                (
                    nom_fichier,
                    hash_contenu,
                    len(resultat.transactions),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            fichier_id = curseur.lastrowid

            connexion.executemany(
                "INSERT INTO transactions (fichier_id, datetime_transaction, iban_origine, "
                "pays_source, banque_source, iban_destinataire, pays_destinataire, "
                "montant_centimes, flag_montant_eleve) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        fichier_id,
                        t.datetime_transaction.isoformat(sep=" "),
                        t.iban_origine,
                        t.pays_source,
                        t.banque_source,
                        t.iban_destinataire,
                        t.pays_destinataire,
                        en_centimes(t.montant),
                        int(t.flag_montant_eleve),
                    )
                    for t in resultat.transactions
                ],
            )

            # Panne simulée EN PLEIN MILIEU de la transaction (après des insertions partielles)
            # pour démontrer que le rollback empêche tout doublon lors du retry.
            if simulateur_panne is not None:
                simulateur_panne.declencher_si_prevu()

            _cumuler(connexion, "total_envoye_par_iban", "iban_origine", resultat.total_envoye_par_iban)
            _cumuler(connexion, "total_envoye_par_banque", "banque_source", resultat.total_envoye_par_banque)
            _cumuler(connexion, "total_recu_par_iban", "iban_destinataire", resultat.total_recu_par_iban)
    except sqlite3.IntegrityError as erreur:
        # Cas d'une tentative précédente qui aurait en réalité abouti : on ne réinsère pas.
        if "processed_files.hash_contenu" in str(erreur):
            raise FichierDejaTraite(nom_fichier) from erreur
        raise
    return fichier_id


def statistiques(connexion: sqlite3.Connection) -> dict[str, int]:
    requetes = {
        "fichiers": "SELECT COUNT(*) FROM processed_files",
        "transactions": "SELECT COUNT(*) FROM transactions",
        "transactions_flaggees": "SELECT COUNT(*) FROM transactions WHERE flag_montant_eleve = 1",
    }
    return {nom: connexion.execute(sql).fetchone()[0] for nom, sql in requetes.items()}