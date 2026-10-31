# Pipeline data CI

Pipeline de données : génération de transactions CSV, stockage dans un service S3 (SeaweedFS), traitement, insertion dans une base SQLite, avec tests d'intégration, retry et déploiement automatisé.

## Architecture

```
Génération CSV -> Upload S3 (bucket "transactions") -> Vérification
                                                         |
                                                         v
                            Téléchargement S3 (retry) -> Chargement -> Traitement -> Base SQLite
```

- `pipeline/generator.py` : génère les CSV (graine fixe, IBAN valides, cas limites).
- `pipeline/loader.py` : valide chaque ligne du CSV (aucun calcul).
- `pipeline/processing.py` : traitements purs (sommes, flag > 5000).
- `pipeline/s3.py` : envoi, vérification et récupération des fichiers S3.
- `pipeline/retry.py` : retry avec attente exponentielle et simulateur de pannes.
- `pipeline/database.py` + `schema.sql` : insertion atomique, anti-doublon par hash SHA-256.
- `infra/` : infrastructure Azure (Terraform).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
```

## Tests et qualité

```bash
ruff check .
python -m pytest
```

Les tests utilisent un faux S3 en mémoire (moto) : aucun service externe n'est nécessaire.

## Lancer la pipeline

Mode local (CSV lus depuis le dossier, sans S3) :

```bash
python -m pipeline --local --n-files 5 --seed 42
```

Mode S3 (nécessite un service S3, voir ci-dessous) :

```bash
python -m pipeline --n-files 5 --seed 42
```

Options utiles :

| Option | Rôle |
|---|---|
| `--inject-invalid` | injecte une donnée invalide (simulation d'échec) |
| `--simulate-db-failures N` | N pannes temporaires à l'insertion |
| `--simulate-s3-failures N` | N pannes temporaires au téléchargement S3 |
| `--max-retries N` | nombre maximal de tentatives |
| `--every S` | relance la pipeline toutes les S secondes |

## Service S3 local (Docker)

```bash
docker compose up --build
```

Lance SeaweedFS (port 8333) et la pipeline, qui tourne toutes les 5 minutes.

## Déploiement sur Azure

Prérequis : Azure CLI, Terraform, un compte Docker Hub, et un abonnement Azure.

```bash
az login
cd infra
cp terraform.tfvars.example terraform.tfvars   # à remplir : subscription_id, pipeline_image
terraform init
terraform plan
terraform apply
```

Le fichier `terraform.tfvars` contient des secrets : il n'est jamais versionné.

Vérifier les logs :

```bash
az container logs --resource-group rg-pipeline-data --name ci-pipeline-data --container-name pipeline
```

Supprimer les ressources :

```bash
terraform destroy
```

## CI/CD

- `.github/workflows/ci.yml` : à chaque push et pull request, vérifie le code (ruff), exécute la pipeline en local, construit l'image Docker et lance les tests.
- `.github/workflows/cd.yml` : à chaque push sur `main`, publie l'image sur Docker Hub, puis déploie l'infrastructure Azure avec Terraform.

Secrets GitHub nécessaires pour le CD : `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `AZURE_CREDENTIALS`, `AZURE_SUBSCRIPTION_ID`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.

## Scénario d'échec et retry

Voir le rapport (captures d'écran) pour la démonstration complète : CSV invalide, puis correction ; pannes temporaires à l'insertion et au téléchargement S3.
