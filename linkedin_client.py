"""
LinkedIn outreach wrapper via de linkedin-api library (cookie-login).

Vereiste cookie:
  1. Open LinkedIn in een browser
  2. DevTools (F12) → Application → Cookies → www.linkedin.com
  3. Kopieer de waarde van "li_at"
  4. Sla op in .env als LINKEDIN_LI_AT=...

Limieten om ban te vermijden:
  - Max ~20 connectieverzoeken per dag
  - Min 30 seconden wachttijd tussen acties
  - Geen bulk DMs zonder eerst geconnect te zijn
"""

import asyncio
import functools

from config import settings

# Lazy import: alleen laden als LinkedIn geconfigureerd is
_linkedin_client = None


def get_client():
    """
    Geeft een gecachede LinkedIn client terug.
    Geeft None terug als LINKEDIN_LI_AT niet is ingesteld.
    """
    global _linkedin_client
    if _linkedin_client is not None:
        return _linkedin_client

    if not settings.linkedin_li_at:
        print("[LinkedIn] LINKEDIN_LI_AT niet ingesteld — LinkedIn outreach overgeslagen")
        return None

    try:
        from linkedin_api import Linkedin  # type: ignore
        _linkedin_client = Linkedin(
            "",
            "",
            cookies={"li_at": settings.linkedin_li_at},
        )
        print("[LinkedIn] Client aangemaakt via li_at cookie")
        return _linkedin_client
    except Exception as e:
        print(f"[LinkedIn] Kan client niet aanmaken: {e}")
        return None


async def send_connection_request(linkedin_id: str, message: str) -> bool:
    """
    Stuur een connectieverzoek naar een LinkedIn profiel.
    linkedin_id: publiek profiel ID (bijv. "john-doe-123")
    message: max 300 tekens
    """
    client = get_client()
    if not client:
        return False

    if settings.outreach_dry_run:
        print(f"[LinkedIn DRY-RUN] Connectieverzoek naar {linkedin_id}: {message[:60]}...")
        return True

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            functools.partial(client.add_connection, linkedin_id, message=message),
        )
        print(f"[LinkedIn] Connectieverzoek verstuurd naar {linkedin_id}")
        await asyncio.sleep(30)  # Wachttijd om ban te vermijden
        return True
    except Exception as e:
        print(f"[LinkedIn] Fout bij connectieverzoek naar {linkedin_id}: {e}")
        return False


async def send_message(linkedin_id: str, message: str) -> bool:
    """
    Stuur een DM naar een bestaande connectie.
    Werkt alleen als je al geconnect bent met de persoon.
    """
    client = get_client()
    if not client:
        return False

    if settings.outreach_dry_run:
        print(f"[LinkedIn DRY-RUN] DM naar {linkedin_id}: {message[:60]}...")
        return True

    try:
        loop = asyncio.get_event_loop()
        # linkedin-api gebruikt profile URN intern; zoek eerst het profiel op
        profile = await loop.run_in_executor(
            None, client.get_profile, linkedin_id
        )
        urn = profile.get("entityUrn", "")
        if not urn:
            print(f"[LinkedIn] Geen URN gevonden voor {linkedin_id}")
            return False

        await loop.run_in_executor(
            None,
            functools.partial(client.send_message, message_body=message, recipients=[urn]),
        )
        print(f"[LinkedIn] DM verstuurd naar {linkedin_id}")
        await asyncio.sleep(30)
        return True
    except Exception as e:
        print(f"[LinkedIn] Fout bij DM naar {linkedin_id}: {e}")
        return False


async def search_high_ticket_people(
    keywords: str = "high ticket coach founder CEO Nederland",
    limit: int = 20,
) -> list[dict]:
    """
    Zoek LinkedIn profielen van oprichters/CEO's in de high-ticket ruimte.

    Geeft lijst van dicts terug:
      {"first_name", "last_name", "linkedin_id", "company", "linkedin_url"}
    """
    client = get_client()
    if not client:
        return []

    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            functools.partial(
                client.search_people,
                keywords=keywords,
                network_depths=["S", "O"],
                limit=limit,
            ),
        )

        leads = []
        for person in results:
            public_id = person.get("public_id") or person.get("publicIdentifier", "")
            if not public_id:
                continue
            name = person.get("name") or ""
            parts = name.strip().split(" ", 1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""
            company = ""
            for pos in person.get("summary", {}).get("experience", []):
                company = pos.get("company", {}).get("name", "")
                if company:
                    break

            leads.append({
                "first_name": first_name,
                "last_name": last_name,
                "linkedin_id": public_id,
                "company_name": company,
                "linkedin_url": f"https://www.linkedin.com/in/{public_id}",
                "source": "linkedin",
            })

        print(f"[LinkedIn] {len(leads)} profielen gevonden voor: {keywords}")
        return leads

    except Exception as e:
        print(f"[LinkedIn] Zoekfout: {e}")
        return []
