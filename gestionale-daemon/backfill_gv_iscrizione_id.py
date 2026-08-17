"""Backfill controllato del meta WordPress gv_iscrizione_id.

Il comando e' read-only per default. Solo --apply abilita le scritture REST.
Gli abbinamenti provengono esclusivamente dai mirror WordpressUser e
WordpressPost del Gestionale; non vengono usate euristiche su nomi o titoli.
"""

import argparse
import base64
import os
import sys

from daemon import (
    Session,
    WordpressPost,
    WordpressRequestError,
    WordpressUser,
    id_wordpress,
    lookup_provisioning_wordpress,
    richiesta_wordpress_json,
)


def header_wordpress():
    credenziali = f"{os.environ['WORDPRESS_USER']}:{os.environ['WORDPRESS_PASSWORD']}"
    token = base64.b64encode(credenziali.encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def verifica_risorsa(endpoint, header, operazione, id_atteso):
    payload, status_http = richiesta_wordpress_json(
        "GET", f"{endpoint}?context=edit", header, operazione
    )
    id_risorsa = id_wordpress(payload, operazione, endpoint, status_http)
    if id_risorsa != id_atteso:
        raise WordpressRequestError(
            operazione,
            endpoint,
            "id REST diverso dal mirror locale",
            status_http=status_http,
        )
    return payload


def backfill(apply=False):
    session = Session()
    header = header_wordpress()
    conflitti = 0
    aggiornamenti = 0
    try:
        utenti = session.query(WordpressUser).order_by(WordpressUser.iscrizioni_id).all()
        post = session.query(WordpressPost).filter_by(tipo="posts").all()
        utenti_per_iscrizione = {}
        post_per_iscrizione = {}
        for utente in utenti:
            utenti_per_iscrizione.setdefault(utente.iscrizioni_id, []).append(utente)
        for pagina in post:
            post_per_iscrizione.setdefault(pagina.iscrizioni_id, []).append(pagina)

        iscrizioni = sorted(set(utenti_per_iscrizione) | set(post_per_iscrizione))
        for iscrizione_id in iscrizioni:
            utenti_locali = utenti_per_iscrizione.get(iscrizione_id, [])
            post_locali = post_per_iscrizione.get(iscrizione_id, [])
            if len(utenti_locali) != 1 or len(post_locali) > 1:
                print(
                    f"CONFLICT iscrizione={iscrizione_id} "
                    f"utenti_locali={len(utenti_locali)} post_locali={len(post_locali)}"
                )
                conflitti += 1
                continue

            utente = utenti_locali[0]
            pagina = post_locali[0] if post_locali else None
            try:
                remoto = lookup_provisioning_wordpress(iscrizione_id, header)
                if remoto["user"] and (
                    remoto["user"]["id"] != utente.wordpress_id
                    or remoto["user"]["username"] != utente.username
                ):
                    raise WordpressRequestError(
                        "backfill utente",
                        f"/users/{utente.wordpress_id}",
                        "meta stabile gia' associato a un altro utente",
                    )
                if remoto["post"] and (
                    pagina is None
                    or remoto["post"]["id"] != pagina.wordpress_id
                    or remoto["post"]["author"] != utente.wordpress_id
                ):
                    raise WordpressRequestError(
                        "backfill post",
                        f"/posts/{pagina.wordpress_id if pagina else 0}",
                        "meta stabile gia' associato a un altro post",
                    )

                payload_utente = verifica_risorsa(
                    f"/users/{utente.wordpress_id}",
                    header,
                    "verifica utente backfill",
                    utente.wordpress_id,
                )
                if payload_utente.get("username") != utente.username:
                    raise WordpressRequestError(
                        "verifica utente backfill",
                        f"/users/{utente.wordpress_id}",
                        "username WordPress diverso dal mirror locale",
                    )

                if pagina:
                    payload_post = verifica_risorsa(
                        f"/posts/{pagina.wordpress_id}",
                        header,
                        "verifica post backfill",
                        pagina.wordpress_id,
                    )
                    if payload_post.get("author") != utente.wordpress_id:
                        raise WordpressRequestError(
                            "verifica post backfill",
                            f"/posts/{pagina.wordpress_id}",
                            "autore WordPress diverso dal mirror utente locale",
                        )

                azioni = []
                if remoto["user"] is None:
                    azioni.append(f"user:{utente.wordpress_id}")
                if pagina and remoto["post"] is None:
                    azioni.append(f"post:{pagina.wordpress_id}")
                print(
                    f"{'APPLY' if apply else 'DRY-RUN'} iscrizione={iscrizione_id} "
                    f"azioni={','.join(azioni) if azioni else 'nessuna'}"
                )

                if apply and remoto["user"] is None:
                    richiesta_wordpress_json(
                        "POST",
                        f"/users/{utente.wordpress_id}",
                        header,
                        "backfill meta utente",
                        dati={"meta": {"gv_iscrizione_id": int(iscrizione_id)}},
                    )
                    aggiornamenti += 1
                if apply and pagina and remoto["post"] is None:
                    richiesta_wordpress_json(
                        "POST",
                        f"/posts/{pagina.wordpress_id}",
                        header,
                        "backfill meta post",
                        dati={"meta": {"gv_iscrizione_id": int(iscrizione_id)}},
                    )
                    aggiornamenti += 1

                if apply:
                    verificato = lookup_provisioning_wordpress(iscrizione_id, header)
                    if (
                        not verificato["user"]
                        or verificato["user"]["id"] != utente.wordpress_id
                        or (pagina and (
                            not verificato["post"]
                            or verificato["post"]["id"] != pagina.wordpress_id
                            or verificato["post"]["author"] != utente.wordpress_id
                        ))
                    ):
                        raise WordpressRequestError(
                            "verifica backfill",
                            f"/guidonciniverdi/v1/provisioning/{iscrizione_id}",
                            "risorse non riconciliate dopo l'aggiornamento",
                        )
            except WordpressRequestError as exc:
                print(
                    f"CONFLICT iscrizione={iscrizione_id} "
                    f"operazione={exc.operazione} motivo={exc.motivo}"
                )
                conflitti += 1
            except Exception as exc:
                print(
                    f"ERROR iscrizione={iscrizione_id} tipo={type(exc).__name__}"
                )
                conflitti += 1
        print(
            f"SUMMARY modalita={'apply' if apply else 'dry-run'} "
            f"iscrizioni={len(iscrizioni)} aggiornamenti={aggiornamenti} "
            f"conflitti={conflitti}"
        )
        return 2 if conflitti else 0
    finally:
        session.rollback()
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill del meta stabile di provisioning WordPress"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="applica le modifiche; senza questa opzione il comando e' read-only",
    )
    args = parser.parse_args()
    return backfill(apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
