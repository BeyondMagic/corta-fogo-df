FROM python:3.11-slim

WORKDIR /app/transformacao

ENV PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/app/transformacao

RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
 && python -c "import duckdb; c = duckdb.connect(); [c.install_extension(e) for e in ('delta', 'spatial', 'postgres')]"

COPY . .

ENTRYPOINT ["dbt"]
CMD ["run"]
