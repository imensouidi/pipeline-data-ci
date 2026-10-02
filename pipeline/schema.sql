-- Schéma de la base relationnelle (SQLite). Idempotent : peut être rejoué sans risque.
-- Les montants sont stockés en CENTIMES (entiers) pour éviter les erreurs d'arrondi des flottants.

-- Registre des fichiers déjà traités : garantit qu'un fichier n'est jamais inséré deux fois.
CREATE TABLE IF NOT EXISTS processed_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_fichier     TEXT    NOT NULL,
    hash_contenu    TEXT    NOT NULL UNIQUE,          -- SHA-256 du contenu
    nb_transactions INTEGER NOT NULL CHECK (nb_transactions > 0),
    traite_le       TEXT    NOT NULL                  -- horodatage ISO 8601 (UTC)
);

-- Transactions détaillées, avec leur flag "montant élevé".
CREATE TABLE IF NOT EXISTS transactions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    fichier_id           INTEGER NOT NULL REFERENCES processed_files(id),
    datetime_transaction TEXT    NOT NULL,
    iban_origine         TEXT    NOT NULL,
    pays_source          TEXT    NOT NULL CHECK (length(pays_source) = 2),
    banque_source        TEXT    NOT NULL,
    iban_destinataire    TEXT    NOT NULL,
    pays_destinataire    TEXT    NOT NULL CHECK (length(pays_destinataire) = 2),
    montant_centimes     INTEGER NOT NULL CHECK (montant_centimes > 0),
    flag_montant_eleve   INTEGER NOT NULL CHECK (flag_montant_eleve IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_transactions_fichier ON transactions(fichier_id);

-- Résultats des agrégations (cumulés sur l'ensemble des fichiers traités).
CREATE TABLE IF NOT EXISTS total_envoye_par_iban (
    iban_origine   TEXT    PRIMARY KEY,
    total_centimes INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS total_envoye_par_banque (
    banque_source  TEXT    PRIMARY KEY,
    total_centimes INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS total_recu_par_iban (
    iban_destinataire TEXT    PRIMARY KEY,
    total_centimes    INTEGER NOT NULL
);