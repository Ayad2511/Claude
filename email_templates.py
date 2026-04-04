"""
Email- en LinkedIn-templates voor de outreach sequentie.

Toon: ondernemer → ondernemer. Nooit sollicitant-taal.
Positionering: senior high-ticket closer als resultaatgerichte partner.

Alle templates zijn geschreven in het Nederlands tenzij de lead
in een Engelstalig land zit (te detecteren via het domein).

Claude AI personaliseert elke email op naam, bedrijf en niche.
Bij API-fout of ontbrekende data: fallback op basis-template.
"""

import json
import re

import anthropic
from config import settings

_claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ─────────────────────────────────────────────────────────────
# GEMEENSCHAPPELIJKE FOOTER (deliverability vereiste)
# ─────────────────────────────────────────────────────────────
def _footer() -> str:
    return f"""
<p style="margin-top:32px;font-size:11px;color:#aaaaaa;border-top:1px solid #eeeeee;padding-top:12px;">
  Je ontvangt dit bericht omdat jouw bedrijf actief is in de high-ticket markt.<br>
  Geen interesse?
  <a href="mailto:{settings.gmail_address}?subject=uitschrijven"
     style="color:#aaaaaa;">Klik hier om uit te schrijven</a>.
</p>
"""


# ─────────────────────────────────────────────────────────────
# LOOM VIDEO BLOK (thumbnail + hyperlink)
# ─────────────────────────────────────────────────────────────
def _loom_block() -> str:
    if not settings.loom_video_url:
        return ""
    if settings.loom_thumbnail_url:
        return f"""
<p>
  <a href="{settings.loom_video_url}" target="_blank">
    <img src="{settings.loom_thumbnail_url}"
         alt="▶ Bekijk mijn introductie (3 min)"
         width="480"
         style="border-radius:8px;border:2px solid #eeeeee;max-width:100%;">
  </a><br>
  <span style="font-size:12px;color:#888888;">
    👆 Klik op de afbeelding om de video te bekijken (3 min)
  </span>
</p>
"""
    # Alleen hyperlink als er geen thumbnail is
    return f"""
<p>
  📹 <a href="{settings.loom_video_url}" target="_blank">Bekijk mijn introductievideo (3 min)</a>
</p>
"""


def _loom_link() -> str:
    """Compacte hyperlink voor follow-up emails."""
    if not settings.loom_video_url:
        return ""
    return (
        f'<a href="{settings.loom_video_url}" target="_blank">'
        "mijn introductievideo</a>"
    )


# ─────────────────────────────────────────────────────────────
# EMAIL TEMPLATES (basis — worden door Claude verbeterd)
# ─────────────────────────────────────────────────────────────
TEMPLATES: dict[str, dict] = {
    "initial": {
        "subject": "Idee voor meer betalende klanten bij {company_name}",
        "html_body": """<p>Hi {first_name},</p>

<p>Ik zag jullie {niche}-aanbod en had direct een concreet idee over hoe
jullie conversieratio omhoog kan — zonder meer advertentiebudget.</p>

{loom_block}

<p>In bovenstaande video leg ik in 3 minuten uit hoe ik voor vergelijkbare
bedrijven 10–30% meer closes haal op dezelfde gesprekken.</p>

<p>Zou je open staan voor een kort gesprek om te kijken of dit voor
{company_name} ook werkt?</p>

<p>
  Met vriendelijke groet,<br>
  <strong>{sender_name}</strong>
</p>
{footer}""",
    },
    "followup_1": {
        "subject": "Re: Idee voor meer betalende klanten bij {company_name}",
        "html_body": """<p>Hi {first_name},</p>

<p>Ik stuurde je vorige week een berichtje over het verhogen van jullie
sluitingsratio bij {company_name}.</p>

<p>Heb je {loom_link} al kunnen bekijken? Daarin laat ik in 3 minuten
zien wat ik bedoel.</p>

<p>Mochten er vragen zijn of wil je even sparren — laat het me weten.</p>

<p>
  Met vriendelijke groet,<br>
  <strong>{sender_name}</strong>
</p>
{footer}""",
    },
    "followup_2": {
        "subject": "Wat ik voor een vergelijkbaar {niche} bedrijf deed",
        "html_body": """<p>Hi {first_name},</p>

<p>Ik heb recentelijk samengewerkt met een {niche} business die vergelijkbaar
is met {company_name}. Ze hadden kwalitatief goede leads maar haalden
niet het maximale eruit in de gesprekken.</p>

<p>Na twee weken samenwerken stegen hun closes met 23% — zonder
één extra euro aan advertenties.</p>

<p>Dat soort resultaat is precies wat ik ook voor jou zou willen bereiken.</p>

<p>Is dat de moeite van een gesprekje van 20 minuten?</p>

<p>
  Met vriendelijke groet,<br>
  <strong>{sender_name}</strong><br>
  <small>P.S. {loom_link} laat dit in detail zien.</small>
</p>
{footer}""",
    },
    "followup_3": {
        "subject": "Nog 1 plek vrij voor samenwerking",
        "html_body": """<p>Hi {first_name},</p>

<p>Ik neem contact op omdat ik vanaf volgende maand ruimte heb voor
precies één nieuwe samenwerkingspartner.</p>

<p>Ik werk liever met één bedrijf intensief dan met tien oppervlakkig —
dat levert betere resultaten op voor beide partijen.</p>

<p>Op basis van wat ik zie bij {company_name} denk ik dat er echt
potentieel ligt. Maar uiteraard wil ik dit samen met jou beoordelen
voor we beslissingen nemen.</p>

<p>Heb je deze week nog 20 minuten?</p>

<p>
  Met vriendelijke groet,<br>
  <strong>{sender_name}</strong>
</p>
{footer}""",
    },
    "followup_4": {
        "subject": "Afsluiter van mijn kant",
        "html_body": """<p>Hi {first_name},</p>

<p>Dit is mijn laatste berichtje.</p>

<p>Als de timing nu niet goed is of als jullie de sales intern houden —
geen probleem, ik snap het volkomen.</p>

<p>Mocht er in de toekomst interesse zijn in een samenwerking, weet dan
dat je altijd welkom bent om contact op te nemen.</p>

<p>Succes met {company_name}, ik volg jullie groei graag van een afstandje.</p>

<p>
  Met vriendelijke groet,<br>
  <strong>{sender_name}</strong>
</p>
{footer}""",
    },
}

# ─────────────────────────────────────────────────────────────
# LINKEDIN TEMPLATES (max 300 tekens voor connectieverzoek)
# ─────────────────────────────────────────────────────────────
LINKEDIN_TEMPLATES: dict[str, str] = {
    "connection": (
        "Hi {first_name}, ik zag jullie {niche}-aanbod en heb een concreet idee "
        "over hoe jullie sluitingsratio omhoog kan. Graag in verbinding — "
        "{sender_name}"
    ),
    "followup_dm": (
        "Hi {first_name}, ik stuurde je ook een email over het verhogen van "
        "jullie conversieratio bij {company_name}. Heb je er even naar kunnen "
        "kijken? Graag sparren als je dat wilt."
    ),
}


# ─────────────────────────────────────────────────────────────
# TEMPLATE OPVULLEN (basis)
# ─────────────────────────────────────────────────────────────
def _fill_template(template: dict, lead: dict) -> dict:
    """Vul de basis-template in met lead-gegevens (geen AI)."""
    vars_ = {
        "first_name": lead.get("first_name") or "daar",
        "last_name": lead.get("last_name") or "",
        "company_name": lead.get("company_name") or "jouw bedrijf",
        "niche": lead.get("niche") or "high-ticket",
        "sender_name": settings.sender_name or "Ahmed",
        "loom_block": _loom_block(),
        "loom_link": _loom_link() or "mijn introductievideo",
        "footer": _footer(),
    }
    subject = template["subject"].format(**vars_)
    html_body = template["html_body"].format(**vars_)
    return {"subject": subject, "html_body": html_body}


# ─────────────────────────────────────────────────────────────
# AI PERSONALISATIE
# ─────────────────────────────────────────────────────────────
async def personalize_email(template_key: str, lead: dict) -> dict:
    """
    Personaliseer een emailtemplate met Claude AI.
    Fallback op basis-template bij fout of ontbrekende gegevens.

    Retourneert: {"subject": str, "html_body": str}
    """
    template = TEMPLATES.get(template_key)
    if not template:
        raise ValueError(f"Onbekende template key: {template_key}")

    base = _fill_template(template, lead)

    # Alleen AI personaliseren als er voldoende lead-info is
    first_name = lead.get("first_name", "")
    company = lead.get("company_name", "")
    niche = lead.get("niche", "")
    if not first_name or not company:
        return base

    system_prompt = (
        "Je bent een senior high-ticket closer die zichzelf positioneert als "
        "zakelijke partner — niet als sollicitant. Je schrijft korte, zakelijke "
        "emails in het Nederlands die conversiegericht zijn. Gebruik nooit "
        "slijmerige verkooptaal. Klink als een zelfverzekerde ondernemer die "
        "waarde biedt, niet vraagt."
    )

    user_prompt = f"""Herschrijf de onderstaande email zodat deze maximaal persoonlijk aanvoelt
voor deze prospect:

Naam: {first_name} {lead.get("last_name", "")}
Bedrijf: {company}
Niche: {niche or "high-ticket coaching/training"}
Website: {lead.get("website", "onbekend")}

BASIS EMAIL:
Onderwerp: {base["subject"]}

{base["html_body"]}

INSTRUCTIES:
- Verander de opener zodat die specifiek verwijst naar iets van hun bedrijf/niche
- Houd de HTML-structuur intact (p-tags, loom-blok, footer)
- Pas de onderwerpregel aan zodat die intrigeert maar niet clickbait-achtig is
- Maximaal 150 woorden in de body (exclusief footer)
- Geef ALLEEN geldig JSON terug in dit formaat:
{{"subject": "...", "html_body": "..."}}"""

    try:
        response = _claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text.strip()
        # Extraheer JSON (Claude geeft soms extra tekst terug)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            if "subject" in data and "html_body" in data:
                return data
    except Exception as e:
        print(f"[Templates] AI personalisatie mislukt, gebruik basis-template: {e}")

    return base


async def personalize_linkedin(template_key: str, lead: dict) -> str:
    """
    Geef een ingevuld LinkedIn bericht terug (max 300 tekens voor connectie).
    Geen AI personalisatie om rate limits te vermijden.
    """
    template = LINKEDIN_TEMPLATES.get(template_key, "")
    if not template:
        return ""

    first_name = lead.get("first_name") or "daar"
    company = lead.get("company_name") or "jullie bedrijf"
    niche = lead.get("niche") or "high-ticket"

    msg = template.format(
        first_name=first_name,
        company_name=company,
        niche=niche,
        sender_name=settings.sender_name or "Ahmed",
    )

    # Zorg dat connectieverzoeken onder 300 tekens blijven
    if template_key == "connection" and len(msg) > 295:
        msg = msg[:292] + "..."

    return msg
