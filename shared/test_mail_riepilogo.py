import unittest
from types import SimpleNamespace

from shared.mail_riepilogo import genera_mail_riepilogo_iscrizione


class MailRiepilogoTest(unittest.TestCase):
    def setUp(self):
        self.iscrizione = SimpleNamespace(
            nome="Volpi & Lupi",
            sesso="f",
            mail="squadriglia@example.invalid",
            specialita="Natura",
            tipo="conferma",
            nome_capo_sq="Capo squadriglia",
            nome_capo1="Capo reparto uno",
            mail_capo1="capo1@example.invalid",
            cell_capo1="111",
            nome_capo2="Capo reparto due",
            mail_capo2="capo2@example.invalid",
            cell_capo2="222",
        )
        self.regione = SimpleNamespace(regione="Piemonte")
        self.zona = SimpleNamespace(zona="Zona Torino")
        self.gruppo = SimpleNamespace(gruppo="Torino 1")
        self.percorso = SimpleNamespace(anno="2025")
        self.wordpress_user = SimpleNamespace(
            username="volpi_stabile", password="NuovaPassword"
        )

    def genera(self, wordpress_user=None, operazione="modifica"):
        return genera_mail_riepilogo_iscrizione(
            self.iscrizione,
            self.regione,
            self.zona,
            self.gruppo,
            self.percorso,
            wordpress_user=wordpress_user,
            operazione=operazione,
        )

    def test_riepilogo_completo_usa_dati_correnti_e_credenziali(self):
        riepilogo = self.genera(self.wordpress_user, "reset_password")

        for valore in [
            "Volpi &amp; Lupi",
            "Femminile",
            "Piemonte",
            "Zona Torino",
            "Torino 1",
            "Natura",
            "Conferma",
            "2025",
            "Capo squadriglia",
            "capo1@example.invalid",
            "111",
            "Capo reparto due",
            "volpi_stabile",
            "NuovaPassword",
        ]:
            self.assertIn(valore, riepilogo["html"])
        self.assertEqual(
            riepilogo["destinatari"], ["squadriglia@example.invalid"]
        )
        self.assertEqual(
            riepilogo["copia"],
            ["capo1@example.invalid", "capo2@example.invalid"],
        )

    def test_senza_wordpress_o_secondo_capo_non_inserisce_valori_vuoti(self):
        self.iscrizione.nome_capo2 = None
        self.iscrizione.mail_capo2 = ""
        self.iscrizione.cell_capo2 = None

        riepilogo = self.genera()

        self.assertNotIn("Credenziali Diario WordPress", riepilogo["html"])
        self.assertNotIn("None", riepilogo["html"])
        self.assertNotIn("Capo reparto 2", riepilogo["html"])
        self.assertEqual(riepilogo["copia"], ["capo1@example.invalid"])


if __name__ == "__main__":
    unittest.main()
