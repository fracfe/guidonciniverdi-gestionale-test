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
    Zona,
    app,
    db,
)
from datetime import datetime  # noqa: E402


class AbilitaIdempotenzaTest(unittest.TestCase):
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
        iscrizione = IscrizioneEG(
            id=1,
            data=datetime.now(),
            stato="da_abilitare",
            nome="Verdi",
            mail="sq@example.invalid",
            regione=1,
            zona=1,
            gruppo=1,
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
            anno_percorso=1,
        )
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


if __name__ == "__main__":
    unittest.main()
