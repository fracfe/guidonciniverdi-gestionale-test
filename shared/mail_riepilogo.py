"""Generazione pura del riepilogo email di una iscrizione."""

from html import escape


def _testo(value):
    if value is None:
        return ""
    return escape(str(value).strip())


def _riga(etichetta, valore):
    return f"<tr><th align=\"left\">{escape(etichetta)}</th><td>{_testo(valore)}</td></tr>"


def _indirizzi(*valori):
    risultato = []
    for valore in valori:
        indirizzo = str(valore).strip() if valore else ""
        if indirizzo and indirizzo not in risultato:
            risultato.append(indirizzo)
    return risultato


def genera_mail_riepilogo_iscrizione(
    iscrizione,
    regione,
    zona,
    gruppo,
    percorso,
    wordpress_user=None,
    operazione="modifica",
):
    """Restituisce oggetto, HTML e destinatari usando lo stato corrente."""
    introduzioni = {
        "modifica": "I dati dell'iscrizione sono stati aggiornati correttamente.",
        "reset_password": "Le credenziali del Diario di Bordo sono state aggiornate correttamente.",
    }
    oggetti = {
        "modifica": "Dati aggiornati iscrizione Guidoncini Verdi",
        "reset_password": "Credenziali aggiornate Guidoncini Verdi",
    }
    if operazione not in introduzioni:
        raise ValueError("operazione riepilogo non supportata")

    sesso = {"m": "Maschile", "f": "Femminile"}.get(
        str(getattr(iscrizione, "sesso", "")).lower(),
        getattr(iscrizione, "sesso", ""),
    )
    righe_squadriglia = [
        _riga("Nome squadriglia", iscrizione.nome),
        _riga("Sesso", sesso),
        _riga("Regione", regione.regione),
        _riga("Zona", zona.zona),
        _riga("Gruppo", gruppo.gruppo),
        _riga("Ambito di specialità", iscrizione.specialita),
        _riga("Percorso", iscrizione.tipo.capitalize()),
        _riga("Anno", percorso.anno),
    ]
    righe_contatti = [
        _riga("Capo squadriglia", iscrizione.nome_capo_sq),
        _riga("Email di contatto", iscrizione.mail),
        _riga("Capo reparto 1", iscrizione.nome_capo1),
        _riga("Email capo reparto 1", iscrizione.mail_capo1),
        _riga("Telefono capo reparto 1", iscrizione.cell_capo1),
    ]
    if any(
        getattr(iscrizione, campo, None)
        for campo in ("nome_capo2", "mail_capo2", "cell_capo2")
    ):
        righe_contatti.extend([
            _riga("Capo reparto 2", iscrizione.nome_capo2),
            _riga("Email capo reparto 2", iscrizione.mail_capo2),
            _riga("Telefono capo reparto 2", iscrizione.cell_capo2),
        ])

    sezione_wordpress = ""
    avviso = (
        "Questa comunicazione riepiloga i dati attualmente registrati per la "
        "squadriglia. Conservatela come riferimento."
    )
    if wordpress_user:
        sezione_wordpress = (
            "<h3>Credenziali Diario WordPress</h3><table>"
            f"{_riga('Username', wordpress_user.username)}"
            f"{_riga('Password', wordpress_user.password)}"
            "</table>"
        )
        avviso = (
            "Questa comunicazione riepiloga i dati attualmente registrati per "
            "la squadriglia. Conservatela con attenzione perché contiene le "
            "credenziali di accesso al Diario di Bordo."
        )

    html = (
        f"<p>{escape(introduzioni[operazione])}</p>"
        "<p>Questa è la situazione attualmente registrata per la squadriglia.</p>"
        f"<h3>Dati squadriglia</h3><table>{''.join(righe_squadriglia)}</table>"
        f"<h3>Contatti</h3><table>{''.join(righe_contatti)}</table>"
        f"{sezione_wordpress}"
        f"<p><strong>{avviso}</strong></p>"
    )
    destinatari = _indirizzi(iscrizione.mail)
    if not destinatari:
        raise ValueError("destinatario principale non disponibile")

    copia = [
        indirizzo
        for indirizzo in _indirizzi(
            iscrizione.mail_capo1, iscrizione.mail_capo2
        )
        if indirizzo not in destinatari
    ]
    return {
        "oggetto": oggetti[operazione],
        "html": html,
        "destinatari": destinatari,
        "copia": copia,
        "anno": percorso.anno,
    }
