import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_NAME"] = ":memory:"
os.environ["MAIL_USERNAME"] = "test@example.invalid"
os.environ["MAIL_HOST"] = "mailpit"
os.environ["MAIL_PORT"] = "1025"
os.environ["WORDPRESS_URL"] = "http://wordpress/wp-json/wp/v2"
os.environ["WORDPRESS_USER"] = "test-user"
os.environ["WORDPRESS_PASSWORD"] = "test-password"

import daemon  # noqa: E402


def risposta_http(status, payload=None, errore_json=None):
    risposta = Mock()
    risposta.status_code = status
    if errore_json:
        risposta.json.side_effect = errore_json
    else:
        risposta.json.return_value = payload
    return risposta


class WorkerWordpressTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        daemon.Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.header = {"Authorization": "Basic segreto-token"}

        session = self.session_factory()
        session.add_all(
            [
                daemon.SysOption(key="TemplatePost", value="10"),
                daemon.SysOption(key="AnnoCorrente", value="2026"),
            ]
        )
        session.commit()
        session.close()

    def tearDown(self):
        daemon.Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def aggiungi_iscrizione_e_job(self, id_record, username):
        session = self.session_factory()
        session.add(
            daemon.IscrizioneEG(
                id=id_record,
                data=datetime.now(),
                stato="in_abilitazione",
                nome=f"Squadriglia {id_record}",
                mail=f"sq{id_record}@example.invalid",
                regione=id_record,
                zona=id_record,
                gruppo=id_record,
                specialita="Natura",
                tipo="conquista",
                nome_capo_sq="Capo sq",
                nome_capo1="Capo uno",
                mail_capo1="capo1@example.invalid",
                cell_capo1="000",
                nome_capo2="Capo due",
                mail_capo2="capo2@example.invalid",
                cell_capo2="001",
                sesso="M",
                link="",
                anno_percorso=None,
            )
        )
        session.add(
            daemon.JobWordpress(
                id=id_record,
                data=datetime.now(),
                stato="PENDING",
                tipo="crea_sq",
                iscrizione_id=id_record,
                updated_at=datetime.now(),
                dati={
                    "iscrizione": id_record,
                    "tipo": "crea_sq",
                    "username": username,
                    "meta": {
                        "squadriglia": f"Squadriglia {id_record}",
                        "specialita": "Natura",
                    },
                },
            )
        )
        session.commit()
        session.close()

    def aggiungi_job_update(self, id_record=1):
        session = self.session_factory()
        session.add_all(
            [
                daemon.Regione(id=1, regione="test", mail="test@example.invalid"),
                daemon.Zona(id=1, zona="zona test", regione=1),
                daemon.Gruppo(id=1, gruppo="test 1", zona=1, regione=1),
                daemon.StatusPercorso(
                    id=1, anno="2025", iscrizioni=True, abilitazioni=True, regione=1
                ),
                daemon.IscrizioneEG(
                    id=id_record,
                    data=datetime.now(),
                    stato="abilitato",
                    nome="Nuovo nome",
                    mail="sq@example.invalid",
                    regione=1,
                    zona=1,
                    gruppo=1,
                    specialita="Natura",
                    tipo="conferma",
                    nome_capo_sq="Capo sq",
                    nome_capo1="Capo uno",
                    mail_capo1="capo1@example.invalid",
                    cell_capo1="000",
                    nome_capo2="Capo due",
                    mail_capo2="capo2@example.invalid",
                    cell_capo2="001",
                    sesso="M",
                    link="http://wordpress/post/30",
                    anno_percorso=1,
                ),
                daemon.WordpressUser(
                    data=datetime.now(), iscrizioni_id=id_record,
                    wordpress_id=20, username="username-stabile",
                    password="password-locale", meta={"roles": ["author"]},
                ),
            ]
        )
        session.flush()
        wordpress_user = session.query(daemon.WordpressUser).filter_by(
            iscrizioni_id=id_record
        ).one()
        session.add_all(
            [
                daemon.WordpressPost(
                    data=datetime.now(), iscrizioni_id=id_record,
                    wordpress_user_id=wordpress_user.id, wordpress_id=30,
                    tipo="posts", meta={"content": "contenuto esistente", "author": 20},
                ),
                daemon.JobWordpress(
                    id=id_record, data=datetime.now(), stato="PENDING",
                    tipo="update_sq", iscrizione_id=id_record,
                    updated_at=datetime.now(), attempts=0,
                    dati={"tipo": "update_sq", "iscrizione": id_record},
                ),
            ]
        )
        session.commit()
        session.close()

    def assert_stati(self, id_record, stato_job, stato_iscrizione):
        session = self.session_factory()
        self.assertEqual(session.get(daemon.JobWordpress, id_record).stato, stato_job)
        self.assertEqual(
            session.get(daemon.IscrizioneEG, id_record).stato,
            stato_iscrizione,
        )
        session.close()

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_errore_http_non_blocca_il_job_successivo(
        self, mock_post, mock_get, _mock_mail
    ):
        self.aggiungi_iscrizione_e_job(1, "prima")
        self.aggiungi_iscrizione_e_job(2, "seconda")
        mock_post.side_effect = [
            risposta_http(
                503,
                {
                    "code": "temporarily_unavailable",
                    "message": "segreto-token test-password",
                },
            ),
            risposta_http(201, {"id": 20}),
            risposta_http(201, {"id": 30}),
        ]
        mock_get.side_effect = [
            risposta_http(200, {"content": {"raw": "Template"}}),
            risposta_http(200, [{"name": "Natura", "id": 40}]),
            risposta_http(200, [{"name": "Pagina unica", "id": 50}]),
            risposta_http(200, {"link": "http://wordpress/post/30"}),
        ]

        with self.assertLogs(daemon.logger.name, level="ERROR") as log:
            daemon.processa_prossimo_job_wordpress(
                self.header, self.session_factory
            )
            daemon.processa_prossimo_job_wordpress(
                self.header, self.session_factory
            )

        self.assert_stati(1, "FAILED", "failed_user")
        self.assert_stati(2, "DONE", "abilitato")
        testo_log = "\n".join(log.output)
        self.assertIn("regione=1", testo_log)
        self.assertIn("endpoint=/users", testo_log)
        self.assertIn("status_http=503", testo_log)
        self.assertNotIn("segreto-token", testo_log)
        self.assertNotIn("test-password", testo_log)
        for chiamata in mock_post.call_args_list + mock_get.call_args_list:
            self.assertEqual(chiamata.kwargs["timeout"], (5, 30))

    @patch.object(daemon.requests, "post", side_effect=daemon.requests.Timeout())
    def test_timeout_viene_isolato_e_non_espone_segreti(self, _mock_post):
        self.aggiungi_iscrizione_e_job(1, "timeout-user")

        with self.assertLogs(daemon.logger.name, level="ERROR") as log:
            daemon.processa_prossimo_job_wordpress(
                self.header, self.session_factory
            )

        testo_log = "\n".join(log.output)
        self.assertIn("timeout HTTP", testo_log)
        self.assertIn("job_id=1", testo_log)
        self.assertIn("username=timeout-user", testo_log)
        self.assertNotIn("segreto-token", testo_log)
        self.assertNotIn("test-password", testo_log)
        session = self.session_factory()
        self.assertNotIn(
            "test-password", session.get(daemon.JobWordpress, 1).last_error
        )
        session.close()
        self.assert_stati(1, "FAILED", "failed_user")

    @patch.object(
        daemon.requests,
        "post",
        side_effect=daemon.requests.ConnectionError("test-password"),
    )
    def test_errore_connessione_viene_isolato_e_sanitizzato(self, _mock_post):
        self.aggiungi_iscrizione_e_job(1, "connection-user")

        with self.assertLogs(daemon.logger.name, level="ERROR") as log:
            daemon.processa_prossimo_job_wordpress(
                self.header, self.session_factory
            )

        self.assert_stati(1, "FAILED", "failed_user")
        testo_log = "\n".join(log.output)
        self.assertIn("errore di connessione", testo_log)
        self.assertNotIn("test-password", testo_log)
        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        self.assertEqual(job.last_error, "errore di connessione")
        session.close()

    @patch.object(daemon.requests, "post")
    def test_json_inatteso_viene_gestito(self, mock_post):
        self.aggiungi_iscrizione_e_job(1, "json-user")
        mock_post.return_value = risposta_http(
            201, errore_json=ValueError("non-json")
        )

        with self.assertLogs(daemon.logger.name, level="ERROR") as log:
            daemon.processa_prossimo_job_wordpress(
                self.header, self.session_factory
            )

        self.assertIn("risposta JSON non valida", "\n".join(log.output))
        self.assert_stati(1, "FAILED", "failed_user")

    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_errore_creazione_post_imposta_failed_post(
        self, mock_post, mock_get
    ):
        self.aggiungi_iscrizione_e_job(1, "post-user")
        mock_post.side_effect = [
            risposta_http(201, {"id": 20}),
            risposta_http(500, {"code": "rest_cannot_create"}),
        ]
        mock_get.side_effect = [
            risposta_http(200, {"content": {"raw": "Template"}}),
            risposta_http(200, [{"name": "Natura", "id": 40}]),
            risposta_http(200, [{"name": "Pagina unica", "id": 50}]),
        ]

        daemon.processa_prossimo_job_wordpress(
            self.header, self.session_factory
        )

        self.assert_stati(1, "FAILED", "failed_post")
        session = self.session_factory()
        self.assertEqual(session.query(daemon.WordpressUser).count(), 1)
        self.assertEqual(session.query(daemon.WordpressPost).count(), 0)
        session.close()

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_update_sq_aggiorna_solo_campi_previsti(
        self, mock_post, mock_get, _mock_mail
    ):
        self.aggiungi_job_update()
        mock_post.side_effect = [
            risposta_http(200, {"id": 20}),
            risposta_http(200, {"id": 30}),
        ]
        mock_get.return_value = risposta_http(
            200, [{"name": "Natura", "id": 40}]
        )

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "DONE", "abilitato")
        payload_utente = mock_post.call_args_list[0].kwargs["json"]
        payload_post = mock_post.call_args_list[1].kwargs["json"]
        self.assertEqual(set(payload_utente), {"name", "meta"})
        self.assertNotIn("username", payload_utente)
        self.assertNotIn("password", payload_utente)
        self.assertNotIn("roles", payload_utente)
        self.assertEqual(set(payload_post), {"title", "meta", "specialita"})
        self.assertNotIn("content", payload_post)
        self.assertNotIn("author", payload_post)
        self.assertEqual(payload_utente["meta"]["anno"], "2025")
        self.assertTrue(payload_utente["meta"]["rinnovo"])
        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        post = session.query(daemon.WordpressPost).one()
        self.assertEqual(job.attempts, 1)
        self.assertEqual(post.meta["content"], "contenuto esistente")
        self.assertEqual(post.meta["author"], 20)
        self.assertEqual(post.meta["specialita"], [40])
        session.close()
        _mock_mail.assert_called_once()
        self.assertEqual(_mock_mail.call_args.kwargs["anno"], "2025")
        corpo_mail = _mock_mail.call_args.args[3]
        for valore in [
            "Nuovo nome",
            "test",
            "zona test",
            "test 1",
            "Natura",
            "Conferma",
            "2025",
            "Capo sq",
            "sq@example.invalid",
            "username-stabile",
            "password-locale",
        ]:
            self.assertIn(valore, corpo_mail)
        self.assertNotIn("test-password", corpo_mail)
        self.assertNotIn("segreto-token", corpo_mail)

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_update_sq_partial_success_puo_essere_ritentato(
        self, mock_post, mock_get, _mock_mail
    ):
        self.aggiungi_job_update()
        mock_get.return_value = risposta_http(200, [{"name": "Natura", "id": 40}])
        mock_post.side_effect = [
            risposta_http(200, {"id": 20}),
            daemon.requests.Timeout(),
        ]
        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)
        self.assert_stati(1, "FAILED", "abilitato")

        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        job.stato = "PENDING"
        job.updated_at = datetime.now()
        session.commit()
        session.close()
        mock_post.side_effect = [
            risposta_http(200, {"id": 20}),
            risposta_http(200, {"id": 30}),
        ]
        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)
        self.assert_stati(1, "DONE", "abilitato")
        _mock_mail.assert_called_once()

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "post")
    def test_update_sq_404_diventa_failed_senza_creare_risorse(
        self, mock_post, mock_mail
    ):
        self.aggiungi_job_update()
        mock_post.return_value = risposta_http(404, {"code": "rest_user_invalid_id"})

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "FAILED", "abilitato")
        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        self.assertIn("risposta HTTP di errore", job.last_error)
        self.assertEqual(session.query(daemon.WordpressUser).count(), 1)
        self.assertEqual(session.query(daemon.WordpressPost).count(), 1)
        session.close()
        mock_mail.assert_not_called()

    def test_recovery_stale_riprova_e_poi_fallisce(self):
        self.aggiungi_job_update()
        adesso = datetime.now()
        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        job.stato = "SENDING"
        job.started_at = adesso - daemon.JOB_STALE_AFTER - timedelta(seconds=1)
        job.updated_at = adesso - daemon.JOB_STALE_AFTER - timedelta(seconds=1)
        job.attempts = 1
        session.commit()
        session.close()

        daemon.recupera_job_wordpress_stale(self.session_factory, adesso)
        session = self.session_factory()
        self.assertEqual(session.get(daemon.JobWordpress, 1).stato, "PENDING")
        job = session.get(daemon.JobWordpress, 1)
        job.stato = "SENDING"
        job.updated_at = adesso - daemon.JOB_STALE_AFTER - timedelta(seconds=1)
        job.attempts = daemon.JOB_MAX_ATTEMPTS
        session.commit()
        session.close()

        daemon.recupera_job_wordpress_stale(self.session_factory, adesso)
        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        self.assertEqual(job.stato, "FAILED")
        self.assertIn("massimo", job.last_error)
        session.close()


if __name__ == "__main__":
    unittest.main()
