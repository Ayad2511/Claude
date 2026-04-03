"""
Gmail SMTP email verzender met maximale deliverability.

Setup:
  1. Zet 2-stapsverificatie aan op je Google account
  2. Google Account → Beveiliging → App-wachtwoorden → Mail → genereer
  3. Sla het 16-cijferige wachtwoord op in GMAIL_APP_PASSWORD

Deliverability maatregelen ingebouwd:
  - Multipart email (HTML + plain text alternatief)
  - Correcte From/Reply-To/List-Unsubscribe headers
  - Bounce detectie en logging
  - 45-90 seconden delay na verzending (in outreach_pipeline.py)
"""

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import database
from config import settings


def _html_to_plain(html_body: str) -> str:
    """Simpele HTML → plain text conversie voor het tekst-alternatief."""
    import re
    # Verwijder style/script blokken
    text = re.sub(r"<(style|script)[^>]*>.*?</(style|script)>", "", html_body, flags=re.DOTALL | re.IGNORECASE)
    # Vervang <br> en <p> door newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    # Verwijder alle overige HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Normaliseer witruimte
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_message(to_email: str, subject: str, html_body: str) -> MIMEMultipart:
    """
    Bouw een volledig MIME bericht op met:
    - Correct From display name
    - Reply-To
    - List-Unsubscribe (GDPR/CAN-SPAM vereiste)
    - HTML + plain text alternatief
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.sender_name} <{settings.gmail_address}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = settings.gmail_address
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=settings.gmail_address.split("@")[-1])
    msg["List-Unsubscribe"] = (
        f"<mailto:{settings.gmail_address}?subject=uitschrijven>"
    )

    plain_text = _html_to_plain(html_body)
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    return msg


def _send_sync(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    """
    Synchrone SMTP verzending (wordt uitgevoerd in een thread executor).
    Geeft (True, "") bij succes, (False, foutmelding) bij fout.
    """
    if not settings.gmail_address or not settings.gmail_app_password:
        return False, "GMAIL_ADDRESS of GMAIL_APP_PASSWORD niet ingesteld"

    msg = _build_message(to_email, subject, html_body)
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(settings.gmail_address, settings.gmail_app_password)
            server.sendmail(
                settings.gmail_address,
                [to_email],
                msg.as_string(),
            )
        return True, ""
    except smtplib.SMTPRecipientsRefused as e:
        return False, f"Ongeldig emailadres (bounce): {e}"
    except smtplib.SMTPAuthenticationError as e:
        return False, f"Gmail authenticatie mislukt: {e}"
    except smtplib.SMTPException as e:
        return False, f"SMTP fout: {e}"
    except Exception as e:
        return False, f"Onverwachte fout: {e}"


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    lead_id: int | None = None,
    template_key: str = "onbekend",
) -> bool:
    """
    Verstuur een email asynchroon via Gmail SMTP.

    Als dry_run=True in config: log de email maar verstuur niet.
    Als lead_id opgegeven: registreer resultaat in outreach_log.

    Geeft True bij succes, False bij fout.
    """
    if settings.outreach_dry_run:
        print(f"[Email DRY-RUN] Aan: {to_email} | Onderwerp: {subject}")
        if lead_id:
            await database.log_outreach(lead_id, "email", template_key, True, "dry-run")
        return True

    loop = asyncio.get_event_loop()
    success, error = await loop.run_in_executor(
        None, _send_sync, to_email, subject, html_body
    )

    if success:
        print(f"[Email] Verstuurd naar {to_email} | Onderwerp: {subject}")
    else:
        print(f"[Email] FOUT naar {to_email}: {error}")

    if lead_id:
        await database.log_outreach(lead_id, "email", template_key, success, error)

    return success
