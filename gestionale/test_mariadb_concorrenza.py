import os
import threading
import unittest
from datetime import datetime


@unittest.skipUnless(
    os.environ.get("RUN_MARIADB_INTEGRATION") == "1",
    "richiede un MariaDB di test usa-e-getta",
)
class ConcorrenzaJobMariaDBTest(unittest.TestCase):
    REGIONE_ID = 2_147_000_001
    ZONA_ID = 2_147_000_002
    GRUPPO_ID = 2_147_000_003
    PERCORSO_ID = 2_147_000_004
    ISCRIZIONE_IDS = (2_147_000_011, 2_147_000_012)
    MARCATORE = "__test_concorrenza_mariadb__"

    @classmethod
    def setUpClass(cls):
        import app as app_module
        from sqlalchemy.orm import sessionmaker

        cls.modulo = app_module
        cls.app_context = app_module.app.app_context()
        cls.app_context.push()
        cls.session_factory = sessionmaker(bind=app_module.db.engine)
        cls.ids = cls.ISCRIZIONE_IDS
        try:
            cls._cleanup_fixture()
            cls._crea_fixture()
        except Exception:
            try:
                cls._cleanup_fixture()
            finally:
                cls.app_context.pop()
            raise
        cls.app_context.pop()

    @classmethod
    def _crea_fixture(cls):
        m = cls.modulo
        session = cls.session_factory()
        try:
            session.add(m.Regione(
                id=cls.REGIONE_ID,
                regione=cls.MARCATORE,
                mail="concorrenza@example.invalid",
            ))
            session.commit()

            session.add(m.Zona(
                id=cls.ZONA_ID,
                zona=cls.MARCATORE,
                regione=cls.REGIONE_ID,
            ))
            session.commit()

            session.add(m.Gruppo(
                id=cls.GRUPPO_ID,
                gruppo=cls.MARCATORE,
                zona=cls.ZONA_ID,
                regione=cls.REGIONE_ID,
            ))
            session.commit()

            session.add(m.StatusPercorso(
                id=cls.PERCORSO_ID,
                anno="2099",
                iscrizioni=True,
                abilitazioni=True,
                regione=cls.REGIONE_ID,
            ))
            session.commit()

            for id_iscrizione in cls.ids:
                session.add(m.IscrizioneEG(
                    id=id_iscrizione,
                    data=datetime.now(),
                    stato="abilitato",
                    nome=f"{cls.MARCATORE}{id_iscrizione}",
                    mail="concorrenza@example.invalid",
                    regione=cls.REGIONE_ID,
                    zona=cls.ZONA_ID,
                    gruppo=cls.GRUPPO_ID,
                    specialita="Natura",
                    tipo="conquista",
                    nome_capo_sq="Capo",
                    nome_capo1="Capo 1",
                    mail_capo1="capo1@example.invalid",
                    cell_capo1="000",
                    nome_capo2="Capo 2",
                    mail_capo2="capo2@example.invalid",
                    cell_capo2="001",
                    sesso="M",
                    link="http://example.invalid",
                    anno_percorso=cls.PERCORSO_ID,
                ))
            session.commit()

            territorio = (
                session.get(m.Regione, cls.REGIONE_ID),
                session.get(m.Zona, cls.ZONA_ID),
                session.get(m.Gruppo, cls.GRUPPO_ID),
                session.get(m.StatusPercorso, cls.PERCORSO_ID),
            )
            if not all(territorio):
                raise RuntimeError("fixture territoriale MariaDB incompleta")
            _, zona, gruppo, percorso = territorio
            if (
                zona.regione != cls.REGIONE_ID
                or gruppo.zona != cls.ZONA_ID
                or gruppo.regione != cls.REGIONE_ID
                or percorso.regione != cls.REGIONE_ID
            ):
                raise RuntimeError("fixture territoriale MariaDB non coerente")
            if any(session.get(m.IscrizioneEG, id_) is None for id_ in cls.ids):
                raise RuntimeError("fixture iscrizioni MariaDB incompleta")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def _cleanup_fixture(cls):
        m = cls.modulo
        session = cls.session_factory()
        try:
            controlli = (
                (m.Regione, cls.REGIONE_ID, "regione", cls.MARCATORE),
                (m.Zona, cls.ZONA_ID, "zona", cls.MARCATORE),
                (m.Gruppo, cls.GRUPPO_ID, "gruppo", cls.MARCATORE),
            )
            for modello, id_record, attributo, valore_atteso in controlli:
                record = session.get(modello, id_record)
                if record and getattr(record, attributo) != valore_atteso:
                    raise RuntimeError(
                        f"ID fixture {id_record} occupato da dati non appartenenti al test"
                    )
            percorso = session.get(m.StatusPercorso, cls.PERCORSO_ID)
            if percorso and (
                percorso.anno != "2099"
                or percorso.regione != cls.REGIONE_ID
            ):
                raise RuntimeError(
                    f"ID fixture {cls.PERCORSO_ID} occupato da dati non appartenenti al test"
                )
            for id_iscrizione in cls.ids:
                iscrizione = session.get(m.IscrizioneEG, id_iscrizione)
                if iscrizione and not iscrizione.nome.startswith(cls.MARCATORE):
                    raise RuntimeError(
                        f"ID fixture {id_iscrizione} occupato da dati non appartenenti al test"
                    )

            session.query(m.JobWordpress).filter(
                m.JobWordpress.iscrizione_id.in_(cls.ids)
            ).delete(synchronize_session=False)
            session.query(m.IscrizioneEG).filter(
                m.IscrizioneEG.id.in_(cls.ids)
            ).delete(synchronize_session=False)
            session.query(m.StatusPercorso).filter_by(
                id=cls.PERCORSO_ID
            ).delete(synchronize_session=False)
            session.query(m.Gruppo).filter_by(
                id=cls.GRUPPO_ID
            ).delete(synchronize_session=False)
            session.query(m.Zona).filter_by(
                id=cls.ZONA_ID
            ).delete(synchronize_session=False)
            session.query(m.Regione).filter_by(
                id=cls.REGIONE_ID
            ).delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_fixture()

    def setUp(self):
        m = self.modulo
        session = self.session_factory()
        try:
            session.query(m.JobWordpress).filter(
                m.JobWordpress.iscrizione_id.in_(self.ids)
            ).delete(synchronize_session=False)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def esegui_concorrenti(self, ids):
        barriera = threading.Barrier(2)
        risultati = []
        errori = []

        def accoda(id_iscrizione):
            session = self.session_factory()
            try:
                barriera.wait(timeout=5)
                risultato = self.modulo.accoda_update_wordpress_con_lock(
                    session, id_iscrizione
                )
                session.commit()
                risultati.append((id_iscrizione, risultato))
            except Exception as exc:
                session.rollback()
                errori.append(exc)
            finally:
                session.close()

        thread = [threading.Thread(target=accoda, args=(id_,)) for id_ in ids]
        for corrente in thread:
            corrente.start()
        for corrente in thread:
            corrente.join(timeout=10)
        self.assertFalse(any(corrente.is_alive() for corrente in thread), "lock permanente")
        self.assertEqual(errori, [])
        return risultati

    def test_stessa_iscrizione_crea_un_solo_job_attivo(self):
        risultati = self.esegui_concorrenti((self.ids[0], self.ids[0]))
        self.assertEqual(sum(esito for _, esito in risultati), 1)
        session = self.session_factory()
        count = session.query(self.modulo.JobWordpress).filter(
            self.modulo.JobWordpress.iscrizione_id == self.ids[0],
            self.modulo.JobWordpress.stato.in_(["PENDING", "SENDING"]),
        ).count()
        stato = session.get(self.modulo.IscrizioneEG, self.ids[0]).stato
        session.close()
        self.assertEqual(count, 1)
        self.assertEqual(stato, "abilitato")

    def test_iscrizioni_diverse_non_condividono_il_lock(self):
        risultati = self.esegui_concorrenti(self.ids)
        self.assertEqual(sorted(risultati), sorted((id_, True) for id_ in self.ids))
        session = self.session_factory()
        count = session.query(self.modulo.JobWordpress).filter(
            self.modulo.JobWordpress.iscrizione_id.in_(self.ids),
            self.modulo.JobWordpress.stato.in_(["PENDING", "SENDING"]),
        ).count()
        stati = {
            session.get(self.modulo.IscrizioneEG, id_).stato for id_ in self.ids
        }
        session.close()
        self.assertEqual(count, 2)
        self.assertEqual(stati, {"abilitato"})


if __name__ == "__main__":
    unittest.main()
