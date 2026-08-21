#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose=(docker compose --project-directory "${repository_root}" --file "${repository_root}/compose.test.yml")

cleanup() {
	"${compose[@]}" down --remove-orphans
}
trap cleanup EXIT INT TERM

"${compose[@]}" up --detach --wait test-db
"${compose[@]}" run --build --rm test-runner "$@"

docker build "${repository_root}" -f "${repository_root}/gestionale/Dockerfile" -t gv-gestionale-tests-gestionale
docker build "${repository_root}" -f "${repository_root}/gestionale-daemon/Dockerfile" -t gv-gestionale-tests-daemon
docker run --rm --network none --entrypoint python gv-gestionale-tests-gestionale -c "import shared.mail_riepilogo"
docker run --rm --network none --entrypoint python gv-gestionale-tests-daemon -c "import shared.mail_riepilogo"
