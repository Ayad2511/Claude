"""
Email verzender met Resend HTTP API (werkt op Railway).

Resend gebruikt HTTPS (poort 443) in plaats van SMTP (465/587),
waardoor Railway het niet blokkeert.

Setup:
  1. Maak account aan op resend.com
  2. Voeg je domein toe en verifieer het (DNS records)
  3. Maak een API key aan
  4. Zet RESEND_API_KEY in Railway variables
  5. Zet GMAIL_ADDRESS als from-adres (moet geverifieerd domein zijn in Resend)
"""

import asyncio
import re

import httpx

import database
from config import settings

RESEND_API_URL = "https://api.resend.com/emails"


def _html_to_plain(html_body: str) -> str:
    """Simpele HTML → plain text conversie voor het tekst-alternatief."""
    text = re.sub(r"<(style|script)[^>]*>.*?</(style|script)>", "", html_body, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    lead_id: int | None = None,
    template_key: str = "onbekend",
) -> bool:
    """
    Verstuur een email via Resend HTTP API.

    Als dry_run=True: log de email maar verstuur niet.
    Als lead_id opgegeven: registreer resultaat in outreach_log.

    Geeft True bij succes, False bij fout.
    """
    if settings.outreach_dry_run:
        print(f"[Email DRY-RUN] Aan: {to_email} | Onderwerp: {subject}")
        if lead_id:
            await database.log_outreach(lead_id, "email", template_key, True, "dry-run")
        return True

    if not settings.resend_api_key:
        print(f"[Email] FOUT: RESEND_API_KEY niet ingesteld")
        if lead_id:
            await database.log_outreach(lead_id, "email", template_key, False, "RESEND_API_KEY ontbreekt")
        return False

    if not settings.gmail_address:
        print(f"[Email] FOUT: GMAIL_ADDRESS niet ingesteld (gebruikt als from-adres)")
        return False

    from_address = f"{settings.sender_name} <{settings.gmail_address}>" if settings.sender_name else settings.gmail_address

    reply_to = settings.reply_to_email or settings.gmail_address

    payload = {
        "from": from_address,
        "to": [to_email],
        "reply_to": reply_to,
        "subject": subject,
        "html": html_body,
        "text": _html_to_plain(html_body),
        "headers": {
            "List-Unsubscribe": f"<mailto:{reply_to}?subject=uitschrijven>",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                RESEND_API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code in (200, 201):
            print(f"[Email] Verstuurd naar {to_email} | Onderwerp: {subject}")
            if lead_id:
                await database.log_outreach(lead_id, "email", template_key, True)
            return True
        else:
            error = f"Resend fout {resp.status_code}: {resp.text[:200]}"
            print(f"[Email] FOUT naar {to_email}: {error}")
            if lead_id:
                await database.log_outreach(lead_id, "email", template_key, False, error)
            return False

    except Exception as e:
        error = f"Onverwachte fout: {e}"
        print(f"[Email] FOUT naar {to_email}: {error}")
        if lead_id:
            await database.log_outreach(lead_id, "email", template_key, False, error)
        return False
