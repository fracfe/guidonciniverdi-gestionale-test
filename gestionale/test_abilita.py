import os
import unittest
from unittest.mock import patch


os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_NAME"] = ":memory:"
os.environ["SECRET_KEY"] = "test-secret-key"

import app as app_module  # noqa: E402
from app import (  # noqa: E402
    CodaMail,
    Gruppo,
    IscrizioneEG,
    JobWordpress,
    Regione,
    StatusPercorso,
    SysOption,
    User,
    WordpressPost,
    WordpressUser,
    Zona,
    app,
    db,
)
from datetime import datetime  # noqa: E402


class AbilitaIdempotenzaTest(unittest.TestCase):
    def nuova_iscrizione(
        self,
        id_iscrizione,
        stato="da_abilitare",
        regione=1,
        zona=1,
        gruppo=1,
        anno_percorso=1,
    ):
        return IscrizioneEG(
            id=id_iscrizione,
            data=datetime.now(),
            stato=stato,
            nome=f"Verdi {id_iscrizione}",
            mail=f"sq{id_iscrizione}@example.invalid",
            regione=regione,
            zona=zona,
            gruppo=gruppo,
            specialita="Natura",
            tipo="conquista",
            nome_capo_sq="Capo sq",
            nome_capo1="Capo uno",
            mail_capo1="capo1@example.invalid",
            cell_capo1="000",
            nome_capo2="Capo due",
            mail_capo2="capo2@example.invalid",
            cell_capo2="001",
            sesso="m",
            link="",
            anno_percorso=anno_percorso,
        )

    def aggiungi_provisioning_locale(
        self, id_iscrizione=1, con_post=True, con_link=True, con_done=True
    ):
        iscrizione = db.session.get(IscrizioneEG, id_iscrizione)
        utente = WordpressUser(
            data=datetime.now(),
            iscrizioni_id=id_iscrizione,
            wordpress_id=20 + id_iscrizione,
            username=f"wordpress-{id_iscrizione}",
            password="password-locale",
            meta={},
        )
        db.session.add(utente)
        db.session.flush()
        if con_post:
            db.session.add(WordpressPost(
                data=datetime.now(),
                iscrizioni_id=id_iscrizione,
                wordpress_user_id=utente.id,
                wordpress_id=30 + id_iscrizione,
                tipo="posts",
                meta={},
            ))
        if con_link:
            iscrizione.link = f"http://wordpress.test/post/{30 + id_iscrizione}"
        if con_done:
            db.session.add(JobWordpress(
                data=datetime.now(),
                stato="DONE",
                tipo="crea_sq",
                iscrizione_id=id_iscrizione,
                updated_at=datetime.now(),
                dati={"tipo": "crea_sq", "iscrizione": id_iscrizione},
            ))
        db.session.commit()
        return utente

    def pannello(self, testo, id_pannello, id_pannello_successivo=None):
        inizio = testo.index(f'id="{id_pannello}"')
        if id_pannello_successivo is None:
            return testo[inizio:]
        fine = testo.index(f'id="{id_pannello_successivo}"', inizio)
        return testo[inizio:fine]

    def dati_modifica(self, **modifiche):
        dati = {
            "nome_squadriglia": "Verdi aggiornate",
            "tipo_sq": "m",
            "zona": "1",
            "gruppo": "1",
            "specialita": "Natura",
            "conquista_conferma": "conquista",
            "nome_capo_squadriglia": "Capo sq",
            "mail_squadriglia": "sq@example.invalid",
            "nome_capo_rep1": "Capo uno",
            "mail_rep1": "capo1@example.invalid",
            "numero_rep1": "000",
            "nome_capo_rep2": "Capo due",
            "mail_rep2": "capo2@example.invalid",
            "numero_rep2": "001",
        }
        dati.update(modifiche)
        return dati

    def setUp(self):
        app.config.update(TESTING=True)
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

        regione = Regione(id=1, regione="test", mail="test@example.invalid")
        zona = Zona(id=1, zona="zona test", regione=1)
        gruppo = Gruppo(id=1, gruppo="test 1", zona=1, regione=1)
        stato = StatusPercorso(
            id=1,
            anno="2026",
            iscrizioni=True,
            abilitazioni=True,
            regione=1,
        )
        utente = User(
            id=1,
            username="responsabile",
            password="unused",
            mail="test@example.invalid",
            regione=1,
            livello="iabr",
        )
        iscrizione = self.nuova_iscrizione(1)
        db.session.add_all(
            [
                regione,
                zona,
                gruppo,
                stato,
                utente,
                iscrizione,
                SysOption(key="AnnoCorrente", value="2026"),
            ]
        )
        db.session.commit()

        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = "1"
            session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_due_post_consecutivi_accodano_un_solo_job(self):
        prima = self.client.post("/abilita/1", data={"username": "verdi_test1"})
        seconda = self.client.post("/abilita/1", data={"username": "verdi_test1"})

        self.assertEqual(prima.status_code, 302)
        self.assertEqual(seconda.status_code, 302)
        self.assertEqual(JobWordpress.query.count(), 1)
        self.assertEqual(JobWordpress.query.one().stato, "PENDING")
        self.assertEqual(IscrizioneEG.query.get(1).stato, "in_abilitazione")

    def test_job_sending_esistente_non_viene_duplicato(self):
        db.session.add(
            JobWordpress(
                data=datetime.now(),
                stato="SENDING",
                dati={
                    "iscrizione": 1,
                    "tipo": "crea_sq",
                    "username": "verdi_test1",
                    "meta": {},
                },
            )
        )
        db.session.commit()

        risposta = self.client.post(
            "/abilita/1", data={"username": "verdi_test1"}
        )

        self.assertEqual(risposta.status_code, 302)
        self.assertEqual(JobWordpress.query.count(), 1)
        self.assertEqual(JobWordpress.query.one().stato, "SENDING")
        self.assertEqual(IscrizioneEG.query.get(1).stato, "in_abilitazione")

    def test_get_abilita_passa_gruppo_e_zona_anche_con_username_occupato(self):
        db.session.add(self.nuova_iscrizione(2))
        db.session.flush()
        db.session.add(WordpressUser(
            data=datetime.now(),
            iscrizioni_id=2,
            wordpress_id=22,
            username="verdi_1_test_1",
            password="password-locale",
            meta={},
        ))
        db.session.commit()

        risposta = self.client.get("/abilita/1")
        testo = risposta.get_data(as_text=True)

        self.assertEqual(risposta.status_code, 200)
        self.assertIn("Gruppo Test 1", testo)
        self.assertIn("Zona Test", testo)
        self.assertIn("Username non valido", testo)

    def test_get_abilita_con_dati_territoriali_mancanti_non_genera_500(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.gruppo = 999
        db.session.commit()

        risposta = self.client.get("/abilita/1")

        self.assertEqual(risposta.status_code, 302)
        self.assertIn("/iscrizioni", risposta.location)

    def test_rendering_stati_e_azioni_provisioning(self):
        casi = [
            (
                "in_abilitazione",
                "Abilitazione in corso",
                "il sistema sta lavorando in background",
                False,
            ),
            (
                "failed_user",
                "Errore creazione utente WordPress",
                "Riprova abilitazione",
                True,
            ),
            (
                "failed_post",
                "Errore creazione pagina WordPress",
                "Il retry automatico non è disponibile",
                False,
            ),
        ]
        iscrizione = db.session.get(IscrizioneEG, 1)

        for stato, etichetta, spiegazione, abilita_visibile in casi:
            with self.subTest(stato=stato):
                JobWordpress.query.delete()
                iscrizione.stato = stato
                if stato == "in_abilitazione":
                    db.session.add(JobWordpress(
                        data=datetime.now(), stato="PENDING", tipo="crea_sq",
                        iscrizione_id=1, updated_at=datetime.now(),
                        dati={"tipo": "crea_sq", "iscrizione": 1},
                    ))
                db.session.commit()
                risposta = self.client.get("/iscrizioni")
                testo = risposta.get_data(as_text=True)

                self.assertEqual(risposta.status_code, 200)
                self.assertIn(etichetta, testo)
                self.assertIn(spiegazione, testo)
                if abilita_visibile:
                    self.assertIn("/abilita/1", testo)
                    self.assertEqual(self.client.get("/abilita/1").status_code, 200)
                else:
                    self.assertNotIn("/abilita/1", testo)
                    self.assertEqual(self.client.get("/abilita/1").status_code, 302)

    def test_dashboard_distingue_tutti_gli_stati(self):
        db.session.add_all(
            [
                self.nuova_iscrizione(2, "in_abilitazione"),
                self.nuova_iscrizione(3, "abilitato"),
                self.nuova_iscrizione(4, "failed_user"),
                self.nuova_iscrizione(5, "failed_post"),
                self.nuova_iscrizione(6, "eliminato"),
            ]
        )
        db.session.commit()

        risposta = self.client.get("/dashboard")
        testo = risposta.get_data(as_text=True)

        self.assertEqual(risposta.status_code, 200)
        self.assertIn("'Da Abilitare'", testo)
        self.assertIn("'In Abilitazione'", testo)
        self.assertIn("'Errori'", testo)
        self.assertIn("data: [1, 1, 1, 2, 1]", testo)

    def test_tab_iscrizioni_separano_stati_e_mostrano_conteggi(self):
        db.session.add_all(
            [
                self.nuova_iscrizione(2, "in_abilitazione"),
                self.nuova_iscrizione(3, "failed_user"),
                self.nuova_iscrizione(4, "failed_post"),
                self.nuova_iscrizione(5, "abilitato"),
                self.nuova_iscrizione(6, "eliminato"),
            ]
        )
        db.session.commit()

        risposta = self.client.get("/iscrizioni")
        testo = risposta.get_data(as_text=True)

        self.assertEqual(risposta.status_code, 200)
        self.assertIn("Da gestire (1)", testo)
        self.assertIn("In coda (1)", testo)
        self.assertIn("Errori (2)", testo)
        self.assertIn("Abilitate (1)", testo)
        self.assertEqual(testo.count("function filtra_tab("), 1)

        da_gestire = self.pannello(
            testo, "abilitare-tab-pane", "coda-tab-pane"
        )
        in_coda = self.pannello(testo, "coda-tab-pane", "errori-tab-pane")
        errori = self.pannello(testo, "errori-tab-pane", "abilitati-tab-pane")
        abilitate = self.pannello(testo, "abilitati-tab-pane", "tutti-tab-pane")
        tutte = self.pannello(testo, "tutti-tab-pane")

        self.assertIn('data-iscrizione-id="1"', da_gestire)
        self.assertNotIn('data-iscrizione-id="2"', da_gestire)
        self.assertNotIn('data-iscrizione-id="3"', da_gestire)
        self.assertNotIn('data-iscrizione-id="4"', da_gestire)
        self.assertIn('data-iscrizione-id="2"', in_coda)
        self.assertIn('id="cerca_gruppo_coda"', in_coda)
        self.assertIn('id="cerca_nome_coda"', in_coda)
        self.assertIn("'iscrizioni_coda', 1", in_coda)
        self.assertIn("'iscrizioni_coda', 2", in_coda)
        self.assertNotIn('data-iscrizione-id="1"', in_coda)
        self.assertNotIn('data-iscrizione-id="3"', in_coda)
        self.assertNotIn('data-iscrizione-id="4"', in_coda)
        self.assertIn('data-iscrizione-id="3"', errori)
        self.assertIn('data-iscrizione-id="4"', errori)
        self.assertIn('id="cerca_gruppo_errori"', errori)
        self.assertIn('id="cerca_nome_errori"', errori)
        self.assertIn("'iscrizioni_errori', 1", errori)
        self.assertIn("'iscrizioni_errori', 2", errori)
        self.assertNotIn('data-iscrizione-id="1"', errori)
        self.assertNotIn('data-iscrizione-id="2"', errori)
        self.assertIn("Errore creazione utente WordPress", errori)
        self.assertIn("Errore creazione pagina WordPress", errori)
        self.assertIn('data-iscrizione-id="5"', abilitate)
        self.assertIn('<th scope="col">Stato</th>', abilitate)
        self.assertIn('<span class="badge bg-success">Abilitata</span>', abilitate)
        self.assertNotIn('data-iscrizione-id="1"', abilitate)
        self.assertNotIn('data-iscrizione-id="2"', abilitate)
        self.assertNotIn('data-iscrizione-id="3"', abilitate)
        self.assertNotIn('data-iscrizione-id="4"', abilitate)
        for id_iscrizione in range(1, 7):
            self.assertIn(f'data-iscrizione-id="{id_iscrizione}"', tutte)

    def test_tab_iscrizioni_rispettano_filtri_regione_e_zona(self):
        db.session.add_all(
            [
                Zona(id=2, zona="altra zona", regione=1),
                Gruppo(id=2, gruppo="test 2", zona=2, regione=1),
                Regione(id=2, regione="altra regione", mail="r2@example.invalid"),
                Zona(id=3, zona="zona esterna", regione=2),
                Gruppo(id=3, gruppo="test 3", zona=3, regione=2),
                StatusPercorso(
                    id=2,
                    anno="2026",
                    iscrizioni=True,
                    abilitazioni=True,
                    regione=2,
                ),
                self.nuova_iscrizione(2, zona=2, gruppo=2),
                self.nuova_iscrizione(
                    3, regione=2, zona=3, gruppo=3, anno_percorso=2
                ),
                self.nuova_iscrizione(
                    4, "in_abilitazione", zona=2, gruppo=2
                ),
                self.nuova_iscrizione(
                    5,
                    "failed_user",
                    regione=2,
                    zona=3,
                    gruppo=3,
                    anno_percorso=2,
                ),
            ]
        )
        db.session.commit()

        risposta_regione = self.client.get("/iscrizioni")
        testo_regione = risposta_regione.get_data(as_text=True)
        da_gestire_regione = self.pannello(
            testo_regione, "abilitare-tab-pane", "coda-tab-pane"
        )

        self.assertIn("Da gestire (2)", testo_regione)
        self.assertIn("In coda (1)", testo_regione)
        self.assertIn("Errori (0)", testo_regione)
        self.assertIn('data-iscrizione-id="1"', da_gestire_regione)
        self.assertIn('data-iscrizione-id="2"', da_gestire_regione)
        self.assertNotIn('data-iscrizione-id="3"', testo_regione)
        self.assertIn('data-iscrizione-id="4"', testo_regione)
        self.assertNotIn('data-iscrizione-id="5"', testo_regione)

        utente = db.session.get(User, 1)
        utente.livello = "iabz"
        utente.zona = 1
        db.session.commit()

        risposta_zona = self.client.get("/iscrizioni")
        testo_zona = risposta_zona.get_data(as_text=True)
        da_gestire_zona = self.pannello(
            testo_zona, "abilitare-tab-pane", "coda-tab-pane"
        )

        self.assertIn("Da gestire (1)", testo_zona)
        self.assertIn("In coda (0)", testo_zona)
        self.assertIn("Errori (0)", testo_zona)
        self.assertIn('data-iscrizione-id="1"', da_gestire_zona)
        self.assertNotIn('data-iscrizione-id="2"', testo_zona)
        self.assertNotIn('data-iscrizione-id="3"', testo_zona)
        self.assertNotIn('data-iscrizione-id="4"', testo_zona)
        self.assertNotIn('data-iscrizione-id="5"', testo_zona)

    def test_edit_usa_fk_numeriche_e_preseleziona_valori(self):
        risposta = self.client.get("/edit/1")
        testo = risposta.get_data(as_text=True)

        self.assertEqual(risposta.status_code, 200)
        self.assertIn('option value="1" selected>zona test</option>', testo)
        self.assertIn('option value="m" selected>Maschile</option>', testo)
        self.assertIn('var tmp_gruppo = "1"', testo)
        self.assertIn('option value="Natura" selected>Natura</option>', testo)
        self.assertIn('value="conquista" type="radio"', testo)
        self.assertIn("Dati squadriglia", testo)
        self.assertIn("Contatti", testo)
        self.assertIn("Salva modifiche", testo)
        self.assertIn("Annulla", testo)
        self.assertNotIn("Reimposta password", testo)
        self.assertNotIn('option value="ZONA TEST"', testo)

    def test_stati_previsti_sono_modificabili_senza_cambiare_stato(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        for stato in ["da_abilitare", "failed_user", "failed_post", "abilitato"]:
            with self.subTest(stato=stato):
                iscrizione.stato = stato
                db.session.commit()
                self.assertEqual(self.client.get("/edit/1").status_code, 200)
                self.assertEqual(db.session.get(IscrizioneEG, 1).stato, stato)

    def test_permessi_edit_iabr_iabz_admin(self):
        db.session.add_all([
            Regione(id=2, regione="esterna", mail="r2@example.invalid"),
            Zona(id=2, zona="zona due", regione=1),
            Gruppo(id=2, gruppo="test 2", zona=2, regione=1),
            Zona(id=3, zona="zona esterna", regione=2),
            Gruppo(id=3, gruppo="test 3", zona=3, regione=2),
            StatusPercorso(id=2, anno="2026", iscrizioni=True, abilitazioni=True, regione=2),
            self.nuova_iscrizione(2, zona=2, gruppo=2),
            self.nuova_iscrizione(3, regione=2, zona=3, gruppo=3, anno_percorso=2),
        ])
        db.session.commit()

        self.assertEqual(self.client.get("/edit/1").status_code, 200)
        self.assertEqual(self.client.get("/edit/3").status_code, 302)
        self.assertEqual(self.client.get("/dettagli/3").status_code, 302)

        utente = db.session.get(User, 1)
        utente.livello = "iabz"
        utente.zona = 1
        db.session.commit()
        self.assertEqual(self.client.get("/edit/1").status_code, 200)
        self.assertEqual(self.client.get("/edit/2").status_code, 302)

        utente.livello = "admin"
        db.session.commit()
        self.assertEqual(self.client.get("/edit/3").status_code, 200)

    @patch.object(app_module, "manda_mail", return_value=True)
    def test_iabz_trasferisce_zona_e_perde_competenza(self, _mock_mail):
        db.session.add_all([
            Zona(id=2, zona="zona due", regione=1),
            Gruppo(id=2, gruppo="test 2", zona=2, regione=1),
        ])
        utente = db.session.get(User, 1)
        utente.livello = "iabz"
        utente.zona = 1
        db.session.commit()

        senza_conferma = self.client.post(
            "/edit/1", data=self.dati_modifica(zona="2", gruppo="2")
        )
        self.assertEqual(senza_conferma.status_code, 302)
        self.assertEqual(db.session.get(IscrizioneEG, 1).zona, 1)

        risposta = self.client.post(
            "/edit/1",
            data=self.dati_modifica(
                zona="2", gruppo="2", conferma_trasferimento="1"
            ),
        )
        self.assertEqual(risposta.status_code, 302)
        iscrizione = db.session.get(IscrizioneEG, 1)
        self.assertEqual((iscrizione.zona, iscrizione.gruppo), (2, 2))
        self.assertEqual(iscrizione.stato, "da_abilitare")
        self.assertEqual(self.client.get("/edit/1").status_code, 302)

    @patch.object(app_module, "manda_mail", return_value=True)
    def test_edit_respinge_gruppo_fuori_zona_e_zona_fuori_regione(
        self, _mock_mail
    ):
        db.session.add_all([
            Regione(id=2, regione="esterna", mail="r2@example.invalid"),
            Zona(id=2, zona="zona due", regione=1),
            Gruppo(id=2, gruppo="test 2", zona=2, regione=1),
            Zona(id=3, zona="zona esterna", regione=2),
            Gruppo(id=3, gruppo="test 3", zona=3, regione=2),
        ])
        db.session.commit()

        self.client.post("/edit/1", data=self.dati_modifica(gruppo="2"))
        iscrizione = db.session.get(IscrizioneEG, 1)
        self.assertEqual((iscrizione.zona, iscrizione.gruppo), (1, 1))
        self.assertEqual(iscrizione.stato, "da_abilitare")

        self.client.post(
            "/edit/1",
            data=self.dati_modifica(
                zona="3", gruppo="3", conferma_trasferimento="1"
            ),
        )
        iscrizione = db.session.get(IscrizioneEG, 1)
        self.assertEqual((iscrizione.zona, iscrizione.gruppo), (1, 1))
        self.assertEqual(iscrizione.stato, "da_abilitare")
        self.assertEqual(JobWordpress.query.count(), 0)
        _mock_mail.assert_not_called()

    @patch.object(app_module, "manda_mail", return_value=True)
    def test_edit_abilitato_accoda_update_solo_per_campi_wordpress(self, _mock_mail):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "abilitato"
        db.session.add(WordpressUser(
            data=datetime.now(), iscrizioni_id=1, wordpress_id=20,
            username="stabile", password="precedente", meta={},
        ))
        db.session.commit()

        locale = self.dati_modifica(
            nome_squadriglia="Verdi 1", nome_capo_squadriglia="Nuovo capo"
        )
        risposta_locale = self.client.post(
            "/edit/1", data=locale, follow_redirects=True
        )
        self.assertEqual(JobWordpress.query.count(), 0)
        testo_locale = risposta_locale.get_data(as_text=True)
        self.assertIn("Dettaglio iscrizione 1", testo_locale)
        self.assertIn("Modifiche salvate correttamente.", testo_locale)
        corpo_locale = _mock_mail.call_args.args[3]
        self.assertIn("stabile", corpo_locale)
        self.assertIn("precedente", corpo_locale)

        rilevante = self.dati_modifica(nome_squadriglia="Nome nuovo")
        risposta_wordpress = self.client.post(
            "/edit/1", data=rilevante, follow_redirects=True
        )
        self.assertEqual(JobWordpress.query.count(), 1)
        job = JobWordpress.query.one()
        self.assertEqual((job.tipo, job.iscrizione_id, job.stato), ("update_sq", 1, "PENDING"))
        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "abilitato")
        self.assertEqual(_mock_mail.call_count, 1)
        testo_wordpress = risposta_wordpress.get_data(as_text=True)
        self.assertIn("Modifiche salvate. Aggiornamento WordPress in corso.", testo_wordpress)
        self.assertIn("Aggiornamento in corso", testo_wordpress)
        self.assertIn("Abilitata", testo_wordpress)

    @patch.object(app_module, "manda_mail", return_value=True)
    def test_modifica_solo_telefono_invia_un_riepilogo_completo(self, mock_mail):
        dati = self.dati_modifica(
            nome_squadriglia="Verdi 1",
            mail_squadriglia="sq1@example.invalid",
            numero_rep1="999",
        )

        self.client.post("/edit/1", data=dati)

        self.assertEqual(JobWordpress.query.count(), 0)
        mock_mail.assert_called_once()
        corpo = mock_mail.call_args.args[3]
        for valore in [
            "Verdi 1",
            "Maschile",
            "test",
            "zona test",
            "test 1",
            "Natura",
            "Conquista",
            "2026",
            "Capo sq",
            "sq1@example.invalid",
            "Capo uno",
            "999",
        ]:
            self.assertIn(valore, corpo)
        self.assertNotIn("Credenziali Diario WordPress", corpo)
        self.assertNotIn("None", corpo)
        self.assertIn("Capo reparto 2", corpo)
        self.assertEqual(
            mock_mail.call_args.args[1],
            ["capo1@example.invalid", "capo2@example.invalid"],
        )

    @patch.object(app_module, "manda_mail", return_value=True)
    def test_failed_post_edit_non_ritenta_ma_azione_esplicita_crea_nuovo_job(self, _mock_mail):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "failed_post"
        db.session.add(WordpressUser(
            data=datetime.now(), iscrizioni_id=1, wordpress_id=20,
            username="stabile", password="precedente", meta={},
        ))
        db.session.commit()

        self.client.post("/edit/1", data=self.dati_modifica())
        self.assertEqual(JobWordpress.query.count(), 0)
        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "failed_post")

        self.client.post("/retry_post/1")
        self.assertEqual(JobWordpress.query.count(), 1)
        job = JobWordpress.query.one()
        self.assertEqual((job.tipo, job.stato), ("crea_sq", "PENDING"))
        self.assertEqual(job.dati["username"], "stabile")
        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "in_abilitazione")

    def test_stati_in_abilitazione_ed_eliminato_bloccano_edit(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        for stato in ["in_abilitazione", "eliminato"]:
            with self.subTest(stato=stato):
                iscrizione.stato = stato
                db.session.commit()
                self.assertEqual(self.client.get("/edit/1").status_code, 302)

    def test_job_wordpress_attivo_blocca_edit(self):
        db.session.add(JobWordpress(
            data=datetime.now(), stato="PENDING", tipo="update_sq",
            iscrizione_id=1, updated_at=datetime.now(),
            dati={"tipo": "update_sq", "iscrizione": 1},
        ))
        db.session.commit()

        risposta = self.client.get("/edit/1", follow_redirects=True)

        self.assertEqual(risposta.status_code, 200)
        self.assertIn("operazione WordPress", risposta.get_data(as_text=True))

    def test_errore_sincronizzazione_e_retry_creano_un_nuovo_job(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "abilitato"
        wordpress_user = WordpressUser(
            data=datetime.now(), iscrizioni_id=1, wordpress_id=20,
            username="stabile", password="precedente", meta={},
        )
        db.session.add(wordpress_user)
        db.session.flush()
        db.session.add_all([
            WordpressPost(
                data=datetime.now(), iscrizioni_id=1,
                wordpress_user_id=wordpress_user.id, wordpress_id=30,
                tipo="posts", meta={},
            ),
            JobWordpress(
                data=datetime.now(), stato="FAILED", tipo="update_sq",
                iscrizione_id=1, updated_at=datetime.now(),
                last_error="timeout HTTP",
                dati={"tipo": "update_sq", "iscrizione": 1},
            ),
        ])
        db.session.commit()

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        self.assertIn("Errore di sincronizzazione", dettaglio)
        self.assertIn("timeout HTTP", dettaglio)
        self.assertIn("Riprova sincronizzazione", dettaglio)

        self.client.post("/retry_sync/1")
        jobs = JobWordpress.query.order_by(JobWordpress.id).all()
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].stato, "FAILED")
        self.assertEqual((jobs[1].tipo, jobs[1].stato), ("update_sq", "PENDING"))
        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "abilitato")

    def test_abilitazione_interrotta_e_ripristino_esplicito(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "in_abilitazione"
        db.session.commit()

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        lista = self.client.get("/iscrizioni").get_data(as_text=True)

        self.assertIn("Abilitazione interrotta", dettaglio)
        self.assertIn("Abilitazione interrotta", lista)
        self.assertIn('Ripristina a "Da abilitare"', dettaglio)
        self.assertIn("risorse remote non registrate localmente", dettaglio)
        self.assertNotIn("window.location.reload", dettaglio)

        risposta = self.client.post(
            "/ripristina_abilitazione_interrotta/1", follow_redirects=True
        )

        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "da_abilitare")
        self.assertEqual(JobWordpress.query.count(), 0)
        self.assertEqual(WordpressUser.query.count(), 0)
        self.assertEqual(WordpressPost.query.count(), 0)
        self.assertIn(
            "ripristinata a Da abilitare", risposta.get_data(as_text=True)
        )

    @patch.object(app_module.requests, "post")
    def test_orfano_completo_viene_ripristinato_come_abilitato(
        self, mock_wordpress_post
    ):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "in_abilitazione"
        self.aggiungi_provisioning_locale()
        id_utente = WordpressUser.query.one().id
        id_post = WordpressPost.query.one().id
        link = iscrizione.link

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        self.assertIn("Provisioning completato da ripristinare", dettaglio)
        self.assertIn("Ripristina come Abilitata", dettaglio)

        risposta = self.client.post(
            "/ripristina_abilitazione_interrotta/1", follow_redirects=True
        )

        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "abilitato")
        self.assertEqual(db.session.get(IscrizioneEG, 1).link, link)
        self.assertEqual(WordpressUser.query.one().id, id_utente)
        self.assertEqual(WordpressPost.query.one().id, id_post)
        self.assertEqual(JobWordpress.query.count(), 1)
        self.assertEqual(JobWordpress.query.one().stato, "DONE")
        self.assertIn(
            "ripristinata come Abilitata", risposta.get_data(as_text=True)
        )
        mock_wordpress_post.assert_not_called()

    @patch.object(app_module.requests, "post")
    def test_orfano_parziale_fallisce_chiuso_senza_modifiche(
        self, mock_wordpress_post
    ):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "in_abilitazione"
        self.aggiungi_provisioning_locale(
            con_post=False, con_link=False, con_done=False
        )
        id_utente = WordpressUser.query.one().id

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        self.assertIn(
            "Provisioning interrotto - stato da riconciliare", dettaglio
        )
        self.assertNotIn("Ripristina come Abilitata", dettaglio)
        self.assertNotIn('Ripristina a "Da abilitare"', dettaglio)

        self.client.post("/ripristina_abilitazione_interrotta/1")

        self.assertEqual(
            db.session.get(IscrizioneEG, 1).stato, "in_abilitazione"
        )
        self.assertEqual(WordpressUser.query.one().id, id_utente)
        self.assertEqual(WordpressPost.query.count(), 0)
        self.assertEqual(JobWordpress.query.count(), 0)
        mock_wordpress_post.assert_not_called()

    def test_storico_done_senza_mirror_o_link_rimane_ambiguo(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "in_abilitazione"
        db.session.add(JobWordpress(
            data=datetime.now(),
            stato="DONE",
            tipo="crea_sq",
            iscrizione_id=1,
            updated_at=datetime.now(),
            dati={"tipo": "crea_sq", "iscrizione": 1},
        ))
        db.session.commit()

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        self.assertIn("stato da riconciliare", dettaglio)

        self.client.post("/ripristina_abilitazione_interrotta/1")

        self.assertEqual(
            db.session.get(IscrizioneEG, 1).stato, "in_abilitazione"
        )
        self.assertEqual(JobWordpress.query.count(), 1)

    def test_abilita_rifiuta_iscrizione_gia_provisionata(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "da_abilitare"
        self.aggiungi_provisioning_locale()

        risposta = self.client.post(
            "/abilita/1",
            data={"username": "nuovo-username"},
            follow_redirects=True,
        )

        self.assertEqual(risposta.status_code, 200)
        self.assertIn("gia completato", risposta.get_data(as_text=True))
        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "da_abilitare")
        self.assertEqual(JobWordpress.query.count(), 1)
        self.assertEqual(JobWordpress.query.one().stato, "DONE")
        self.assertEqual(WordpressUser.query.count(), 1)
        self.assertEqual(WordpressPost.query.count(), 1)

    def test_job_attivo_abilita_auto_refresh_e_blocca_ripristino(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "in_abilitazione"
        db.session.add(JobWordpress(
            data=datetime.now(), stato="PENDING", tipo="crea_sq",
            iscrizione_id=1, updated_at=datetime.now(),
            dati={"tipo": "crea_sq", "iscrizione": 1, "username": "verdi"},
        ))
        db.session.commit()

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        self.assertIn("Aggiornamento in corso", dettaglio)
        self.assertIn("window.setTimeout", dettaglio)
        self.assertIn("5000", dettaglio)
        self.assertNotIn('Ripristina a "Da abilitare"', dettaglio)

        self.client.post("/ripristina_abilitazione_interrotta/1")
        self.assertEqual(db.session.get(IscrizioneEG, 1).stato, "in_abilitazione")
        self.assertEqual(JobWordpress.query.count(), 1)

    @patch.object(app_module, "richiesta_wordpress_reset_password")
    def test_reset_password_aggiorna_locale_solo_dopo_successo(self, mock_reset):
        db.session.add(WordpressUser(
            data=datetime.now(), iscrizioni_id=1, wordpress_id=20,
            username="stabile", password="precedente", meta={},
        ))
        db.session.commit()

        risposta = self.client.get("/dettagli/1")
        self.assertIn("precedente", risposta.get_data(as_text=True))
        successo = self.client.post(
            "/reset_password_wordpress/1",
            data={"nuova_password": "nuova", "conferma_password": "nuova"},
            follow_redirects=True,
        )
        self.assertEqual(WordpressUser.query.one().password, "nuova")
        mock_reset.assert_called_once_with(20, "nuova")
        self.assertEqual(CodaMail.query.count(), 1)
        mail_reset = CodaMail.query.one()
        self.assertIn("Credenziali aggiornate", mail_reset.titolo)
        self.assertIn("nuova", mail_reset.testo)
        self.assertIn("Verdi 1", mail_reset.testo)
        self.assertIn("zona test", mail_reset.testo)
        self.assertIn("test 1", mail_reset.testo)
        testo_successo = successo.get_data(as_text=True)
        self.assertIn("Dettaglio iscrizione 1", testo_successo)
        self.assertIn("Password WordPress aggiornata correttamente.", testo_successo)

        mock_reset.side_effect = RuntimeError("errore")
        fallimento = self.client.post(
            "/reset_password_wordpress/1",
            data={"nuova_password": "altra", "conferma_password": "altra"},
            follow_redirects=True,
        )
        self.assertEqual(WordpressUser.query.one().password, "nuova")
        self.assertEqual(CodaMail.query.count(), 1)
        testo_fallimento = fallimento.get_data(as_text=True)
        self.assertIn("Reimposta password WordPress", testo_fallimento)
        self.assertIn("password precedente è rimasta invariata", testo_fallimento)

    def test_reset_password_ha_pagina_dedicata_e_validazione_live(self):
        db.session.add(WordpressUser(
            data=datetime.now(), iscrizioni_id=1, wordpress_id=20,
            username="stabile", password="precedente", meta={},
        ))
        db.session.commit()

        dettaglio = self.client.get("/dettagli/1").get_data(as_text=True)
        self.assertIn("Stato iscrizione", dettaglio)
        self.assertIn("WordPress", dettaglio)
        self.assertIn("Credenziali WordPress", dettaglio)
        self.assertIn("Dati iscrizione", dettaglio)
        self.assertIn("Modifica iscrizione", dettaglio)
        self.assertIn("Reimposta password", dettaglio)
        self.assertIn('href="/reset_password_wordpress/1"', dettaglio)

        risposta = self.client.get("/reset_password_wordpress/1")
        testo = risposta.get_data(as_text=True)
        self.assertEqual(risposta.status_code, 200)
        self.assertIn("Verdi 1", testo)
        self.assertIn("test 1", testo)
        self.assertIn("stabile", testo)
        self.assertEqual(testo.count('name="nuova_password"'), 1)
        self.assertEqual(testo.count('name="conferma_password"'), 1)
        self.assertIn("Ripeti password", testo)
        self.assertIn("Le password non coincidono", testo)
        self.assertIn("Le password coincidono", testo)
        self.assertIn("reset-password-submit\" disabled", testo)
        self.assertEqual(testo.count("function aggiornaValidazionePassword"), 1)
        self.assertIn("Annulla", testo)

        non_coincidenti = self.client.post(
            "/reset_password_wordpress/1",
            data={"nuova_password": "una", "conferma_password": "diversa"},
            follow_redirects=True,
        )
        self.assertIn(
            "Le password non coincidono.",
            non_coincidenti.get_data(as_text=True),
        )
        self.assertEqual(WordpressUser.query.one().password, "precedente")
        self.assertEqual(CodaMail.query.count(), 0)

    def test_dettaglio_mostra_risorse_e_password_agli_autorizzati(self):
        iscrizione = db.session.get(IscrizioneEG, 1)
        iscrizione.stato = "failed_post"
        wordpress_user = WordpressUser(
            data=datetime.now(),
            iscrizioni_id=1,
            wordpress_id=20,
            username="verdi_test1",
            password="segreto-da-non-mostrare",
            meta={},
        )
        db.session.add(wordpress_user)
        db.session.flush()
        db.session.add(
            WordpressPost(
                data=datetime.now(),
                iscrizioni_id=1,
                wordpress_user_id=wordpress_user.id,
                wordpress_id=30,
                tipo="posts",
                meta={},
            )
        )
        db.session.commit()

        risposta = self.client.get("/dettagli/1")
        testo = risposta.get_data(as_text=True)

        self.assertEqual(risposta.status_code, 200)
        self.assertIn("Utente WordPress", testo)
        self.assertIn("Pagina WordPress", testo)
        self.assertIn("verdi_test1", testo)
        self.assertIn("segreto-da-non-mostrare", testo)


if __name__ == "__main__":
    unittest.main()
