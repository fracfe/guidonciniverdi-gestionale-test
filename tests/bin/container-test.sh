#!/usr/bin/env bash

set -euo pipefail

readonly expected_db_host="test-db"
readonly expected_db_name="gv_automated_test"
readonly expected_db_user="gv_automated_test"

if [[ "${DB_HOST:-}" == "gestionale-db" ]]; then
	echo "ERRORE: DB_HOST=gestionale-db punta al database runtime" >&2
	exit 1
fi
if [[ "${DB_NAME:-}" == "guidoncini_test" ]]; then
	echo "ERRORE: DB_NAME=guidoncini_test identifica il database runtime" >&2
	exit 1
fi
if [[ "${DB_HOST:-}" != "${expected_db_host}" \
	|| "${DB_NAME:-}" != "${expected_db_name}" \
	|| "${DB_USER:-}" != "${expected_db_user}" ]]; then
	echo "ERRORE: configurazione database diversa dall'istanza automatica consentita" >&2
	exit 1
fi

cd /app

git diff --check
python scripts/check_migrations.py
python -c "from shared.mail_riepilogo import genera_mail_riepilogo_iscrizione"
python -m unittest shared.test_mail_riepilogo -v
python -m unittest discover -s gestionale -p "test_*.py" -v
python -m unittest discover -s gestionale-daemon -p "test_*.py" -v

cd /app/gestionale
flask db upgrade
head_revision="$(flask db heads | awk 'NR == 1 { revision = $1 } END { if (NR != 1) exit 1; print revision }')"
flask db current | grep -F "${head_revision}"
RUN_MARIADB_INTEGRATION=1 python -m unittest test_mariadb_concorrenza.py -v
