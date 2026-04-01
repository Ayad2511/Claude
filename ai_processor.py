"""
AI verwerking van gespreksopnames:
1. Whisper  → transcriptie van het audiobestand
2. Claude   → notitie genereren + lead categoriseren
"""

import io
import anthropic
from openai import AsyncOpenAI
from config import settings

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
claude_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def transcribe_audio(audio_bytes: bytes, filename: str = "recording.mp3") -> str:
    """
    Transcribeer het audiobestand met OpenAI Whisper.
    Geeft de volledige transcriptie terug als tekst.
    """
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename

    response = await openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="nl",  # Nederlands; pas aan als gesprekken in andere talen zijn
        response_format="text",
    )
    return response


SYSTEM_PROMPT = """Je bent een AI-assistent die verkoopgesprekken analyseert voor een Nederlands bedrijf.

Je taak:
1. Maak een beknopte notitie van het gesprek (max 200 woorden)
2. Categoriseer de lead in één van deze vijf vakjes:

   - geen_fit_geen_interesse  → Contact is geen ICP én heeft geen interesse
   - icp_geen_fit             → Contact is een ICP-profiel, maar is geen goede fit (bijv. verkeerde situatie, budget, timing)
   - icp_geen_interesse       → Contact is een ICP-profiel, maar heeft nu geen interesse
   - icp_niet_warm            → Contact is een ICP-profiel, heeft interesse, maar is nog niet warm genoeg
   - icp_gepland              → Contact is een ICP-profiel en er is een afspraak of vervolgstap ingepland

Geef je antwoord ALTIJD in dit exacte JSON-formaat:
{
  "notitie": "Korte samenvatting van het gesprek...",
  "categorie": "icp_gepland",
  "reden": "Waarom je deze categorie hebt gekozen..."
}

Gebruik alleen één van de vijf categorienamen hierboven, exact zoals geschreven."""


def analyze_transcript(transcript: str, contact_name: str = "") -> dict:
    """
    Analyseer de transcriptie met Claude en geef een notitie + categorie terug.
    Geeft een dict terug met: notitie, categorie, reden.
    """
    user_message = f"Analyseer dit verkoopgesprek:\n\n"
    if contact_name:
        user_message += f"Contact: {contact_name}\n\n"
    user_message += f"Transcriptie:\n{transcript}"

    response = claude_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    # Haal de tekstinhoud op uit het antwoord
    text_content = next(
        (block.text for block in response.content if hasattr(block, "text")),
        "",
    )

    # Parseer de JSON uit het antwoord
    import json
    import re

    # Zoek JSON-blok in de response (Claude kan soms extra tekst toevoegen)
    json_match = re.search(r"\{.*\}", text_content, re.DOTALL)
    if not json_match:
        raise ValueError(f"Geen geldig JSON-antwoord van Claude: {text_content}")

    result = json.loads(json_match.group())

    valid_categories = {
        "geen_fit_geen_interesse",
        "icp_geen_fit",
        "icp_geen_interesse",
        "icp_niet_warm",
        "icp_gepland",
    }
    if result.get("categorie") not in valid_categories:
        raise ValueError(f"Ongeldige categorie van Claude: {result.get('categorie')}")

    return result


def format_note(analysis: dict, transcript: str) -> str:
    """Formatteer de volledige notitie die in GHL wordt geplaatst."""
    category_labels = {
        "geen_fit_geen_interesse": "🔴 Geen fit & geen interesse",
        "icp_geen_fit": "🟠 ICP maar geen fit",
        "icp_geen_interesse": "🟡 ICP met geen interesse",
        "icp_niet_warm": "🔵 ICP - niet warm genoeg",
        "icp_gepland": "🟢 ICP - Gepland/Ingeboekt",
    }

    label = category_labels.get(analysis["categorie"], analysis["categorie"])

    note = f"""📞 AUTOMATISCHE GESPREKSNOTITIE
{'='*40}
Status: {label}

📝 Samenvatting:
{analysis['notitie']}

💡 Reden categorisering:
{analysis['reden']}

{'='*40}
📄 Volledige transcriptie:
{transcript}
"""
    return note
