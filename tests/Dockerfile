FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libglib2.0-0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY gestionale/requirements.txt /tmp/gestionale-requirements.txt
COPY gestionale-daemon/requirements.txt /tmp/gestionale-daemon-requirements.txt

RUN pip install --no-cache-dir \
    -r /tmp/gestionale-requirements.txt \
    -r /tmp/gestionale-daemon-requirements.txt
