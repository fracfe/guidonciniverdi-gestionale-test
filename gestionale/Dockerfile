FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /gestionale_gv

ENV PYTHONPATH=/

COPY ./gestionale/requirements.txt ./requirements.txt

RUN pip install -r requirements.txt

COPY ./shared /shared
COPY ./gestionale/app.py ./app.py
COPY ./gestionale/templates ./templates
COPY ./gestionale/static ./static
COPY ./gestionale/migrations ./migrations
COPY ./gestionale/docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
