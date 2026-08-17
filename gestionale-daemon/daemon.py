from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey, UnicodeText
from sqlalchemy.orm import declarative_base, sessionmaker
from jinja2 import Environment, FileSystemLoader
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote
from datetime import datetime, timedelta
from time import sleep
import threading
import schedule
import requests
import smtplib
import random
import base64
import json
import os
import logging
from shared.mail_riepilogo import genera_mail_riepilogo_iscrizione


logger = logging.getLogger("guidonciniverdi.daemon.wordpress")
WORDPRESS_TIMEOUT = (5, 30)
JOB_STALE_AFTER = timedelta(minutes=15)
JOB_MAX_ATTEMPTS = 3


class WordpressRequestError(Exception):
    def __init__(self, operazione, endpoint, motivo, status_http=None):
        super().__init__(motivo)
        self.operazione = operazione
        self.endpoint = endpoint
        self.motivo = motivo
        self.status_http = status_http

specialita = [
    "Alpinismo",
    "Artigianato",
    "Campismo",
    "Civitas",
    "Esplorazione",
    "Espressione",
    "Giornalismo",
    "Internazionale",
    "Natura",
    "Nautica",
    "Olimpia",
    "Pronto intervento"
]

sender_address = os.environ["MAIL_USERNAME"]
smtp_host = os.environ["MAIL_HOST"]
smtp_port = os.environ["MAIL_PORT"]

drivers = {
    "sqlite": "sqlite:///",
    "mariadb": "mysql+pymysql://",
}

db_type = os.environ["DB_TYPE"]
if db_type not in drivers:
    print("Tipo di database non supportato")
    raise RuntimeError("Tipo di database non supportato")

if db_type == "sqlite":
    uri = f"{drivers[db_type]}{os.environ['DB_NAME']}"
else:
    uri = (
        f"{drivers[db_type]}"
        f"{os.environ['DB_USER']}:"
        f"{os.environ['DB_PASSWORD']}@"
        f"{os.environ['DB_HOST']}:"
        f"{os.environ['DB_PORT']}/"
        f"{os.environ['DB_NAME']}"
    )

Base = declarative_base()

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    username = Column(String(255), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
    mail = Column(String(255), nullable=False)
    regione = Column(Integer, ForeignKey("regioni.id", name="fk_user_regioni_id"), nullable=True)
    zona = Column(Integer, ForeignKey("zone.id", name="fk_user_zone_id"), nullable=True)
    livello = Column(String(255), nullable=False)
    telegram_id = Column(String(255), nullable=True)

class IscrizioneEG(Base):
    __tablename__ = "iscrizioni_eg"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    stato = Column(String(255), nullable=False)
    nome = Column(String(255), nullable=False)
    mail = Column(String(255), nullable=False)
    regione = Column(Integer,ForeignKey("regioni.id", name="fk_iscrizioni_eg_regioni_id"), nullable=False)
    zona = Column(Integer, ForeignKey("zone.id", name="fk_iscrizioni_eg_zone_id"), nullable=False)
    gruppo = Column(Integer, ForeignKey("gruppi.id", name="fk_iscrizioni_eg_gruppi_id"), nullable=False)
    specialita = Column(String(255), nullable=False)
    # tipo indica se conquista o conferma => True se conferma
    tipo = Column(String(255), nullable=False)
    # Contatti
    nome_capo_sq = Column(String(255), nullable=False)
    nome_capo1 = Column(String(255), nullable=False)
    mail_capo1 = Column(String(255), nullable=False)
    cell_capo1 = Column(String(255), nullable=False)
    nome_capo2 = Column(String(255), nullable=False)
    mail_capo2 = Column(String(255), nullable=False)
    cell_capo2 = Column(String(255), nullable=False)
    sesso = Column(String(2), nullable=False)
    link = Column(Text, nullable=False)
    anno_percorso = Column(Integer, ForeignKey("status_percorso.id", name="fk_iscrizioni_eg_status_percorso_id"), nullable=True)

class WordpressUser(Base):
    __tablename__ = "wordpress_user"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    iscrizioni_id = Column(Integer, ForeignKey("iscrizioni_eg.id", name="fk_wordpress_user_iscrizioni_id"), nullable=False)
    wordpress_id = Column(Integer, nullable=False)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)
    meta = Column(JSON, nullable=False)

class WordpressPost(Base):
    __tablename__ = "wordpress_post"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    iscrizioni_id = Column(Integer, ForeignKey("iscrizioni_eg.id", name="fk_wordpress_post_iscrizioni_id"), nullable=False)
    wordpress_user_id = Column(Integer, ForeignKey("wordpress_user.id", name="fk_wordpress_post_wordpress_user_id"), nullable=False)
    wordpress_id = Column(Integer, nullable=False)
    tipo = Column(String(255), nullable=False)
    meta = Column(JSON, nullable=False)

class RelazioniPuglia(Base):
    __tablename__ = "relazioni_puglia"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    stato = Column(Boolean, nullable=False)
    iscrizioni_id = Column(Integer, ForeignKey("iscrizioni_eg.id", name="fk_relazioni_puglia_iscrizioni_id"), nullable=False)
    dati = Column(JSON, nullable=False)

class MailMassiva(Base):
    __tablename__ = "mail_massive"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    stato = Column(String(255), nullable=False)
    regione = Column(Integer, ForeignKey("regioni.id", name="fk_mail_massive_regioni_id"), nullable=False)
    destinatari = Column(JSON, nullable=False)
    titolo = Column(String(255), nullable=False)
    testo = Column(UnicodeText, nullable=False)

class CodaMail(Base):
    __tablename__ = "coda_mail"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    stato = Column(String(255), nullable=False)
    regione = Column(Integer, ForeignKey("regioni.id", name="fk_coda_mail_regioni_id"), nullable=False)
    indirizzi = Column(JSON, nullable=False)
    indirizzi_copia = Column(JSON, nullable=False)
    titolo = Column(String(255), nullable=False)
    testo = Column(UnicodeText, nullable=False)

class CodaTelegram(Base):
    __tablename__ = "coda_telegram"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    stato = Column(String(255), nullable=False)
    chat_id = Column(Integer, nullable=False)
    titolo = Column(String(255), nullable=False)
    testo = Column(UnicodeText, nullable=False)

class JobWordpress(Base):
    __tablename__ = "job_wordpress"
    id = Column(Integer, primary_key=True)
    data = Column(DateTime, nullable=False)
    stato = Column(String(255), nullable=False)
    tipo = Column(String(255), nullable=False, default="crea_sq")
    iscrizione_id = Column(
        Integer,
        ForeignKey(
            "iscrizioni_eg.id",
            name="fk_job_wordpress_iscrizioni_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    started_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    dati = Column(JSON, nullable=False)

class StatusPercorso(Base):
    __tablename__ = "status_percorso"
    id = Column(Integer, primary_key=True)
    anno = Column(String(4), nullable=True)
    iscrizioni = Column(JSON, nullable=False)
    abilitazioni = Column(JSON, nullable=False)
    regione = Column(Integer, ForeignKey("regioni.id", name="fk_status_percorso_regioni_id"), nullable=True)
    data_apertura = Column(DateTime, nullable=True)
    data_chiusura = Column(DateTime, nullable=True)

class Regione(Base):
    __tablename__ = "regioni"
    id = Column(Integer, primary_key=True)
    regione = Column(String(255), nullable=False)
    mail = Column(String(255), nullable=True)

class Zona(Base):
    __tablename__ = "zone"
    id = Column(Integer, primary_key=True)
    zona = Column(String(255), nullable=False)
    regione = Column(Integer, ForeignKey("regioni.id", name="fk_zone_regioni_id"), nullable=False)

class Gruppo(Base):
    __tablename__ = "gruppi"
    id = Column(Integer, primary_key=True)
    gruppo = Column(String(255), nullable=True)
    zona = Column(Integer, ForeignKey("zone.id", name="fk_gruppi_zone_id"), nullable=False)
    regione = Column(Integer, ForeignKey("regioni.id", name="fk_gruppi_regioni_id"), nullable=False)

class Demone(Base):
    __tablename__ = "demoni"
    key = Column(String(255), primary_key=True)
    value = Column(Boolean, nullable=False)

class SysOption(Base):
    __tablename__ = "system_option"
    key = Column(String(128), primary_key=True)
    value = Column(String(128), nullable=False)

engine = create_engine(uri, pool_pre_ping=True, pool_recycle=3600)
Session = sessionmaker(bind=engine)

demone_mail = True
demone_telegram = True
demone_notifiche = True
demone_wordpress = True

def manda_mail(indirizzi, copia, titolo, testo, regione, anno=None):
    session = Session()
    try:
        anno_mail = anno or session.query(SysOption).filter_by(
            key="AnnoCorrente"
        ).first().value
        session.add(CodaMail(
            data=datetime.now(),
            stato="PENDING",
            regione=regione,
            indirizzi=indirizzi,
            indirizzi_copia=copia,
            titolo=f"Guidoncini Verdi {anno_mail} - {titolo}",
            testo=testo,
        ))
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def manda_telegram(chat_id, titolo, testo):
    session = Session()
    session.add(CodaTelegram(data=datetime.now(), stato="PENDING", chat_id=chat_id, titolo=f"Guidoncini Verdi {session.query(SysOption).filter_by(key='AnnoCorrente').first().value} - {titolo}", testo=testo))
    session.commit()
    return True

def genera_password_sq():
    nomi = ["Akela", "Baloo", "Chil", "Kaa", "Raksha", "Arcanda", "Sciba", "Scoiattoli", "Mi", "Mowgli"]
    colori = ["Rosso", "Blu", "Verde", "Giallo", "Arancione", "Viola", "Rosa", "Marrone", "Grigio", "Nero"]
    return f"{random.choice(nomi)}{random.choice(colori)}"

def richiesta_wordpress_json(metodo, endpoint, header, operazione, dati=None):
    url = f"{os.environ['WORDPRESS_URL'].rstrip('/')}{endpoint}"
    kwargs = {"headers": header, "timeout": WORDPRESS_TIMEOUT}
    if dati is not None:
        kwargs["json"] = dati

    try:
        if metodo == "GET":
            response = requests.get(url, **kwargs)
        elif metodo == "POST":
            response = requests.post(url, **kwargs)
        else:
            raise ValueError(f"Metodo HTTP non supportato: {metodo}")
    except requests.Timeout as exc:
        raise WordpressRequestError(
            operazione, endpoint, "timeout HTTP"
        ) from exc
    except requests.ConnectionError as exc:
        raise WordpressRequestError(
            operazione, endpoint, "errore di connessione"
        ) from exc
    except requests.RequestException as exc:
        raise WordpressRequestError(
            operazione, endpoint, f"errore HTTP {type(exc).__name__}"
        ) from exc

    status_http = response.status_code
    if not 200 <= status_http < 300:
        codice_wordpress = None
        try:
            payload_errore = response.json()
            if isinstance(payload_errore, dict):
                codice_wordpress = payload_errore.get("code")
        except (TypeError, ValueError):
            pass
        motivo = "risposta HTTP di errore"
        if codice_wordpress:
            motivo = f"{motivo} (codice WordPress: {codice_wordpress})"
        raise WordpressRequestError(
            operazione, endpoint, motivo, status_http=status_http
        )

    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise WordpressRequestError(
            operazione,
            endpoint,
            "risposta JSON non valida",
            status_http=status_http,
        ) from exc
    return payload, status_http


def id_wordpress(payload, operazione, endpoint, status_http):
    id_risorsa = payload.get("id") if isinstance(payload, dict) else None
    if type(id_risorsa) is not int or id_risorsa <= 0:
        raise WordpressRequestError(
            operazione,
            endpoint,
            "risposta JSON inattesa: id assente o non numerico",
            status_http=status_http,
        )
    return id_risorsa


def crea_utente(session, id_iscrizione, header, dati):
    endpoint = "/users"
    payload, status_http = richiesta_wordpress_json(
        "POST", endpoint, header, "creazione utente", dati=dati
    )
    id_autore = id_wordpress(
        payload, "creazione utente", endpoint, status_http
    )
    utente = WordpressUser(data=datetime.now(), iscrizioni_id=int(id_iscrizione), wordpress_id=int(id_autore), username=dati["username"], password=dati["password"], meta=dati)
    session.add(utente)
    session.commit()
    return id_autore

def crea_post(session, id_iscrizione, id_autore, header, dati, tipo):
    endpoint = "/posts"
    payload, status_http = richiesta_wordpress_json(
        "POST", endpoint, header, "creazione post", dati=dati
    )
    id_post = id_wordpress(payload, "creazione post", endpoint, status_http)
    utente = session.query(WordpressUser).filter_by(wordpress_id=int(id_autore)).first()
    post = WordpressPost(data=datetime.now(), iscrizioni_id=int(id_iscrizione), wordpress_user_id=utente.id, wordpress_id=int(id_post), tipo=tipo, meta=dati)
    session.add(post)
    session.commit()
    return id_post

def send_notifiche():
    def task():
        scheduler = schedule.Scheduler()
        def job():
            session = Session()
            try:
                tmp_utenti = session.query(User).filter_by(livello="iabr").all()
                tmp_utenti.extend(session.query(User).filter_by(livello="pattuglia").all())
                for i in tmp_utenti:
                    non_abilitate = session.query(IscrizioneEG).filter_by(stato="da_abilitare").filter_by(regione=i.regione).count()
                    abilitate = session.query(IscrizioneEG).filter_by(stato="abilitato").filter_by(regione=i.regione).count()
                    testo_telegram = f"Da abilitare: {non_abilitate}\nAbilitate: {abilitate}"
                    if non_abilitate > 0:
                        manda_telegram(i.telegram_id, f"Report {i.regione.capitalize()}", testo_telegram)

                tmp_utenti = session.query(User).filter_by(livello="iabz").all()
                for i in tmp_utenti:
                    non_abilitate = session.query(IscrizioneEG).filter_by(stato="da_abilitare").filter_by(zona=i.zona).count()
                    abilitate = session.query(IscrizioneEG).filter_by(stato="abilitato").filter_by(zona=i.zona).count()
                    testo_telegram = f"Da abilitare: {non_abilitate}\nAbilitate: {abilitate}"
                    if non_abilitate > 0:
                        manda_telegram(i.telegram_id, f"Report {i.zona}", testo_telegram)
            except Exception as e:
                print(e)
            session.close()

        scheduler.every().saturday.at("10:00").do(job)

        global demone_notifiche
        while demone_notifiche:
            scheduler.run_pending()
            sleep(1)
    threading.Thread(target=task, name="send_notifiche", daemon=True).start()

def send_telegram():
    def task():
        scheduler = schedule.Scheduler()
        def job():
            session = Session()
            tmp_telegram = session.query(CodaTelegram).filter_by(stato="PENDING").first()
            if tmp_telegram:
                tmp_telegram.stato = "SENDING"
                session.commit()
                try:
                    text = quote(f"{tmp_telegram.titolo}\n{tmp_telegram.testo}")
                    t_url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage?chat_id={tmp_telegram.chat_id}&text={text}"
                    requests.get(t_url, timeout=20)
                    
                    tmp_telegram.stato = "SENT"

                except Exception as e:
                    print(e)
                    tmp_telegram.stato = "FAILED"
                session.commit()
            session.close()

        scheduler.every(10).seconds.do(job)

        global demone_telegram
        while demone_telegram:
            scheduler.run_pending()
            sleep(1)
    threading.Thread(target=task, name="send_telegram", daemon=True).start()

def send_mail():
    def task():
        env = Environment(loader=FileSystemLoader("."))
        template = env.get_template("mail_base.html")
        scheduler = schedule.Scheduler()
        def job():
            session = Session()
            tmp_mail = session.query(CodaMail).filter_by(stato="PENDING").first()
            if tmp_mail:
                tmp_mail.stato = "SENDING"
                session.commit()
                try:
                    tmp_regione = session.query(Regione).filter_by(id=tmp_mail.regione).first()
                    anno = session.query(SysOption).filter_by(key="AnnoCorrente").first().value
                    html = template.render(anno=anno, titolo=tmp_mail.titolo, testo=tmp_mail.testo, mail_regione=tmp_regione.mail)
                    indirizzi = tmp_mail.indirizzi.copy()
                    message = MIMEMultipart("alternative")
                    message["Subject"] = f"Guidoncini Verdi {anno} - {tmp_mail.titolo}"
                    message["From"] = sender_address
                    message["Reply-To"] = tmp_regione.mail
                    message["To"] = ", ".join(tmp_mail.indirizzi)
                    if tmp_mail.indirizzi_copia:
                        message["Cc"] = ", ".join(tmp_mail.indirizzi_copia)
                        indirizzi.extend(tmp_mail.indirizzi_copia)
                        indirizzi = [x for x in indirizzi if x != ""]

                    text = f"{tmp_mail.titolo}\n{tmp_mail.testo}"
                    part1 = MIMEText(text, "plain")
                    part2 = MIMEText(html, "html")
                    message.attach(part1)
                    message.attach(part2)

                    with smtplib.SMTP(smtp_host, smtp_port) as server:
                        response = server.sendmail(sender_address, indirizzi, message.as_string())
                    
                    refused_count = len(response)
                    sent_count = len(indirizzi) - refused_count
                    if refused_count:
                        print(f"Mail {tmp_mail.id}: destinatari rifiutati dal server SMTP: {response}")

                    if sent_count > 0:
                        tmp_mail.stato = "SENT"
                    else:
                        tmp_mail.stato = "FAILED"

                except Exception as e:
                    print(e)
                    tmp_mail.stato = "FAILED"
                session.commit()
            session.close()

        scheduler.every(10).seconds.do(job)

        global demone_mail
        while demone_mail:
            scheduler.run_pending()
            sleep(1)
    threading.Thread(target=task, name="send_mail", daemon=True).start()

def contesto_job_wordpress(tmp_job):
    dati = tmp_job.dati if isinstance(tmp_job.dati, dict) else {}
    return {
        "job_id": tmp_job.id,
        "iscrizione": tmp_job.iscrizione_id or dati.get("iscrizione"),
        "username": dati.get("username"),
        "regione": None,
        "stato_iscrizione_errore": None,
        "fase": "lettura job",
    }


def log_errore_wordpress(contesto, errore):
    logger.error(
        "JobWordpress fallito job_id=%s iscrizione=%s username=%s regione=%s "
        "operazione=%s endpoint=%s status_http=%s motivo=%s",
        contesto["job_id"],
        contesto["iscrizione"],
        contesto["username"],
        contesto["regione"],
        errore.operazione,
        errore.endpoint,
        errore.status_http,
        errore.motivo,
    )


def marca_job_wordpress_fallito(session, contesto, motivo):
    try:
        tmp_job = session.get(JobWordpress, contesto["job_id"])
        if tmp_job:
            tmp_job.stato = "FAILED"
            tmp_job.updated_at = datetime.now()
            tmp_job.last_error = motivo
        if contesto["iscrizione"] and contesto["stato_iscrizione_errore"]:
            tmp_iscrizione = session.get(IscrizioneEG, contesto["iscrizione"])
            if tmp_iscrizione:
                tmp_iscrizione.stato = contesto["stato_iscrizione_errore"]
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(
            "Impossibile persistere il fallimento JobWordpress job_id=%s "
            "iscrizione=%s username=%s regione=%s motivo=%s",
            contesto["job_id"],
            contesto["iscrizione"],
            contesto["username"],
            contesto["regione"],
            type(exc).__name__,
        )


def processa_job_crea_squadriglia(session, tmp_job, header, contesto):
    if not isinstance(tmp_job.dati, dict):
        raise ValueError("dati job non validi")

    id_iscrizione = tmp_job.dati.get("iscrizione")
    tmp_iscrizione = session.get(IscrizioneEG, id_iscrizione)
    if not tmp_iscrizione:
        raise ValueError("iscrizione non trovata")

    contesto["regione"] = tmp_iscrizione.regione
    contesto["stato_iscrizione_errore"] = "failed_user"
    contesto["fase"] = "creazione utente"
    tmp_iscrizione.stato = "in_abilitazione"
    session.commit()

    wordpress_user = session.query(WordpressUser).filter_by(
        iscrizioni_id=id_iscrizione
    ).first()
    if wordpress_user:
        id_autore = wordpress_user.wordpress_id
        tmp_passwd = wordpress_user.password
    else:
        tmp_passwd = genera_password_sq()
        dati_utente = {
            "username": tmp_job.dati["username"],
            "name": tmp_iscrizione.nome.capitalize(),
            "email": f"{tmp_job.dati['username']}@guidonciniverdi.it",
            "password": tmp_passwd,
            "roles": ["author"],
            "meta": tmp_job.dati["meta"],
        }
        id_autore = crea_utente(
            session, id_iscrizione, header, dati_utente
        )

    contesto["stato_iscrizione_errore"] = "failed_post"
    contesto["fase"] = "creazione post"
    wordpress_post = session.query(WordpressPost).filter_by(
        iscrizioni_id=id_iscrizione, tipo="posts"
    ).first()
    if wordpress_post:
        id_post = wordpress_post.wordpress_id
    else:
        template_post = session.query(SysOption).filter_by(
            key="TemplatePost"
        ).first()
        if not template_post:
            raise ValueError("TemplatePost non configurato")

        endpoint_template = f"/posts/{template_post.value}?context=edit"
        payload_template, status_template = richiesta_wordpress_json(
            "GET", endpoint_template, header, "lettura template post"
        )
        try:
            tmp_content = payload_template["content"]["raw"]
        except (KeyError, TypeError) as exc:
            raise WordpressRequestError(
                "lettura template post",
                endpoint_template,
                "risposta JSON inattesa: content.raw assente",
                status_http=status_template,
            ) from exc

        endpoint_specialita = "/specialita?per_page=100"
        specialita_wordpress, status_specialita = richiesta_wordpress_json(
            "GET", endpoint_specialita, header, "lettura specialita"
        )
        if not isinstance(specialita_wordpress, list):
            raise WordpressRequestError(
                "lettura specialita",
                endpoint_specialita,
                "risposta JSON inattesa: elenco specialita non valido",
                status_http=status_specialita,
            )
        tmp_specialita = {
            voce.get("name"): voce.get("id")
            for voce in specialita_wordpress
            if isinstance(voce, dict)
        }
        id_specialita = tmp_specialita.get(tmp_iscrizione.specialita.title())
        if not isinstance(id_specialita, int):
            raise WordpressRequestError(
                "lettura specialita",
                endpoint_specialita,
                "specialita richiesta non trovata",
                status_http=status_specialita,
            )

        endpoint_categorie = "/categories?per_page=100"
        categorie_wordpress, status_categorie = richiesta_wordpress_json(
            "GET", endpoint_categorie, header, "lettura categorie"
        )
        if not isinstance(categorie_wordpress, list):
            raise WordpressRequestError(
                "lettura categorie",
                endpoint_categorie,
                "risposta JSON inattesa: elenco categorie non valido",
                status_http=status_categorie,
            )
        id_categoria = next(
            (
                voce.get("id")
                for voce in categorie_wordpress
                if isinstance(voce, dict) and voce.get("name") == "Pagina unica"
            ),
            None,
        )
        if not isinstance(id_categoria, int):
            raise WordpressRequestError(
                "lettura categorie",
                endpoint_categorie,
                "categoria Pagina unica non trovata",
                status_http=status_categorie,
            )

        dati_post = {
            "author": int(id_autore),
            "categories": [id_categoria],
            "content": tmp_content,
            "meta": tmp_job.dati["meta"],
            "specialita": [id_specialita],
            "title": f"{tmp_job.dati['meta']['squadriglia']}",
            "status": "publish",
        }
        id_post = crea_post(
            session, id_iscrizione, int(id_autore), header, dati_post, "posts"
        )

    endpoint_post = f"/posts/{id_post}"
    payload_post, status_post = richiesta_wordpress_json(
        "GET", endpoint_post, header, "lettura post creato"
    )
    link_post = payload_post.get("link") if isinstance(payload_post, dict) else None
    if not isinstance(link_post, str) or not link_post:
        raise WordpressRequestError(
            "lettura post creato",
            endpoint_post,
            "risposta JSON inattesa: link assente",
            status_http=status_post,
        )

    testo_mail_sq = f"Congratulazioni {tmp_iscrizione.nome},<br>ecco le credenziali per il Diario di Bordo Digitale, potete accedere <a href=\"https://guidonciniverdi.it/wp-login.php\" target=\"_blank\">cliccando qui</a> oppure scaricando la app.<br><a href=\"https://play.google.com/store/apps/details?id=org.wordpress.android\" target=\"_blank\">Clicca qui per scaricare la app per Android</a><br><a href=\"https://apps.apple.com/it/app/wordpress-website-builder/id335703880\" target=\"_blank\">Clicca qui per scaricare la app per iOS</a><br>Trovate maggiori info qui: <a href=\"https://guidonciniverdi.it/come-funziona/\" target=\"_blank\">guidonciniverdi.it/come-funziona/</a><br><h4><strong>Credenziali</strong></h4>Username: {tmp_job.dati['username']}<br>Password: {tmp_passwd}"
    destinatari_mail = [tmp_iscrizione.mail]
    copia_mail = [tmp_iscrizione.mail_capo1, tmp_iscrizione.mail_capo2]
    regione_mail = tmp_iscrizione.regione

    tmp_job.stato = "DONE"
    tmp_job.updated_at = datetime.now()
    tmp_job.last_error = None
    tmp_iscrizione.link = link_post
    tmp_iscrizione.stato = "abilitato"
    session.commit()

    try:
        manda_mail(
            destinatari_mail,
            copia_mail,
            "Credenziali Diario di Bordo!",
            testo_mail_sq,
            regione_mail,
            anno=tmp_job.dati["meta"].get("anno"),
        )
    except Exception as exc:
        logger.error(
            "Accodamento mail fallito job_id=%s iscrizione=%s username=%s "
            "regione=%s motivo=%s",
            contesto["job_id"],
            contesto["iscrizione"],
            contesto["username"],
            contesto["regione"],
            type(exc).__name__,
        )


def meta_wordpress_iscrizione(session, iscrizione):
    gruppo = session.get(Gruppo, iscrizione.gruppo)
    zona = session.get(Zona, iscrizione.zona)
    regione = session.get(Regione, iscrizione.regione)
    percorso = session.get(StatusPercorso, iscrizione.anno_percorso)
    if not all([gruppo, zona, regione, percorso]):
        raise ValueError("dati territoriali o percorso non validi")
    return {
        "anno": percorso.anno,
        "gruppo": gruppo.gruppo.capitalize(),
        "rinnovo": iscrizione.tipo != "conquista",
        "specialita": iscrizione.specialita.title(),
        "squadriglia": iscrizione.nome.capitalize(),
        "regione": regione.regione.capitalize(),
        "zona": zona.zona.removeprefix("ZONA ").title(),
    }, gruppo, zona


def id_specialita_wordpress(header, nome_specialita):
    endpoint = "/specialita?per_page=100"
    elenco, status_http = richiesta_wordpress_json(
        "GET", endpoint, header, "lettura specialita"
    )
    if not isinstance(elenco, list):
        raise WordpressRequestError(
            "lettura specialita",
            endpoint,
            "risposta JSON inattesa: elenco specialita non valido",
            status_http=status_http,
        )
    id_specialita = next(
        (
            voce.get("id")
            for voce in elenco
            if isinstance(voce, dict) and voce.get("name") == nome_specialita
        ),
        None,
    )
    if not isinstance(id_specialita, int):
        raise WordpressRequestError(
            "lettura specialita",
            endpoint,
            "specialita richiesta non trovata",
            status_http=status_http,
        )
    return id_specialita


def processa_job_update_squadriglia(session, tmp_job, header, contesto):
    iscrizione = session.get(IscrizioneEG, tmp_job.iscrizione_id)
    if not iscrizione:
        raise ValueError("iscrizione non trovata")
    wordpress_user = session.query(WordpressUser).filter_by(
        iscrizioni_id=iscrizione.id
    ).first()
    wordpress_post = session.query(WordpressPost).filter_by(
        iscrizioni_id=iscrizione.id, tipo="posts"
    ).first()
    if not wordpress_user or not wordpress_post:
        raise WordpressRequestError(
            "aggiornamento risorse",
            "/users|/posts",
            "risorsa WordPress locale non presente",
        )

    contesto["regione"] = iscrizione.regione
    contesto["username"] = wordpress_user.username
    meta, gruppo, zona = meta_wordpress_iscrizione(session, iscrizione)
    contesto["fase"] = "aggiornamento utente"
    endpoint_utente = f"/users/{wordpress_user.wordpress_id}"
    payload_utente, status_utente = richiesta_wordpress_json(
        "POST",
        endpoint_utente,
        header,
        "aggiornamento utente",
        dati={"name": iscrizione.nome, "meta": meta},
    )
    id_utente = id_wordpress(
        payload_utente, "aggiornamento utente", endpoint_utente, status_utente
    )
    if id_utente != wordpress_user.wordpress_id:
        raise WordpressRequestError(
            "aggiornamento utente",
            endpoint_utente,
            "risposta JSON inattesa: id risorsa non corrispondente",
            status_http=status_utente,
        )

    contesto["fase"] = "aggiornamento post"
    id_specialita = id_specialita_wordpress(header, meta["specialita"])
    endpoint_post = f"/posts/{wordpress_post.wordpress_id}"
    dati_post = {
        "title": iscrizione.nome,
        "meta": meta,
        "specialita": [id_specialita],
    }
    payload_post, status_post = richiesta_wordpress_json(
        "POST", endpoint_post, header, "aggiornamento post", dati=dati_post
    )
    id_post = id_wordpress(
        payload_post, "aggiornamento post", endpoint_post, status_post
    )
    if id_post != wordpress_post.wordpress_id:
        raise WordpressRequestError(
            "aggiornamento post",
            endpoint_post,
            "risposta JSON inattesa: id risorsa non corrispondente",
            status_http=status_post,
        )

    dati_utente_locali = dict(wordpress_user.meta or {})
    dati_utente_locali["name"] = iscrizione.nome
    dati_utente_locali["meta"] = meta
    wordpress_user.meta = dati_utente_locali
    dati_post_locali = dict(wordpress_post.meta or {})
    dati_post_locali.update(dati_post)
    wordpress_post.meta = dati_post_locali
    tmp_job.stato = "DONE"
    tmp_job.updated_at = datetime.now()
    tmp_job.last_error = None
    session.commit()

    try:
        regione = session.get(Regione, iscrizione.regione)
        percorso = session.get(StatusPercorso, iscrizione.anno_percorso)
        riepilogo = genera_mail_riepilogo_iscrizione(
            iscrizione,
            regione,
            zona,
            gruppo,
            percorso,
            wordpress_user=wordpress_user,
            operazione="modifica",
        )
        manda_mail(
            riepilogo["destinatari"],
            riepilogo["copia"],
            riepilogo["oggetto"],
            riepilogo["html"],
            iscrizione.regione,
            anno=riepilogo["anno"],
        )
    except Exception as exc:
        logger.error(
            "Accodamento mail aggiornamento fallito job_id=%s iscrizione=%s "
            "username=%s regione=%s motivo=%s",
            contesto["job_id"], contesto["iscrizione"], contesto["username"],
            contesto["regione"], type(exc).__name__,
        )


def processa_prossimo_job_wordpress(header, session_factory=Session):
    session = session_factory()
    contesto = None
    try:
        tmp_job = (
            session.query(JobWordpress)
            .filter_by(stato="PENDING")
            .order_by(JobWordpress.id)
            .first()
        )
        if not tmp_job:
            return False

        contesto = contesto_job_wordpress(tmp_job)
        tmp_job.stato = "SENDING"
        tmp_job.started_at = datetime.now()
        tmp_job.updated_at = tmp_job.started_at
        tmp_job.attempts = (tmp_job.attempts or 0) + 1
        tmp_job.last_error = None
        session.commit()

        if not isinstance(tmp_job.dati, dict):
            raise ValueError("payload job non valido")
        tipo_job = tmp_job.tipo or tmp_job.dati.get("tipo") or "crea_sq"
        if tipo_job == "crea_sq":
            contesto["stato_iscrizione_errore"] = "failed_user"
            processa_job_crea_squadriglia(session, tmp_job, header, contesto)
        elif tipo_job == "update_sq":
            processa_job_update_squadriglia(session, tmp_job, header, contesto)
        else:
            raise ValueError("tipo job non supportato")
        return True
    except WordpressRequestError as exc:
        session.rollback()
        log_errore_wordpress(contesto, exc)
        marca_job_wordpress_fallito(session, contesto, exc.motivo)
        return True
    except Exception as exc:
        session.rollback()
        if contesto:
            logger.error(
                "JobWordpress fallito job_id=%s iscrizione=%s username=%s "
                "regione=%s operazione=%s motivo=eccezione inattesa %s",
                contesto["job_id"],
                contesto["iscrizione"],
                contesto["username"],
                contesto["regione"],
                contesto["fase"],
                type(exc).__name__,
            )
            marca_job_wordpress_fallito(
                session, contesto, f"eccezione inattesa {type(exc).__name__}"
            )
        else:
            logger.error(
                "Lettura coda JobWordpress fallita motivo=%s",
                type(exc).__name__,
            )
        return True
    finally:
        session.close()


def recupera_job_wordpress_stale(session_factory=Session, adesso=None):
    session = session_factory()
    adesso = adesso or datetime.now()
    soglia = adesso - JOB_STALE_AFTER
    try:
        stale = session.query(JobWordpress).filter(
            JobWordpress.stato == "SENDING",
            JobWordpress.updated_at < soglia,
        ).all()
        for job in stale:
            job.updated_at = adesso
            if (job.attempts or 0) < JOB_MAX_ATTEMPTS:
                job.stato = "PENDING"
                job.started_at = None
                job.last_error = "Job stale recuperato e riportato in coda"
                logger.warning(
                    "Recovery JobWordpress stale job_id=%s iscrizione=%s tipo=%s attempts=%s",
                    job.id, job.iscrizione_id, job.tipo, job.attempts,
                )
            else:
                job.stato = "FAILED"
                job.last_error = "Job stale: numero massimo di tentativi raggiunto"
                if job.tipo == "crea_sq" and job.iscrizione_id:
                    iscrizione = session.get(IscrizioneEG, job.iscrizione_id)
                    if iscrizione and iscrizione.stato == "in_abilitazione":
                        wordpress_user = session.query(WordpressUser).filter_by(
                            iscrizioni_id=iscrizione.id
                        ).first()
                        iscrizione.stato = (
                            "failed_post" if wordpress_user else "failed_user"
                        )
                logger.error(
                    "JobWordpress stale fallito job_id=%s iscrizione=%s tipo=%s attempts=%s",
                    job.id, job.iscrizione_id, job.tipo, job.attempts,
                )

        iscrizioni_in_corso = session.query(IscrizioneEG).filter_by(
            stato="in_abilitazione"
        ).all()
        for iscrizione in iscrizioni_in_corso:
            job_attivo = session.query(JobWordpress).filter(
                JobWordpress.iscrizione_id == iscrizione.id,
                JobWordpress.stato.in_(["PENDING", "SENDING"]),
            ).first()
            if not job_attivo:
                logger.error(
                    "Iscrizione in_abilitazione senza job attivo iscrizione=%s regione=%s",
                    iscrizione.id, iscrizione.regione,
                )
        session.commit()
        return len(stale)
    except Exception as exc:
        session.rollback()
        logger.error("Recovery JobWordpress stale fallito motivo=%s", type(exc).__name__)
        return 0
    finally:
        session.close()


def job_wordpress():
    def task():
        scheduler = schedule.Scheduler()
        creds = f"{os.environ['WORDPRESS_USER']}:{os.environ['WORDPRESS_PASSWORD']}"
        token = base64.b64encode(creds.encode())
        header = {"Authorization": f"Basic {token.decode('utf-8')}"}
        recupera_job_wordpress_stale()

        scheduler.every(10).seconds.do(
            processa_prossimo_job_wordpress, header
        )
        scheduler.every(1).minutes.do(recupera_job_wordpress_stale)

        global demone_wordpress
        while demone_wordpress:
            scheduler.run_pending()
            sleep(1)
    threading.Thread(target=task, name="job_wordpress", daemon=True).start()

def main():
    global demone_mail, demone_telegram, demone_notifiche, demone_wordpress
    while True:
        session = Session()
        demoni = {d.key: d.value for d in session.query(Demone).all()}
        session.close()
        demone_mail = demoni["send_mail"]
        demone_telegram = demoni["send_telegram"]
        demone_notifiche = demoni["send_notifiche"]
        demone_wordpress = demoni["job_wordpress"]
        mail_seen = False
        telegram_seen = False
        notifiche_seen = False
        wordpress_seen = False
        for thread in threading.enumerate():
            if thread.name == "send_mail":
                mail_seen = True
            if thread.name == "send_telegram":
                telegram_seen = True
            if thread.name == "send_notifiche":
                notifiche_seen = True
            if thread.name == "job_wordpress":
                wordpress_seen = True
        if demone_mail and not mail_seen:
            send_mail()
        if demone_telegram and not telegram_seen:
            send_telegram()
        if demone_notifiche and not notifiche_seen:
            send_notifiche()
        if demone_wordpress and not wordpress_seen:
            job_wordpress()
        sleep(30)


if __name__ == "__main__":
    main()
