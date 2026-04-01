"""
Dagelijks Slack-rapport met gespreksstatistieken.
Wordt elke avond automatisch verstuurd.
"""

import httpx
import anthropic
from datetime import date
from config import settings

claude_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

CATEGORY_LABELS = {
    "geen_fit_geen_interesse": "🔴 Geen fit & geen interesse",
    "icp_geen_fit": "🟠 ICP maar geen fit",
    "icp_geen_interesse": "🟡 ICP met geen interesse",
    "icp_niet_warm": "🔵 ICP - niet warm genoeg",
    "icp_gepland": "🟢 ICP - Gepland/Ingeboekt",
}


def generate_ai_insights(daily_stats: dict) -> str:
    """
    Laat Claude een korte analyse maken van de dagstatistieken:
    wat kom je het meest tegen en wat zijn verbeterpunten.
    """
    if not daily_stats["samenvattingen"]:
        return "Geen gesprekken om te analyseren."

    samenvattingen_tekst = "\n".join(
        f"- [{s['categorie']}] {s['samenvatting']}"
        for s in daily_stats["samenvattingen"]
    )

    response = claude_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": f"""Analyseer deze dagelijkse gesprekssamenvattingen van een verkoopteam
en geef in 3-5 zinnen:
1. Wat het meest voorkomt in de bezwaren of reacties
2. Waar waarschijnlijk verbeterpunten zitten

Gesprekken van vandaag:
{samenvattingen_tekst}

Geef een praktische, directe analyse. Geen bullet points, gewoon lopende tekst."""
        }],
    )

    return next(
        (block.text for block in response.content if hasattr(block, "text")),
        "Analyse niet beschikbaar.",
    )


async def send_daily_report(daily_stats: dict) -> bool:
    """
    Stuur het dagelijkse rapport naar Slack via de Incoming Webhook URL.
    Geeft True terug bij succes.
    """
    if not settings.slack_webhook_url:
        print("[Slack] Geen webhook URL ingesteld, rapport overgeslagen.")
        return False

    today = date.today().strftime("%d %B %Y")
    total = daily_stats["total_webhooks"]
    answered = daily_stats["calls_with_recording"]
    processed = daily_stats["calls_processed"]
    categories = daily_stats["categories"]
    vsl_ja = daily_stats["vsl_bekeken_ja"]
    vsl_nee = daily_stats["vsl_bekeken_nee"]

    # Bereken percentages per categorie
    cat_lines = []
    for cat_key, label in CATEGORY_LABELS.items():
        count = categories.get(cat_key, 0)
        pct = round((count / processed * 100) if processed > 0 else 0)
        cat_lines.append(f"{label}: *{count}* ({pct}%)")

    # Ophaalpercentage
    pickup_pct = round((answered / total * 100) if total > 0 else 0)

    # VSL-statistieken
    vsl_total = vsl_ja + vsl_nee
    vsl_pct = round((vsl_ja / vsl_total * 100) if vsl_total > 0 else 0)

    # AI-inzichten
    insights = generate_ai_insights(daily_stats)

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📞 Dagrapport gesprekken – {today}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Totaal gebeld:*\n{total}"},
                    {"type": "mrkdwn", "text": f"*Opgenomen:*\n{answered} ({pickup_pct}%)"},
                    {"type": "mrkdwn", "text": f"*Verwerkt door AI:*\n{processed}"},
                    {"type": "mrkdwn", "text": f"*VSL bekeken:*\n✅ {vsl_ja} van {vsl_total} ({vsl_pct}%)"},
                ]
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Verdeling per categorie:*\n" + "\n".join(cat_lines)}
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*🔍 AI-analyse:*\n{insights}"}
            },
        ]
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(settings.slack_webhook_url, json=message)
        if resp.status_code == 200:
            print(f"[Slack] Dagrapport verstuurd voor {today}")
            return True
        else:
            print(f"[Slack] Fout bij versturen: {resp.status_code} - {resp.text}")
            return False
