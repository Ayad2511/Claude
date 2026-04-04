"""
Lead scraper: haalt contactinfo op via Google en LinkedIn.

Strategie:
  1. Stuur Google-zoekopdrachten voor high-ticket bedrijven in NL
  2. Bezoek gevonden websites + subpagina's → zoek ALLE emails + LinkedIn URL
  3. Detecteer rol per emailadres (ceo / sales / marketing / general)
  4. Zoek aanvullend via LinkedIn profiel-search
  5. Valideer emaildomeinen via MX record check
  6. Sla nieuwe leads op in SQLite (duplicaten worden genegeerd)

Geen gebruik van betaalde scraping tools of GHL.
"""

import asyncio
import re
from urllib.parse import quote_plus, urljoin, urlparse

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

# ─────────────────────────────────────────────────────────────
# MULTI-EMAIL CONFIGURATIE
# ─────────────────────────────────────────────────────────────
SUBPAGE_PATHS = [
    "/contact", "/contact-us", "/over-ons", "/about",
    "/team", "/over", "/mensen", "/contacteer-ons",
]

ROLE_MAP = {
    # CEO / oprichter
    "ceo": "ceo", "founder": "ceo", "oprichter": "ceo", "directeur": "ceo",
    "owner": "ceo", "eigenaar": "ceo",
    # Sales
    "sales": "sales", "verkoop": "sales", "closer": "sales",
    "acquisitie": "sales", "business": "sales",
    # Marketing
    "marketing": "marketing", "groei": "marketing", "growth": "marketing",
    "communicatie": "marketing",
    # General (info@ etc.)
    "info": "general", "contact": "general", "hallo": "general",
    "hello": "general", "support": "general", "help": "general",
    "post": "general", "mail": "general",
}

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


def _detect_role(email: str) -> str:
    """
    Bepaal de rol van een emailadres op basis van het prefix.
    Bijv. ceo@bedrijf.nl → 'ceo', sales@bedrijf.nl → 'sales'.
    Onbekende prefixen → 'general'.
    """
    prefix = email.split("@")[0].lower().strip()
    # Exacte match
    if prefix in ROLE_MAP:
        return ROLE_MAP[prefix]
    # Gedeeltelijke match (bijv. "sales.manager" bevat "sales")
    for keyword, role in ROLE_MAP.items():
        if keyword in prefix:
            return role
    return "general"


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
def _extract_emails_from_soup(soup: BeautifulSoup) -> set[str]:
    """Extraheer alle emailadressen uit een BeautifulSoup object."""
    found: set[str] = set()

    # mailto: links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            candidate = href[7:].split("?")[0].strip().lower()
            if _looks_like_email(candidate) and "example" not in candidate:
                found.add(candidate)

    # Regex in platte tekst
    text = soup.get_text()
    matches = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    for m in matches:
        m = m.lower()
        if _looks_like_email(m) and "example" not in m:
            found.add(m)

    return found


async def extract_all_emails_from_website(url: str) -> list[dict]:
    """
    Bezoek een website (homepage + subpagina's) en extraheer:
    - ALLE emailadressen met gedetecteerde rol
    - linkedin_url (eerste gevonden)
    - company_name (title of h1 van homepage)

    Geeft een lijst van dicts terug — één per uniek emailadres.
    Lege lijst als de site niet bereikbaar is of geen emails heeft.
    """
    base_domain = urlparse(url).scheme + "://" + urlparse(url).netloc
    all_emails: dict[str, str] = {}  # email → page_url
    linkedin_url = ""
    company_name = ""

    pages_to_visit = [url] + [base_domain + path for path in SUBPAGE_PATHS]

    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            for page_url in pages_to_visit:
                try:
                    resp = await client.get(page_url)
                    if resp.status_code != 200:
                        continue

                    soup = BeautifulSoup(resp.text, "lxml")

                    # Bedrijfsnaam + LinkedIn alleen van eerste (homepage)
                    if page_url == url:
                        title_tag = soup.find("title")
                        if title_tag:
                            company_name = (
                                title_tag.get_text(strip=True)
                                .split("|")[0].split("-")[0].strip()
                            )
                        if not company_name:
                            h1 = soup.find("h1")
                            if h1:
                                company_name = h1.get_text(strip=True)

                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            if "linkedin.com/in/" in href or "linkedin.com/company/" in href:
                                linkedin_url = href.split("?")[0]
                                break

                    # Emails van elke pagina
                    page_emails = _extract_emails_from_soup(soup)
                    for email in page_emails:
                        if email not in all_emails:
                            all_emails[email] = page_url

                    await asyncio.sleep(0.5)  # vriendelijk voor de server

                except Exception:
                    continue  # Subpagina niet bereikbaar — ga door

    except Exception as e:
        print(f"[Scraper] Websiteanalyse mislukt voor {url}: {e}")
        return []

    if not all_emails:
        return []

    results = []
    for email, _ in all_emails.items():
        role = _detect_role(email)
        results.append({
            "email": email,
            "role": role,
            "linkedin_url": linkedin_url,
            "company_name": company_name[:100],
            "website": url,
            "source": "google",
        })
        print(f"[Scraper] Email gevonden: {email} (role:{role}) — {company_name[:40]}")

    return results


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
        await asyncio.sleep(3)

        for url in urls:
            if stats["nieuw"] >= limit:
                break
            leads_from_site = await extract_all_emails_from_website(url)
            candidates.extend(leads_from_site)
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
