# Image de la pipeline (base indiquée dans les rappels Docker du cours)
FROM python:3.10.21-slim-trixie AS base

WORKDIR /app

# Dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline ./pipeline

# Adresse du service S3 (nom du service dans docker-compose)
ENV S3_ENDPOINT=http://s3:8333

CMD ["python", "-m", "pipeline"]
