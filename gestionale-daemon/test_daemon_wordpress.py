import os
import unittest
from datetime import datetime
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
        self.assert_stati(1, "FAILED", "failed_user")

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


if __name__ == "__main__":
    unittest.main()
