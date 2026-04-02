"""
AI verwerking van gespreksopnames:
1. Whisper  → transcriptie van het audiobestand
2. Claude   → notitie genereren + lead categoriseren + VSL-check
"""

import io
import json
import re
import anthropic
from openai import AsyncOpenAI
from config import settings

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
claude_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def transcribe_audio(audio_bytes: bytes, filename: str = "recording.mp3") -> str:
    """Transcribeer het audiobestand met OpenAI Whisper."""
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename

    response = await openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="nl",  # Pas aan als gesprekken in andere talen zijn
        response_format="text",
    )
    return response


SYSTEM_PROMPT = """Je bent een AI-assistent die verkoopgesprekken analyseert voor een Nederlands bedrijf.

Je taken:
1. Maak een KORTE samenvatting van het gesprek (max 3-4 zinnen)
2. Stel vast of de lead de VSL (video) heeft bekeken:
   - JA: de lead noemt de video, verwijst naar inhoud, of toont duidelijk voorkennis
   - NEE: de lead weet niet waar het over gaat, herinnert zich niets, of reageert alsof alles nieuw is
   - WAARSCHIJNLIJK JA / WAARSCHIJNLIJK NEE: als het niet duidelijk is, schat dan in op basis van hoe warm/geïnformeerd de lead is
3. Categoriseer de lead in één van deze vijf vakjes:
   - geen_fit_geen_interesse  → Contact is geen ICP én heeft geen interesse
   - icp_geen_fit             → Contact is een ICP-profiel, maar is geen goede fit (bijv. verkeerde situatie, budget, timing)
   - icp_geen_interesse       → Contact is een ICP-profiel, maar heeft nu geen interesse
   - icp_niet_warm            → Contact is een ICP-profiel, heeft interesse, maar is nog niet warm genoeg
   - icp_gepland              → Contact is een ICP-profiel en er is een afspraak of vervolgstap ingepland

Geef je antwoord ALTIJD in dit exacte JSON-formaat:
{
  "samenvatting": "Korte samenvatting in 3-4 zinnen...",
  "categorie": "icp_gepland",
  "reden": "Korte uitleg waarom dit vakje...",
  "vsl_bekeken": "ja",
  "vsl_toelichting": "Waarom je denkt dat de VSL wel/niet bekeken is..."
}

Voor vsl_bekeken gebruik je exact één van: "ja", "nee", "waarschijnlijk ja", "waarschijnlijk nee"
Gebruik voor categorie alleen één van de vijf namen hierboven, exact zoals geschreven."""


def analyze_transcript(transcript: str, contact_name: str = "") -> dict:
    """
    Analyseer de transcriptie met Claude.
    Geeft een dict terug met: samenvatting, categorie, reden, vsl_bekeken, vsl_toelichting.
    """
    user_message = "Analyseer dit verkoopgesprek:\n\n"
    if contact_name:
        user_message += f"Contact: {contact_name}\n\n"
    user_message += f"Transcriptie:\n{transcript}"

    response = claude_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text_content = next(
        (block.text for block in response.content if hasattr(block, "text")),
        "",
    )

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


def format_note(analysis: dict) -> str:
    """Formatteer de korte notitie die in GHL wordt geplaatst."""
    category_labels = {
        "geen_fit_geen_interesse": "🔴 Geen fit & geen interesse",
        "icp_geen_fit": "🟠 ICP maar geen fit",
        "icp_geen_interesse": "🟡 ICP met geen interesse",
        "icp_niet_warm": "🔵 ICP - niet warm genoeg",
        "icp_gepland": "🟢 ICP - Gepland/Ingeboekt",
    }
    vsl_icons = {
        "ja": "✅",
        "waarschijnlijk ja": "🟡",
        "waarschijnlijk nee": "🟠",
        "nee": "❌",
    }

    label = category_labels.get(analysis["categorie"], analysis["categorie"])
    vsl_status = analysis.get("vsl_bekeken", "onbekend")
    vsl_icon = vsl_icons.get(vsl_status, "❓")

    note = f"""📞 GESPREKSNOTITIE
Status: {label}
VSL bekeken: {vsl_icon} {vsl_status.capitalize()}

📝 {analysis['samenvatting']}

💡 {analysis['reden']}
VSL: {analysis.get('vsl_toelichting', '')}"""

    return note
