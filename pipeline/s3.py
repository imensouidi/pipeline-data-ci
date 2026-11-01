"""Niveau 2 — Stockage des CSV dans un service compatible S3 (SeaweedFS en local).

Le traitement ne lit plus les CSV directement depuis le dossier de génération : il les
récupère depuis le bucket S3, avec retry en cas d'indisponibilité temporaire.
"""
import logging
import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, ConnectTimeoutError, EndpointConnectionError, ReadTimeoutError

logger = logging.getLogger(__name__)


class ServiceS3Indisponible(RuntimeError):
    """Le service S3 répond par une erreur serveur (5xx) : on peut réessayer."""


class FichierS3Manquant(RuntimeError):
    """Un fichier envoyé n'est pas présent (ou incomplet) dans le bucket."""


# Erreurs réseau et serveur considérées comme temporaires pour la récupération depuis S3.
ERREURS_S3_TEMPORAIRES = (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError, ServiceS3Indisponible)


def creer_client(endpoint: str, access_key: str, secret_key: str, region: str = "us-east-1"):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        # Pas de retry interne de boto3 : c'est notre mécanisme (retry.py) qui réessaie, avec log.
        config=Config(retries={"max_attempts": 1}, connect_timeout=5, read_timeout=10),
    )


def client_depuis_environnement():
    """Crée le client à partir des variables d'environnement (utile en Docker)."""
    return creer_client(
        os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
        os.environ.get("S3_ACCESS_KEY", "admin"),
        os.environ.get("S3_SECRET_KEY", "admin"),
    )


def configurer_bucket(client, bucket: str) -> None:
    """Crée le bucket s'il n'existe pas encore."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as erreur:
        if erreur.response["Error"]["Code"] in ("404", "NoSuchBucket", "NotFound"):
            client.create_bucket(Bucket=bucket)
            logger.info("Bucket '%s' créé.", bucket)
        else:
            raise


def envoyer_fichiers(client, bucket: str, chemins: list[Path]) -> list[str]:
    """Envoie chaque CSV dans le bucket. Renvoie les clés (noms) des objets."""
    cles = []
    for chemin in chemins:
        client.upload_file(str(chemin), bucket, chemin.name)
        cles.append(chemin.name)
        logger.info("%s envoyé dans le bucket '%s'.", chemin.name, bucket)
    return cles


def verifier_presence(client, bucket: str, chemins: list[Path]) -> None:
    """Vérifie que chaque fichier est présent dans le bucket avec la même taille."""
    manquants = []
    for chemin in chemins:
        try:
            objet = client.head_object(Bucket=bucket, Key=chemin.name)
        except ClientError:
            manquants.append(chemin.name)
            continue
        if objet["ContentLength"] != chemin.stat().st_size:
            manquants.append(chemin.name)
    if manquants:
        raise FichierS3Manquant(f"absents ou incomplets dans le bucket '{bucket}' : {manquants}")
    logger.info("Vérification S3 : %d fichier(s) présent(s) et complets.", len(chemins))


def lister_cles_csv(client, bucket: str) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    cles = [
        objet["Key"]
        for page in paginator.paginate(Bucket=bucket)
        for objet in page.get("Contents", [])
        if objet["Key"].endswith(".csv")
    ]
    return sorted(cles)


def telecharger_fichier(client, bucket: str, cle: str, dossier_cache: Path) -> Path:
    """Télécharge un objet dans le dossier de travail. Erreur serveur 5xx -> ServiceS3Indisponible."""
    dossier_cache.mkdir(parents=True, exist_ok=True)
    destination = dossier_cache / cle
    try:
        client.download_file(bucket, cle, str(destination))
    except ClientError as erreur:
        status = erreur.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if status >= 500:
            raise ServiceS3Indisponible(f"erreur serveur S3 ({status}) pour {cle}") from erreur
        raise
    return destination


class SimulateurPanneS3:
    """Fait échouer les `nb_pannes` premiers téléchargements avec une erreur réseau."""

    def __init__(self, nb_pannes: int = 0, endpoint: str = "http://simulateur"):
        self.pannes_restantes = nb_pannes
        self.endpoint = endpoint

    def declencher_si_prevu(self) -> None:
        if self.pannes_restantes > 0:
            self.pannes_restantes -= 1
            raise EndpointConnectionError(endpoint_url=self.endpoint)


def attendre_service_s3(client, timeout: float = 60.0, intervalle: float = 2.0, sleep=None) -> None:
    """Attend que le service S3 réponde avant de lancer la pipeline.

    Le conteneur S3 est lancé par docker compose ; la pipeline vérifie qu'il est prêt
    avant la première étape, et échoue proprement s'il ne répond pas dans le délai.
    """
    import time

    sleep = sleep or time.sleep
    ecoule = 0.0
    while True:
        try:
            client.list_buckets()
            logger.info("Service S3 prêt.")
            return
        except (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError) as erreur:
            if ecoule >= timeout:
                raise ServiceS3Indisponible(
                    f"service S3 injoignable après {timeout:.0f} s : {erreur}"
                ) from erreur
            logger.info("Attente du service S3 (%.0f s)...", ecoule)
            sleep(intervalle)
            ecoule += intervalle
