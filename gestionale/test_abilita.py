import os
import unittest


os.environ["DB_TYPE"] = "sqlite"
os.environ["DB_NAME"] = ":memory:"
os.environ["SECRET_KEY"] = "test-secret-key"

from app import (  # noqa: E402
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

    def pannello(self, testo, id_pannello, id_pannello_successivo=None):
        inizio = testo.index(f'id="{id_pannello}"')
        if id_pannello_successivo is None:
            return testo[inizio:]
        fine = testo.index(f'id="{id_pannello_successivo}"', inizio)
        return testo[inizio:fine]

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
                iscrizione.stato = stato
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

    def test_dettaglio_mostra_risorse_wordpress_senza_password(self):
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
        self.assertNotIn("segreto-da-non-mostrare", testo)


if __name__ == "__main__":
    unittest.main()
