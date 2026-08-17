FROM python:3.11-slim

ENV TZ=Europe/Rome

WORKDIR /daemon

ENV PYTHONPATH=/

COPY ./gestionale-daemon/requirements.txt ./requirements.txt

RUN pip install -r requirements.txt

COPY ./shared /shared
COPY ./gestionale-daemon/daemon.py ./daemon.py
COPY ./gestionale-daemon/backfill_gv_iscrizione_id.py ./backfill_gv_iscrizione_id.py
COPY ./gestionale-daemon/mail_base.html ./mail_base.html

CMD ["python","daemon.py"]
