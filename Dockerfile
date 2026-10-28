FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && rm -rf /var/lib/apt/lists/*

# App dependencies live in their own venv so they can't clash with the system
# Python packages GDAL's own scripts (gdal2tiles) rely on.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY planetcoveragefinder-main/ /tmp/planetcoveragefinder/
RUN pip install --no-cache-dir /tmp/planetcoveragefinder && rm -rf /tmp/planetcoveragefinder

COPY tile_service/ tile_service/

# gdal2tiles needs the system Python that has the GDAL bindings, not the venv.
# PL_API_KEY and TILE_BUCKET are injected by the ECS task definition at runtime.
ENV GDAL2TILES_CMD="/usr/bin/python3 -m osgeo_utils.gdal2tiles" \
    WORK_DIR=/tmp/tile-service \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 tiles
USER tiles

CMD ["python", "-m", "tile_service"]
