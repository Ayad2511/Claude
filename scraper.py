"""
Lead scraper: haalt contactinfo op via Google en LinkedIn.

Strategie:
  1. Stuur Google-zoekopdrachten voor high-ticket bedrijven in NL
  2. Bezoek gevonden websites → zoek email en LinkedIn URL
  3. Zoek aanvullend via LinkedIn profiel-search
  4. Valideer emaildomeinen via MX record check
  5. Sla nieuwe leads op in SQLite (duplicaten worden genegeerd)

Geen gebruik van betaalde scraping tools of GHL.
"""

import asyncio
import re
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

import database
import linkedin_client
from config import settings

# ─────────────────────────────────────────────────────────────
# ZOEKOPDRACHTEN
# ─────────────────────────────────────────────────────────────
GOOGLE_QUERIES = [
    "high ticket coaching programma Nederland",
    "online business coaching programma €5000",
    "high ticket sales funnel masterclass site:.nl",
    "online training ondernemerschap aanmelden NL",
    "high ticket closer werving samenwerking Nederland",
    "business coaching hoge omzet programma oprichter",
    "mindset coaching premium programma founder NL",
    "online sales coach high end aanbod nederland",
]

LINKEDIN_SEARCH_QUERIES = [
    "high ticket coach founder CEO Nederland",
    "online business coach oprichter nederland",
    "sales trainer entrepreneur netherlands",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}


# ─────────────────────────────────────────────────────────────
# EMAIL DOMEIN VALIDATIE (MX record check)
# ─────────────────────────────────────────────────────────────
def _is_valid_email_domain(email: str) -> bool:
    """
    Controleer of het domein een MX record heeft.
    Filtert nep/inactieve domeinen eruit vóór opslag.
    """
    try:
        import dns.resolver  # type: ignore
        domain = email.split("@")[-1]
        dns.resolver.resolve(domain, "MX", lifetime=5.0)
        return True
    except Exception:
        return False


def _looks_like_email(text: str) -> bool:
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))


# ─────────────────────────────────────────────────────────────
# GOOGLE SCRAPER
# ─────────────────────────────────────────────────────────────
async def scrape_google(query: str, num: int = 10) -> list[str]:
    """
    Haal organische Google-resultaten op voor een zoekopdracht.
    Geeft een lijst van URLs terug (geen advertenties).
    """
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&hl=nl"
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"[Scraper] Google geeft {resp.status_code} voor: {query[:50]}")
                return []

        soup = BeautifulSoup(resp.text, "lxml")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Google wraps organische links in /url?q=...
            if href.startswith("/url?q="):
                actual = href[7:].split("&")[0]
                parsed = urlparse(actual)
                # Filter Google's eigen domeinen en advertentie-links
                if parsed.scheme in ("http", "https") and "google" not in parsed.netloc:
                    urls.append(actual)
        return list(dict.fromkeys(urls))[:num]  # Dedupliceren + limiet

    except Exception as e:
        print(f"[Scraper] Google fout voor '{query[:40]}': {e}")
        return []


# ─────────────────────────────────────────────────────────────
# WEBSITE ANALYSE
# ─────────────────────────────────────────────────────────────
async def extract_from_website(url: str) -> dict:
    """
    Bezoek een website en extraheer:
    - email (mailto: links)
    - linkedin_url (/in/ of /company/ links)
    - company_name (title of h1)
    - website

    Geeft een dict terug, leeg als de site niet bereikbaar is.
    """
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}

        soup = BeautifulSoup(resp.text, "lxml")

        # Email: zoek mailto: links
        email = ""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("mailto:"):
                candidate = href[7:].split("?")[0].strip()
                if _looks_like_email(candidate):
                    # Sla info@, contact@, support@ e.d. over als er betere zijn
                    if not email or email.startswith(("info@", "contact@", "support@", "hallo@", "hello@")):
                        email = candidate

        # Email ook zoeken in platte tekst (regex)
        if not email:
            text = soup.get_text()
            matches = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
            for m in matches:
                if _looks_like_email(m) and "example" not in m:
                    email = m
                    break

        # LinkedIn URL
        linkedin_url = ""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "linkedin.com/in/" in href or "linkedin.com/company/" in href:
                linkedin_url = href.split("?")[0]
                break

        # Bedrijfsnaam
        company_name = ""
        title_tag = soup.find("title")
        if title_tag:
            company_name = title_tag.get_text(strip=True).split("|")[0].split("-")[0].strip()
        if not company_name:
            h1 = soup.find("h1")
            if h1:
                company_name = h1.get_text(strip=True)

        if not email:
            return {}

        return {
            "email": email.lower(),
            "linkedin_url": linkedin_url,
            "company_name": company_name[:100],
            "website": url,
            "source": "google",
        }

    except Exception as e:
        print(f"[Scraper] Websiteanalyse mislukt voor {url}: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# HOOFD SCRAPE JOB
# ─────────────────────────────────────────────────────────────
async def run_scrape_job(max_new_leads: int | None = None) -> dict:
    """
    Voer een volledige scrape-run uit:
    1. Google → websites → email + LinkedIn URL
    2. LinkedIn profiel-search
    3. Dedupliceren op email + MX validatie
    4. Opslaan in SQLite

    Geeft stats terug: {"nieuw", "duplicaat", "geen_email", "ongeldig_domein"}
    """
    limit = max_new_leads or settings.scrape_max_leads_per_run
    stats = {"nieuw": 0, "duplicaat": 0, "geen_email": 0, "ongeldig_domein": 0}
    candidates: list[dict] = []

    # ── 1. Google scraping ──────────────────────────────────
    for query in GOOGLE_QUERIES:
        if stats["nieuw"] >= limit:
            break
        print(f"[Scraper] Google: {query[:60]}")
        urls = await scrape_google(query, num=10)
        await asyncio.sleep(3)  # Vriendelijk voor Google

        for url in urls:
            if stats["nieuw"] >= limit:
                break
            data = await extract_from_website(url)
            if data:
                candidates.append(data)
            await asyncio.sleep(1)

    # ── 2. LinkedIn profiel-search ──────────────────────────
    for query in LINKEDIN_SEARCH_QUERIES:
        if stats["nieuw"] >= limit:
            break
        print(f"[Scraper] LinkedIn search: {query}")
        li_leads = await linkedin_client.search_high_ticket_people(keywords=query, limit=20)
        for person in li_leads:
            # LinkedIn-leads hebben geen direct email; sla op als partial lead
            if person.get("linkedin_id"):
                candidates.append(person)
        await asyncio.sleep(5)

    # ── 3. Dedupliceren en opslaan ──────────────────────────
    seen_emails: set[str] = set()
    for lead in candidates:
        email = lead.get("email", "").lower().strip()

        # LinkedIn-leads zonder email: sla op met placeholder
        if not email and lead.get("linkedin_id"):
            # Gebruik linkedin_id als tijdelijke email-sleutel
            placeholder = f"{lead['linkedin_id']}@linkedin.placeholder"
            lead["email"] = placeholder
            email = placeholder
            lead["source"] = "linkedin"

        if not email:
            stats["geen_email"] += 1
            continue

        if email in seen_emails:
            continue
        seen_emails.add(email)

        # MX validatie (sla placeholder-emails over)
        if not email.endswith("@linkedin.placeholder"):
            if not _is_valid_email_domain(email):
                print(f"[Scraper] Ongeldig domein overgeslagen: {email}")
                stats["ongeldig_domein"] += 1
                continue

        new_id = await database.create_lead(lead)
        if new_id:
            stats["nieuw"] += 1
            print(f"[Scraper] Nieuwe lead opgeslagen: {email} ({lead.get('company_name', '')})")
        else:
            stats["duplicaat"] += 1

    print(
        f"[Scraper] Klaar — nieuw: {stats['nieuw']}, "
        f"duplicaat: {stats['duplicaat']}, "
        f"geen email: {stats['geen_email']}, "
        f"ongeldig domein: {stats['ongeldig_domein']}"
    )
    return stats
