FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DAGSTER_HOME=/opt/dagster/home \
    DBT_PROFILES_DIR=/app/transformacao

RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/dagster/app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "import duckdb; c = duckdb.connect(); [c.install_extension(e) for e in ('delta', 'spatial', 'postgres')]"

RUN mkdir -p /opt/dagster/home /opt/dagster/storage
COPY dagster.yaml workspace.yaml /opt/dagster/home/
COPY corta_fogo_dagster ./corta_fogo_dagster

COPY demo_backfill.py demo_scd2_imovel.py ./
