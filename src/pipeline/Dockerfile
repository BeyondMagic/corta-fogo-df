FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin libgdal-dev gcc g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_CONFIG=/usr/bin/gdal-config

# shapely 2.0.4 falha ao montar MultiPolygon com furos vindo de GeoJSON (UCs do IBRAM têm essas geometrias).
RUN pip install --no-cache-dir geopandas==0.14.4 "shapely>=2.0.6" psycopg2-binary==2.9.9 deltalake pyarrow

COPY extract_camadas.py load_camadas.py batch_ingest.py ./

ENTRYPOINT ["sh", "-c", "python extract_camadas.py --camada todas && python load_camadas.py"]
