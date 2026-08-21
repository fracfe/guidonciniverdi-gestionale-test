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

    def aggiungi_mirror_wordpress(self, id_record, con_post=False):
        session = self.session_factory()
        utente = daemon.WordpressUser(
            data=datetime.now(),
            iscrizioni_id=id_record,
            wordpress_id=20,
            username="utente-remoto",
            password="password-locale",
            meta={"roles": ["author"]},
        )
        session.add(utente)
        session.flush()
        if con_post:
            session.add(
                daemon.WordpressPost(
                    data=datetime.now(),
                    iscrizioni_id=id_record,
                    wordpress_user_id=utente.id,
                    wordpress_id=30,
                    tipo="posts",
                    meta={"author": 20},
                )
            )
        session.commit()
        session.close()

    @patch.object(
        daemon, "lookup_provisioning_wordpress",
        return_value={"user": None, "post": None},
    )
    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_errore_http_non_blocca_il_job_successivo(
        self, mock_post, mock_get, _mock_mail, _mock_lookup
    ):
        self.aggiungi_iscrizione_e_job(1, "prima")
        self.aggiungi_iscrizione_e_job(2, "seconda")
        _mock_lookup.side_effect = [
            {"user": None, "post": None},
            {"user": None, "post": None},
            {"user": {"id": 20, "username": "seconda"}, "post": None},
        ]
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
        self.assertEqual(mock_post.call_args_list[1].kwargs["json"]["roles"], ["author"])
        self.assertEqual(
            mock_post.call_args_list[1].kwargs["json"]["meta"]["gv_iscrizione_id"],
            2,
        )
        chiamata_post = mock_post.call_args_list[2]
        self.assertIn("/posts", chiamata_post.args[0])
        payload_post = chiamata_post.kwargs["json"]
        self.assertEqual(payload_post["status"], "draft")
        self.assertEqual(payload_post["author"], 20)
        self.assertEqual(payload_post["categories"], [50])
        self.assertEqual(payload_post["specialita"], [40])
        self.assertEqual(payload_post["content"], "Template")
        self.assertEqual(payload_post["title"], "Squadriglia 2")
        self.assertEqual(payload_post["meta"]["gv_iscrizione_id"], 2)
        self.assertEqual(payload_post["meta"]["squadriglia"], "Squadriglia 2")
        self.assertEqual(payload_post["meta"]["specialita"], "Natura")
        session = self.session_factory()
        wordpress_post = session.query(daemon.WordpressPost).one()
        self.assertEqual(wordpress_post.wordpress_id, 30)
        self.assertEqual(wordpress_post.iscrizioni_id, 2)
        self.assertEqual(wordpress_post.meta, payload_post)
        session.close()
        for chiamata in mock_post.call_args_list + mock_get.call_args_list:
            self.assertEqual(chiamata.kwargs["timeout"], (5, 30))

    @patch.object(
        daemon, "lookup_provisioning_wordpress",
        return_value={"user": None, "post": None},
    )
    @patch.object(daemon.requests, "post", side_effect=daemon.requests.Timeout())
    def test_timeout_viene_isolato_e_non_espone_segreti(
        self, _mock_post, _mock_lookup
    ):
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
        daemon, "lookup_provisioning_wordpress",
        return_value={"user": None, "post": None},
    )
    @patch.object(
        daemon.requests,
        "post",
        side_effect=daemon.requests.ConnectionError("test-password"),
    )
    def test_errore_connessione_viene_isolato_e_sanitizzato(
        self, _mock_post, _mock_lookup
    ):
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

    @patch.object(
        daemon, "lookup_provisioning_wordpress",
        return_value={"user": None, "post": None},
    )
    @patch.object(daemon.requests, "post")
    def test_json_inatteso_viene_gestito(self, mock_post, _mock_lookup):
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

    @patch.object(
        daemon, "lookup_provisioning_wordpress",
        return_value={"user": None, "post": None},
    )
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_errore_creazione_post_imposta_failed_post(
        self, mock_post, mock_get, _mock_lookup
    ):
        self.aggiungi_iscrizione_e_job(1, "post-user")
        _mock_lookup.side_effect = [
            {"user": None, "post": None},
            {"user": {"id": 20, "username": "post-user"}, "post": None},
        ]
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

    @patch.object(
        daemon, "lookup_provisioning_wordpress",
        return_value={"user": None, "post": None},
    )
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_failed_post_retry_riusa_utente_e_conserva_lo_storico(
        self, mock_post, mock_get, _mock_lookup
    ):
        self.aggiungi_iscrizione_e_job(1, "post-user")
        remoto = {
            "user": {"id": 20, "username": "post-user"},
            "post": None,
        }
        _mock_lookup.side_effect = [
            {"user": None, "post": None},
            remoto,
            remoto,
            remoto,
        ]
        mock_post.side_effect = [
            risposta_http(201, {"id": 20}),
            risposta_http(500, {"code": "rest_cannot_create"}),
        ]
        mock_get.side_effect = [
            risposta_http(200, {"content": {"raw": "Template"}}),
            risposta_http(200, [{"name": "Natura", "id": 40}]),
            risposta_http(200, [{"name": "Pagina unica", "id": 50}]),
        ]
        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        session = self.session_factory()
        vecchio = session.get(daemon.JobWordpress, 1)
        session.get(daemon.IscrizioneEG, 1).stato = "in_abilitazione"
        session.add(daemon.JobWordpress(
            id=2, data=datetime.now(), stato="PENDING", tipo="crea_sq",
            iscrizione_id=1, updated_at=datetime.now(), attempts=0,
            dati=dict(vecchio.dati),
        ))
        session.commit()
        session.close()
        mock_post.reset_mock()
        mock_get.reset_mock()
        mock_post.side_effect = [risposta_http(201, {"id": 30})]
        mock_get.side_effect = [
            risposta_http(200, {"content": {"raw": "Template"}}),
            risposta_http(200, [{"name": "Natura", "id": 40}]),
            risposta_http(200, [{"name": "Pagina unica", "id": 50}]),
            risposta_http(200, {"link": "http://wordpress/post/30"}),
        ]

        with patch.object(daemon, "manda_mail", return_value=True) as mock_mail:
            daemon.processa_prossimo_job_wordpress(
                self.header, self.session_factory
            )

        session = self.session_factory()
        jobs = session.query(daemon.JobWordpress).order_by(
            daemon.JobWordpress.id
        ).all()
        self.assertEqual([job.stato for job in jobs], ["FAILED", "DONE"])
        self.assertEqual(session.query(daemon.WordpressUser).count(), 1)
        self.assertEqual(session.query(daemon.WordpressPost).count(), 1)
        self.assertEqual(session.get(daemon.IscrizioneEG, 1).stato, "abilitato")
        session.close()
        self.assertEqual(mock_post.call_count, 1)
        self.assertIn("/posts", mock_post.call_args.args[0])
        mock_mail.assert_called_once()

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    @patch.object(daemon, "lookup_provisioning_wordpress")
    def test_crash_dopo_utente_adotta_reset_password_e_crea_post(
        self, mock_lookup, mock_post, mock_get, _mock_mail
    ):
        self.aggiungi_iscrizione_e_job(1, "utente-remoto")
        remoto = {
            "user": {"id": 20, "username": "utente-remoto"},
            "post": None,
        }
        mock_lookup.side_effect = [remoto, remoto]
        mock_post.side_effect = [
            risposta_http(200, {"id": 20}),
            risposta_http(201, {"id": 30}),
        ]
        mock_get.side_effect = [
            risposta_http(200, {"content": {"raw": "Template"}}),
            risposta_http(200, [{"name": "Natura", "id": 40}]),
            risposta_http(200, [{"name": "Pagina unica", "id": 50}]),
            risposta_http(200, {"link": "http://wordpress/post/30"}),
        ]

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "DONE", "abilitato")
        session = self.session_factory()
        utente = session.query(daemon.WordpressUser).one()
        self.assertEqual(utente.wordpress_id, 20)
        self.assertNotEqual(utente.password, "password-locale")
        self.assertEqual(session.query(daemon.WordpressPost).count(), 1)
        session.close()
        self.assertIn("/users/20", mock_post.call_args_list[0].args[0])
        self.assertEqual(
            mock_post.call_args_list[1].kwargs["json"]["meta"]["gv_iscrizione_id"],
            1,
        )

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    @patch.object(daemon, "lookup_provisioning_wordpress")
    def test_crash_dopo_post_adotta_mirror_senza_nuove_creazioni(
        self, mock_lookup, mock_post, mock_get, _mock_mail
    ):
        self.aggiungi_iscrizione_e_job(1, "utente-remoto")
        self.aggiungi_mirror_wordpress(1)
        remoto = {
            "user": {"id": 20, "username": "utente-remoto"},
            "post": {
                "id": 30,
                "author": 20,
                "link": "http://wordpress/post/30",
            },
        }
        mock_lookup.side_effect = [remoto, remoto]
        mock_get.return_value = risposta_http(
            200, {"link": "http://wordpress/post/30"}
        )

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "DONE", "abilitato")
        self.assertEqual(mock_post.call_count, 0)
        session = self.session_factory()
        self.assertEqual(session.query(daemon.WordpressPost).one().wordpress_id, 30)
        session.close()

    @patch.object(daemon, "manda_mail", return_value=True)
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    @patch.object(daemon, "lookup_provisioning_wordpress")
    def test_mirror_completi_non_resettano_password_ne_duplicano_post(
        self, mock_lookup, mock_post, mock_get, _mock_mail
    ):
        self.aggiungi_iscrizione_e_job(1, "utente-remoto")
        self.aggiungi_mirror_wordpress(1, con_post=True)
        remoto = {
            "user": {"id": 20, "username": "utente-remoto"},
            "post": {
                "id": 30,
                "author": 20,
                "link": "http://wordpress/post/30",
            },
        }
        mock_lookup.side_effect = [remoto, remoto]
        mock_get.return_value = risposta_http(
            200, {"link": "http://wordpress/post/30"}
        )

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "DONE", "abilitato")
        mock_post.assert_not_called()
        session = self.session_factory()
        self.assertEqual(
            session.query(daemon.WordpressUser).one().password,
            "password-locale",
        )
        session.close()

    @patch.object(daemon.requests, "get")
    def test_lookup_assente_singolo_duplicato_e_json_inatteso(self, mock_get):
        mock_get.side_effect = [
            risposta_http(200, {"user": None, "post": None}),
            risposta_http(
                200,
                {
                    "user": {"id": 20, "username": "utente-remoto"},
                    "post": {"id": 30, "author": 20, "link": "http://wp/30"},
                },
            ),
            risposta_http(
                409,
                {
                    "code": "guidonciniverdi_provisioning_user_conflict",
                    "data": {"status": 409, "resource": "user"},
                },
            ),
            risposta_http(200, {"user": {"id": "20"}, "post": None}),
        ]

        self.assertEqual(
            daemon.lookup_provisioning_wordpress(1, self.header),
            {"user": None, "post": None},
        )
        self.assertEqual(
            daemon.lookup_provisioning_wordpress(1, self.header)["post"]["id"],
            30,
        )
        with self.assertRaises(daemon.WordpressRequestError) as conflitto:
            daemon.lookup_provisioning_wordpress(1, self.header)
        self.assertEqual(conflitto.exception.status_http, 409)
        self.assertEqual(conflitto.exception.risorsa, "user")
        with self.assertRaises(daemon.WordpressRequestError):
            daemon.lookup_provisioning_wordpress(1, self.header)
        for chiamata in mock_get.call_args_list:
            self.assertIn(
                "/wp-json/guidonciniverdi/v1/provisioning/1",
                chiamata.args[0],
            )

    @patch.object(daemon.requests, "post")
    @patch.object(
        daemon,
        "lookup_provisioning_wordpress",
        side_effect=daemon.WordpressRequestError(
            "riconciliazione provisioning",
            "/guidonciniverdi/v1/provisioning/1",
            "risposta HTTP di errore (codice WordPress: conflitto)",
            status_http=409,
            risorsa="user",
        ),
    )
    def test_conflitto_lookup_fallisce_chiuso_senza_creare(
        self, _mock_lookup, mock_post
    ):
        self.aggiungi_iscrizione_e_job(1, "utente-remoto")

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "FAILED", "failed_user")
        mock_post.assert_not_called()
        session = self.session_factory()
        self.assertEqual(session.query(daemon.WordpressUser).count(), 0)
        self.assertEqual(session.query(daemon.WordpressPost).count(), 0)
        session.close()

    @patch.object(daemon.requests, "post")
    @patch.object(
        daemon,
        "lookup_provisioning_wordpress",
        side_effect=daemon.WordpressRequestError(
            "riconciliazione provisioning",
            "/guidonciniverdi/v1/provisioning/1",
            "risposta HTTP di errore (codice WordPress: conflitto)",
            status_http=409,
            risorsa="post",
        ),
    )
    def test_conflitto_post_lookup_fallisce_chiuso_senza_creare(
        self, _mock_lookup, mock_post
    ):
        self.aggiungi_iscrizione_e_job(1, "utente-remoto")

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "FAILED", "failed_post")
        mock_post.assert_not_called()

    @patch.object(daemon.requests, "post")
    @patch.object(daemon, "lookup_provisioning_wordpress")
    def test_autore_post_incoerente_fallisce_chiuso(
        self, mock_lookup, mock_post
    ):
        self.aggiungi_iscrizione_e_job(1, "utente-remoto")
        mock_lookup.return_value = {
            "user": {"id": 20, "username": "utente-remoto"},
            "post": {"id": 30, "author": 99, "link": "http://wp/30"},
        }

        daemon.processa_prossimo_job_wordpress(self.header, self.session_factory)

        self.assert_stati(1, "FAILED", "failed_post")
        mock_post.assert_not_called()

    @patch.object(daemon.requests, "get", side_effect=daemon.requests.Timeout())
    def test_timeout_lookup_provisioning_viene_classificato(self, _mock_get):
        with self.assertRaises(daemon.WordpressRequestError) as errore:
            daemon.lookup_provisioning_wordpress(1, self.header)
        self.assertEqual(errore.exception.motivo, "timeout HTTP")
        self.assertEqual(
            errore.exception.endpoint,
            "/guidonciniverdi/v1/provisioning/1",
        )

    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_update_sq_aggiorna_solo_campi_previsti(
        self, mock_post, mock_get
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
        mail = session.query(daemon.CodaMail).one()
        self.assertEqual(mail.stato, "PENDING")
        self.assertIn("Guidoncini Verdi 2025", mail.titolo)
        corpo_mail = mail.testo
        session.close()
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

    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_update_sq_partial_success_puo_essere_ritentato(
        self, mock_post, mock_get
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
        self.assertEqual(session.query(daemon.CodaMail).count(), 0)
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
        session = self.session_factory()
        self.assertEqual(session.query(daemon.CodaMail).count(), 1)
        session.close()

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
        job = session.get(daemon.JobWordpress, 1)
        self.assertEqual(job.stato, "PENDING")
        self.assertEqual(job.attempts, 2)
        self.assertIsNone(job.started_at)
        self.assertEqual(job.updated_at, adesso)
        self.assertIn("riportato in coda", job.last_error)
        job.stato = "SENDING"
        started_at = adesso - daemon.JOB_STALE_AFTER - timedelta(seconds=2)
        job.started_at = started_at
        job.updated_at = adesso - daemon.JOB_STALE_AFTER - timedelta(seconds=1)
        job.attempts = daemon.JOB_MAX_ATTEMPTS
        session.commit()
        session.close()

        daemon.recupera_job_wordpress_stale(self.session_factory, adesso)
        session = self.session_factory()
        job = session.get(daemon.JobWordpress, 1)
        self.assertEqual(job.stato, "FAILED")
        self.assertEqual(job.attempts, daemon.JOB_MAX_ATTEMPTS + 1)
        self.assertEqual(job.started_at, started_at)
        self.assertEqual(job.updated_at, adesso)
        self.assertIn("massimo", job.last_error)
        session.close()

    @patch.object(daemon, "accoda_mail_sessione", side_effect=ValueError("coda non disponibile"))
    @patch.object(daemon.requests, "get")
    @patch.object(daemon.requests, "post")
    def test_update_non_diventa_done_se_accodamento_mail_fallisce(
        self, mock_post, mock_get, _mock_accoda
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

        self.assert_stati(1, "FAILED", "abilitato")
        session = self.session_factory()
        self.assertEqual(session.query(daemon.CodaMail).count(), 0)
        session.close()

    def test_timeout_smtp_lascia_la_mail_ritentabile(self):
        session = self.session_factory()
        session.add_all([
            daemon.Regione(id=1, regione="test", mail="regione@example.invalid"),
            daemon.CodaMail(
                data=datetime.now(), stato="PENDING", regione=1,
                indirizzi=["dest@example.invalid"], indirizzi_copia=[],
                titolo="Test", testo="Nessun segreto",
            ),
        ])
        session.commit()
        session.close()
        template = Mock()
        template.render.return_value = "<p>Test</p>"
        smtp_factory = Mock(side_effect=TimeoutError())

        daemon.processa_prossima_mail(
            template, self.session_factory, smtp_factory
        )

        session = self.session_factory()
        self.assertEqual(session.get(daemon.CodaMail, 1).stato, "PENDING")
        session.close()
        smtp_factory.assert_called_once_with(
            "mailpit", 1025, timeout=daemon.MAIL_SMTP_TIMEOUT
        )

    def test_recovery_segnala_iscrizione_in_abilitazione_orfana(self):
        self.aggiungi_iscrizione_e_job(1, "orfana")
        session = self.session_factory()
        session.get(daemon.JobWordpress, 1).stato = "FAILED"
        session.commit()
        session.close()

        with self.assertLogs(daemon.logger.name, level="ERROR") as log:
            daemon.recupera_job_wordpress_stale(
                self.session_factory, datetime.now()
            )

        self.assertIn(
            "Iscrizione in_abilitazione senza job attivo iscrizione=1",
            "\n".join(log.output),
        )


if __name__ == "__main__":
    unittest.main()
