"""
Webhook server voor automatische GHL gespreksnotities.

Start met:
    uvicorn main:app --host 0.0.0.0 --port 8000

Stel de volgende webhook-URL in GHL in:
    https://jouw-server.com/webhook/call-completed
"""

from contextlib import asynccontextmanager
from datetime import datetime, time as dtime
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

import ghl_client
import ai_processor
import slack_reporter
from config import settings

# ─────────────────────────────────────────────
# Dagelijkse statistieken (reset om middernacht)
# ─────────────────────────────────────────────
def _empty_stats() -> dict:
    return {
        "total_webhooks": 0,          # Alle ontvangen call-webhooks
        "calls_with_recording": 0,    # Calls waarbij een opname gevonden werd
        "calls_processed": 0,         # Calls succesvol verwerkt door AI
        "categories": {               # Teller per pipeline-vakje
            "geen_fit_geen_interesse": 0,
            "icp_geen_fit": 0,
            "icp_geen_interesse": 0,
            "icp_niet_warm": 0,
            "icp_gepland": 0,
        },
        "vsl_bekeken_ja": 0,          # VSL zeker/waarschijnlijk bekeken
        "vsl_bekeken_nee": 0,         # VSL zeker/waarschijnlijk NIET bekeken
        "samenvattingen": [],         # [(categorie, samenvatting)] voor AI-inzichten
    }

daily_stats = _empty_stats()


async def send_and_reset():
    """Stuur het dagrapport naar Slack en reset de tellers."""
    global daily_stats
    await slack_reporter.send_daily_report(daily_stats)
    daily_stats = _empty_stats()
    print("[Scheduler] Stats gereset voor nieuwe dag.")


# ─────────────────────────────────────────────
# App lifecycle
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    # Stuur dagrapport op het ingestelde tijdstip (standaard 18:00)
    hour, minute = map(int, settings.daily_report_time.split(":"))
    scheduler.add_job(send_and_reset, CronTrigger(hour=hour, minute=minute))
    scheduler.start()
    print(f"[Scheduler] Dagrapport ingepland om {settings.daily_report_time}")
    yield
    scheduler.shutdown()


app = FastAPI(title="GHL Call Notes AI", version="1.0.0", lifespan=lifespan)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "stats_vandaag": daily_stats}


@app.post("/report/now")
async def trigger_report_now():
    """Stuur het dagrapport direct (handig voor testen)."""
    await send_and_reset()
    return {"status": "verstuurd"}


@app.post("/webhook/call-completed")
async def call_completed_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Ontvangt GHL webhooks wanneer een gesprek klaar is.
    Verwerking op de achtergrond zodat GHL direct een 200 OK krijgt.
    """
    if settings.webhook_secret:
        signature = request.headers.get("X-GHL-Signature", "")
        if not _verify_signature(await request.body(), signature):
            raise HTTPException(status_code=401, detail="Ongeldige webhook signature")

    payload = await request.json()
    event_type = payload.get("type", "")
    print(f"[Webhook] Ontvangen: {event_type}")

    if "call" not in event_type.lower() and "conversation" not in event_type.lower():
        return JSONResponse({"status": "genegeerd", "reden": f"Event type: {event_type}"})

    daily_stats["total_webhooks"] += 1
    background_tasks.add_task(process_call, payload)
    return JSONResponse({"status": "ontvangen"})


# ─────────────────────────────────────────────
# Hoofdverwerking
# ─────────────────────────────────────────────
async def process_call(payload: dict):
    """
    1. Haal opname op uit GHL
    2. Transcribeer met Whisper
    3. Analyseer met Claude (notitie + categorie + VSL-check)
    4. Voeg notitie toe in GHL
    5. Verplaats naar juist pipeline-vakje
    6. Update dagstatistieken
    """
    global daily_stats
    try:
        conversation_id = (
            payload.get("conversationId")
            or payload.get("conversation_id")
            or payload.get("id")
        )
        contact_id = (
            payload.get("contactId")
            or payload.get("contact_id")
            or payload.get("contact", {}).get("id")
        )
        contact_name = (
            payload.get("contactName")
            or payload.get("contact_name")
            or payload.get("contact", {}).get("name", "")
        )
        message_id = payload.get("messageId") or payload.get("message_id")
        recording_url = payload.get("recordingUrl") or payload.get("recording_url")

        if not conversation_id or not contact_id:
            print(f"[Verwerking] Ontbrekende IDs in payload: {payload}")
            return

        print(f"[Verwerking] Gesprek {conversation_id} – {contact_name or contact_id}")

        # Stap 1: Haal opname-URL op
        if not recording_url:
            if not message_id:
                messages = await ghl_client.get_conversation_messages(conversation_id)
                call_messages = [m for m in messages if m.get("type") in ("TYPE_CALL", "Call", "call")]
                if not call_messages:
                    print(f"[Verwerking] Geen gespreksberichten gevonden")
                    return
                message_id = call_messages[-1]["id"]

            recording_url = await ghl_client.get_call_recording_url(conversation_id, message_id)

        if not recording_url:
            print(f"[Verwerking] Geen opname gevonden voor {conversation_id}")
            return

        daily_stats["calls_with_recording"] += 1

        # Stap 2: Download en transcribeer
        audio_bytes = await ghl_client.download_recording(recording_url)
        transcript = await ai_processor.transcribe_audio(audio_bytes)
        print(f"[Verwerking] Transcriptie klaar ({len(transcript)} tekens)")

        if not transcript.strip():
            print(f"[Verwerking] Lege transcriptie")
            return

        # Stap 3: Analyseer met Claude
        analysis = ai_processor.analyze_transcript(transcript, contact_name)
        print(f"[Verwerking] Categorie: {analysis['categorie']} | VSL: {analysis.get('vsl_bekeken')}")

        # Stap 4: Notitie toevoegen in GHL
        note_text = ai_processor.format_note(analysis)
        await ghl_client.add_contact_note(contact_id, note_text)

        # Stap 5: Pipeline updaten
        await ghl_client.set_contact_pipeline_stage(contact_id, analysis["categorie"])

        # Stap 6: Statistieken bijwerken
        daily_stats["calls_processed"] += 1
        daily_stats["categories"][analysis["categorie"]] += 1

        vsl = analysis.get("vsl_bekeken", "nee")
        if "ja" in vsl:
            daily_stats["vsl_bekeken_ja"] += 1
        else:
            daily_stats["vsl_bekeken_nee"] += 1

        daily_stats["samenvattingen"].append({
            "categorie": analysis["categorie"],
            "samenvatting": analysis.get("samenvatting", ""),
        })

        print(f"[Verwerking] ✅ Klaar voor gesprek {conversation_id}")

    except Exception as e:
        print(f"[Verwerking] ❌ Fout: {e}")
        import traceback
        traceback.print_exc()


def _verify_signature(body: bytes, signature: str) -> bool:
    if not signature:
        return False
    # TODO: implementeer Ed25519 verificatie indien vereist door GHL
    return True
