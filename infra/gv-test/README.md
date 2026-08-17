# GV-TEST riproducibile

Questa configurazione usa esclusivamente servizi e credenziali di test. Non
inserire endpoint o segreti di produzione.

## Preparazione e avvio

Da `infra/gv-test`:

```sh
cp .env.example .env
# compilare i valori vuoti con credenziali dedicate esclusivamente a GV-TEST
docker compose config
docker compose up -d --build
```

Il file usa gli stessi nomi dell'attuale configurazione GV-TEST:

- `GV_DB_NAME`, `GV_DB_USER`, `GV_DB_PASSWORD`, `GV_DB_ROOT_PASSWORD`;
- `GV_SECRET_KEY`;
- `WP_DB_NAME`, `WP_DB_USER`, `WP_DB_PASSWORD`, `WP_DB_ROOT_PASSWORD`;
- `WP_API_USER`, `WP_API_PASSWORD`;
- `MAIL_USERNAME`, `TELEGRAM_TOKEN`;
- `WORDPRESS_SOURCE_DIR`.

`WORDPRESS_SOURCE_DIR` è obbligatoria e deve contenere un percorso assoluto
alla copia test del repository WordPress. L'esempio usa
`/opt/gv-test/wordpress`; non esiste un default relativo implicito.
Dopo il primo avvio completare l'installazione WordPress, attivare tema e plugin
test e creare un utente REST con application password dedicata. Copiare tali
credenziali soltanto nel `.env` non versionato.

Il daemon è nel profilo `integration`:

```sh
docker compose --profile integration up -d --build
```

Il Compose imposta `TELEGRAM_ENABLED=false`: anche se la migration iniziale abilita
il relativo record DB, il daemon non contatta Telegram. Un eventuale test Telegram
richiede di cambiare esplicitamente questo valore e usare un bot esclusivamente di
test.

## Migrazioni e inizializzazione

Il Gestionale esegue `flask db upgrade` all'avvio. Per eseguirlo o verificarlo
esplicitamente:

```sh
docker compose run --rm --entrypoint flask gestionale db upgrade
docker compose run --rm --entrypoint flask gestionale db current
docker compose run --rm --entrypoint flask gestionale db heads
```

Su un database nuovo, dopo le migration:

```sh
docker compose run --rm --entrypoint flask gestionale init_db
```

La password iniziale stampata da `init_db` va cambiata immediatamente in GV-TEST.

## Build e test isolati

Da root del repository:

```sh
docker build . -f gestionale/Dockerfile -t gv-test-gestionale
docker build . -f gestionale-daemon/Dockerfile -t gv-test-daemon
python -m unittest shared.test_mail_riepilogo -v
python -m unittest discover -s gestionale -p "test_*.py" -v
python -m unittest discover -s gestionale-daemon -p "test_*.py" -v
python scripts/check_migrations.py
git diff --check
```

Il test concorrenza richiede il MariaDB usa-e-getta della CI o un DB GV-TEST
dedicato e la variabile `RUN_MARIADB_INTEGRATION=1`; non va eseguito su database
con dati da preservare.

## Endpoint locali

- Gestionale: `http://localhost:${GESTIONALE_PORT:-5000}`
- WordPress: `http://localhost:${WORDPRESS_PORT:-8080}`
- Mailpit: `http://localhost:${MAILPIT_HTTP_PORT:-8025}`
- REST WordPress interno ai container: `http://wordpress/wp-json/wp/v2`

## Checklist operativa E2E

1. Modifica solo contatti: nessun `update_sq`, una mail completa in Mailpit.
2. Modifica dati WordPress: `update_sq`, auto-refresh, `DONE`, una mail completa.
3. Ferma WordPress, modifica dati WordPress: job `FAILED`, iscrizione ancora
   `abilitato`, nessuna mail; riavvia WordPress e usa **Riprova sincronizzazione**:
   nuovo job `DONE`, una sola mail finale.
4. Porta un caso a `failed_post`: la modifica non ritenta; **Riprova creazione
   pagina** riusa il `WordpressUser`, conserva il vecchio job `FAILED` e termina
   `abilitato`.
5. Reimposta password: verifica nuova login WordPress e riepilogo in Mailpit.
6. Prepara un `SENDING` più vecchio della soglia: verifica recovery a `PENDING`
   oppure `FAILED` al limite tentativi.
7. Prepara `in_abilitazione` senza job attivo: verifica warning e ripristino
   manuale, dopo controllo delle eventuali risorse remote.
8. Esegui il test MariaDB concorrente sulla stessa iscrizione: un solo job.
9. Eseguilo su iscrizioni diverse: entrambi i job vengono accodati senza lock
   globale.

Per simulare indisponibilità senza endpoint finti:

```sh
docker compose stop wordpress
docker compose start wordpress
docker compose logs gestionale-daemon
```

## Rollout riconciliazione WordPress

L'ordine e' vincolante: il nuovo daemon non deve essere avviato prima che il
plugin e il meta stabile siano disponibili.

1. Aggiornare e attivare per primo il plugin Guidoncini Verdi su GV-TEST.
2. Verificare con l'utenza REST tecnica che
   `GET /wp-json/guidonciniverdi/v1/provisioning/1` risponda `200` e restituisca
   esclusivamente le chiavi `user` e `post`. Un ID non associato deve produrre
   `{"user":null,"post":null}`; senza autenticazione la richiesta deve essere
   rifiutata.

   ```sh
   curl --fail-with-body --user "$WP_API_USER" \
     "http://localhost:${WORDPRESS_PORT:-8080}/wp-json/guidonciniverdi/v1/provisioning/1"
   ```

   Passare la password di test al prompt di `curl`, senza inserirla nella riga
   di comando o nei log.
3. Ricostruire l'immagine daemon, senza avviarla, ed eseguire il backfill in
   dry-run (modalita' predefinita):

   ```sh
   docker compose --profile integration build gestionale-daemon
   docker compose --profile integration run --rm --no-deps \
     --entrypoint python gestionale-daemon backfill_gv_iscrizione_id.py
   ```

4. Esaminare ogni riga `CONFLICT`. Non applicare il backfill finche' i mirror
   locali e le risorse GV-TEST non sono stati verificati. Il comando usa solo
   gli ID dei mirror locali, senza matching per username, titolo o altri dati.
5. Solo dopo un dry-run senza conflitti, applicare esplicitamente:

   ```sh
   docker compose --profile integration run --rm --no-deps \
     --entrypoint python gestionale-daemon backfill_gv_iscrizione_id.py --apply
   ```

6. Ripetere il dry-run: deve riportare `azioni=nessuna` e zero conflitti.
7. Avviare il nuovo daemon e verificare provisioning nuovo e retry dei casi
   `failed_user`/`failed_post`, controllando DB locale, endpoint e Mailpit:

   ```sh
   docker compose --profile integration up -d gestionale-daemon
   docker compose logs --since=10m gestionale-daemon
   ```

La stessa sequenza va ripetuta in produzione soltanto dopo l'esito positivo
completo su GV-TEST, con backup e finestra operativa approvati. Questi comandi
non devono essere eseguiti contro produzione durante lo sviluppo.
